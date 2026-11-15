//! Constant-time, table-free AES-256 and AES-256-GCM (SP 800-38D).
//!
//! * The S-box and inverse S-box are computed, never looked up: inversion in
//!   GF(2^8) as `x^254` (an Itoh-Tsujii chain of four packed multiplications
//!   and three GF(2)-linear packed Frobenius maps) followed by the affine map.
//!   All 16 state bytes are processed at once inside one `u128`.
//! * MixColumns / InvMixColumns use packed `xtime` and lane rotations.
//! * GHASH is the BearSSL `ghash_ctmul64` technique: carry-less multiplication
//!   from ordinary integer multiplications of "holey" operands, the high half
//!   from bit reversal, then reduction modulo `x^128 + x^7 + x^2 + x + 1` with
//!   shifts and XORs.
//!
//! Secret data: key, round keys, plaintext, keystream, GHASH key `H`, GHASH
//! state and the computed tag before comparison. Lengths, the nonce and the
//! accept/reject outcome of [`gcm::open`] are public.
//!
//! The only assumption about the target is that 64-bit integer multiplication
//! takes data-independent time (true on all mainstream 64-bit CPUs). The code
//! has no `unsafe`, no allocation and no table lookup indexed by a secret.
//! Local temporaries held in registers or the stack frame cannot be wiped
//! with certainty from safe Rust; the long-lived secrets (round keys, `H`,
//! GHASH state, keystream blocks, tag) are wiped explicitly.

use crate::ct;
use core::hint::black_box;

// ---------------------------------------------------------------------------
// Packed GF(2^8) arithmetic: 16 field elements in the 16 bytes of a u128.
// ---------------------------------------------------------------------------

/// 0x01 in every byte.
const ONES: u128 = 0x0101_0101_0101_0101_0101_0101_0101_0101;
/// 0x7f in every byte.
const LO7: u128 = 0x7f7f_7f7f_7f7f_7f7f_7f7f_7f7f_7f7f_7f7f;
/// 1 in every 32-bit lane.
const LANES: u128 = 0x0000_0001_0000_0001_0000_0001_0000_0001;

/// Multiply every byte by `x` (i.e. 2) in GF(2^8) modulo 0x11b.
#[inline(always)]
fn xtime(a: u128) -> u128 {
    let hi = (a >> 7) & ONES; // 1 where the top bit of a byte was set
    ((a & LO7) << 1) ^ (hi ^ (hi << 1) ^ (hi << 3) ^ (hi << 4)) // 0x1b = 1+2+8+16
}

/// Bytewise GF(2^8) product of `a` and `b` (masks only, no branches).
#[inline(always)]
fn gf_mul(mut a: u128, b: u128) -> u128 {
    let mut acc = 0u128;
    let mut i = 0;
    while i < 8 {
        let mask = ((b >> i) & ONES).wrapping_mul(0xff);
        acc ^= a & mask;
        a = xtime(a);
        i += 1;
    }
    acc
}

/// Scalar GF(2^8) product, used only at compile time.
const fn gmul_const(mut a: u8, mut b: u8) -> u8 {
    let mut r = 0u8;
    let mut i = 0;
    while i < 8 {
        if b & 1 != 0 {
            r ^= a;
        }
        let hi = a & 0x80;
        a <<= 1;
        if hi != 0 {
            a ^= 0x1b;
        }
        b >>= 1;
        i += 1;
    }
    r
}

/// Constants of the GF(2)-linear map `a -> a^(2^k)`: entry `i` is `(x^i)^(2^k)`.
const fn frob_consts(k: u32) -> [u8; 8] {
    let mut out = [0u8; 8];
    let mut i = 0;
    while i < 8 {
        let mut v = 1u8;
        let mut j = 0;
        while j < i {
            v = gmul_const(v, 2);
            j += 1;
        }
        let mut t = 0;
        while t < k {
            v = gmul_const(v, v);
            t += 1;
        }
        out[i] = v;
        i += 1;
    }
    out
}

const FROB1: [u8; 8] = frob_consts(1);
const FROB2: [u8; 8] = frob_consts(2);
const FROB4: [u8; 8] = frob_consts(4);

/// Packed Frobenius power `a^(2^k)` for the constants of `frob_consts(k)`.
#[inline(always)]
fn frob(a: u128, c: &[u8; 8]) -> u128 {
    let mut acc = 0u128;
    let mut i = 0;
    while i < 8 {
        // `i` is a public loop counter; bit i of every byte, times the constant.
        acc ^= ((a >> i) & ONES).wrapping_mul(c[i] as u128);
        i += 1;
    }
    acc
}

/// Bytewise inverse in GF(2^8) via `a^254` (0 maps to 0).
#[inline(always)]
fn gf_inv(a: u128) -> u128 {
    let a2 = frob(a, &FROB1); // a^2
    let a3 = gf_mul(a2, a); // a^3
    let a12 = frob(a3, &FROB2); // a^12
    let a14 = gf_mul(a12, a2); // a^14
    let a15 = gf_mul(a12, a3); // a^15
    let a240 = frob(a15, &FROB4); // a^240
    gf_mul(a240, a14) // a^254
}

/// Rotate every byte left by `R` bits (1 <= R <= 7).
#[inline(always)]
fn rolb<const R: u32>(a: u128) -> u128 {
    let m1 = (((0xffu16 << R) & 0xff) as u128) * ONES;
    let m2 = ((0xffu16 >> (8 - R)) as u128) * ONES;
    ((a << R) & m1) | ((a >> (8 - R)) & m2)
}

/// SubBytes on 16 packed bytes.
#[inline(always)]
fn sub_bytes(a: u128) -> u128 {
    let y = gf_inv(a);
    y ^ rolb::<1>(y) ^ rolb::<2>(y) ^ rolb::<3>(y) ^ rolb::<4>(y) ^ (0x63 * ONES)
}

/// InvSubBytes on 16 packed bytes.
#[inline(always)]
fn inv_sub_bytes(a: u128) -> u128 {
    let x = rolb::<1>(a) ^ rolb::<3>(a) ^ rolb::<6>(a) ^ (0x05 * ONES);
    gf_inv(x)
}

/// Rotate every 32-bit lane right by `N` bytes: byte `r` of a column becomes
/// byte `r + N`.
#[inline(always)]
fn rot_cols<const N: u32>(a: u128) -> u128 {
    let lo = ((0xffff_ffffu32 >> (8 * N)) as u128) * LANES;
    let hi = ((0xffff_ffffu32 << (32 - 8 * N)) as u128) * LANES;
    ((a >> (8 * N)) & lo) | ((a << (32 - 8 * N)) & hi)
}

#[inline(always)]
fn mix_columns(a: u128) -> u128 {
    let r1 = rot_cols::<1>(a);
    xtime(a) ^ xtime(r1) ^ r1 ^ rot_cols::<2>(a) ^ rot_cols::<3>(a)
}

#[inline(always)]
fn inv_mix_columns(a: u128) -> u128 {
    // Multiply by {04}(x^2 + 1) first, then apply MixColumns (FIPS 197 §5.3.3 trick).
    let t = xtime(xtime(a ^ rot_cols::<2>(a)));
    mix_columns(a ^ t)
}

/// ShiftRows; the permutation is fixed and public.
#[inline(always)]
fn shift_rows(s: u128) -> u128 {
    let b = s.to_le_bytes();
    let mut o = [0u8; 16];
    let mut c = 0;
    while c < 4 {
        let mut r = 0;
        while r < 4 {
            o[4 * c + r] = b[4 * ((c + r) % 4) + r];
            r += 1;
        }
        c += 1;
    }
    u128::from_le_bytes(o)
}

#[inline(always)]
fn inv_shift_rows(s: u128) -> u128 {
    let b = s.to_le_bytes();
    let mut o = [0u8; 16];
    let mut c = 0;
    while c < 4 {
        let mut r = 0;
        while r < 4 {
            o[4 * c + r] = b[4 * ((c + 4 - r) % 4) + r];
            r += 1;
        }
        c += 1;
    }
    u128::from_le_bytes(o)
}

/// SubBytes applied to 16 bytes, exposed so tests can check the computed
/// S-box against a reference table. Not part of the stable API.
#[doc(hidden)]
pub fn sbox_block(block: &[u8; 16]) -> [u8; 16] {
    sub_bytes(u128::from_le_bytes(*block)).to_le_bytes()
}

/// InvSubBytes applied to 16 bytes, exposed for tests. Not part of the stable API.
#[doc(hidden)]
pub fn inv_sbox_block(block: &[u8; 16]) -> [u8; 16] {
    inv_sub_bytes(u128::from_le_bytes(*block)).to_le_bytes()
}

// ---------------------------------------------------------------------------
// AES-256
// ---------------------------------------------------------------------------

const ROUNDS: usize = 14;
const RCON: [u8; 7] = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40];

/// SubWord on one little-endian word, using the table-free S-box.
#[inline(always)]
fn sub_word(w: u32) -> u32 {
    sub_bytes(w as u128) as u32
}

/// AES-256 block cipher with an expanded key (zeroized on Drop).
pub struct Aes256 {
    rk: [u128; ROUNDS + 1],
}

impl Aes256 {
    /// Expands `key` into the 15 round keys. The key schedule uses the same
    /// table-free S-box as the cipher.
    pub fn new(key: &[u8; 32]) -> Self {
        let mut w = [0u32; 4 * (ROUNDS + 1)];
        let mut i = 0;
        while i < 8 {
            w[i] = u32::from_le_bytes([key[4 * i], key[4 * i + 1], key[4 * i + 2], key[4 * i + 3]]);
            i += 1;
        }
        // `i` is a public loop counter, so the branches below are public.
        while i < w.len() {
            let mut t = w[i - 1];
            if i % 8 == 0 {
                t = sub_word(t.rotate_right(8)) ^ (RCON[i / 8 - 1] as u32);
            } else if i % 8 == 4 {
                t = sub_word(t);
            }
            w[i] = w[i - 8] ^ t;
            i += 1;
        }
        let mut rk = [0u128; ROUNDS + 1];
        let mut r = 0;
        while r <= ROUNDS {
            rk[r] = (w[4 * r] as u128)
                | ((w[4 * r + 1] as u128) << 32)
                | ((w[4 * r + 2] as u128) << 64)
                | ((w[4 * r + 3] as u128) << 96);
            r += 1;
        }
        ct::zeroize_u32(&mut w);
        Aes256 { rk }
    }

    /// Encrypts one 16-byte block in place.
    pub fn encrypt_block(&self, block: &mut [u8; 16]) {
        let mut s = u128::from_le_bytes(*block) ^ self.rk[0];
        let mut r = 1;
        while r < ROUNDS {
            s = mix_columns(shift_rows(sub_bytes(s))) ^ self.rk[r];
            r += 1;
        }
        s = shift_rows(sub_bytes(s)) ^ self.rk[ROUNDS];
        *block = s.to_le_bytes();
        s = 0;
        black_box(&mut s);
    }

    /// Decrypts one 16-byte block in place.
    pub fn decrypt_block(&self, block: &mut [u8; 16]) {
        let mut s = u128::from_le_bytes(*block) ^ self.rk[ROUNDS];
        let mut r = ROUNDS - 1;
        while r >= 1 {
            s = inv_mix_columns(inv_sub_bytes(inv_shift_rows(s)) ^ self.rk[r]);
            r -= 1;
        }
        s = inv_sub_bytes(inv_shift_rows(s)) ^ self.rk[0];
        *block = s.to_le_bytes();
        s = 0;
        black_box(&mut s);
    }
}

impl Drop for Aes256 {
    fn drop(&mut self) {
        for k in self.rk.iter_mut() {
            *k = 0;
        }
        black_box(&mut self.rk);
    }
}

// ---------------------------------------------------------------------------
// GCM
// ---------------------------------------------------------------------------

/// AES-256-GCM (SP 800-38D), 96-bit nonce, 128-bit tag.
pub mod gcm {
    use super::Aes256;
    use crate::ct;

    /// Nonce length in bytes (96 bits).
    pub const NONCE_LEN: usize = 12;
    /// Tag length in bytes (128 bits).
    pub const TAG_LEN: usize = 16;
    /// Maximum plaintext/ciphertext length in bytes: `(2^32 - 2)` blocks of
    /// 16 bytes (SP 800-38D §5.2.1.1; the 32-bit counter starts at 2).
    pub const MAX_DATA_LEN: u64 = ((1u64 << 32) - 2) * 16;

    /// Carry-less 64x64 -> low 64 bits using integer multiplication on
    /// operands with 3 of every 4 bits cleared (BearSSL `bmul64`).
    #[inline(always)]
    fn bmul64(x: u64, y: u64) -> u64 {
        const M0: u64 = 0x1111_1111_1111_1111;
        const M1: u64 = 0x2222_2222_2222_2222;
        const M2: u64 = 0x4444_4444_4444_4444;
        const M3: u64 = 0x8888_8888_8888_8888;
        let (x0, x1, x2, x3) = (x & M0, x & M1, x & M2, x & M3);
        let (y0, y1, y2, y3) = (y & M0, y & M1, y & M2, y & M3);
        let z0 = x0.wrapping_mul(y0) ^ x1.wrapping_mul(y3) ^ x2.wrapping_mul(y2) ^ x3.wrapping_mul(y1);
        let z1 = x0.wrapping_mul(y1) ^ x1.wrapping_mul(y0) ^ x2.wrapping_mul(y3) ^ x3.wrapping_mul(y2);
        let z2 = x0.wrapping_mul(y2) ^ x1.wrapping_mul(y1) ^ x2.wrapping_mul(y0) ^ x3.wrapping_mul(y3);
        let z3 = x0.wrapping_mul(y3) ^ x1.wrapping_mul(y2) ^ x2.wrapping_mul(y1) ^ x3.wrapping_mul(y0);
        (z0 & M0) | (z1 & M1) | (z2 & M2) | (z3 & M3)
    }

    /// GHASH state with the key powers precomputed (all secret).
    struct Ghash {
        /// `[h0, h1, rev(h0), rev(h1), h0^h1, rev(h0)^rev(h1)]`
        h: [u64; 6],
        /// `[y0, y1]`: `y1` holds the first 8 bytes (big-endian).
        y: [u64; 2],
    }

    impl Ghash {
        fn new(hb: &[u8; 16]) -> Self {
            let h1 = u64::from_be_bytes([hb[0], hb[1], hb[2], hb[3], hb[4], hb[5], hb[6], hb[7]]);
            let h0 = u64::from_be_bytes([hb[8], hb[9], hb[10], hb[11], hb[12], hb[13], hb[14], hb[15]]);
            let (h0r, h1r) = (h0.reverse_bits(), h1.reverse_bits());
            Ghash { h: [h0, h1, h0r, h1r, h0 ^ h1, h0r ^ h1r], y: [0, 0] }
        }

        /// `y = (y ^ block) * H` in GF(2^128).
        fn block(&mut self, b: &[u8; 16]) {
            let [h0, h1, h0r, h1r, h2, h2r] = self.h;
            let y1 = self.y[1] ^ u64::from_be_bytes([b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7]]);
            let y0 = self.y[0] ^ u64::from_be_bytes([b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]]);
            let (y0r, y1r) = (y0.reverse_bits(), y1.reverse_bits());
            let (y2, y2r) = (y0 ^ y1, y0r ^ y1r);

            // Karatsuba: three 64x64 -> 128 products; high halves via bit reversal.
            let z0 = bmul64(y0, h0);
            let z1 = bmul64(y1, h1);
            let mut z2 = bmul64(y2, h2);
            let mut z0h = bmul64(y0r, h0r);
            let mut z1h = bmul64(y1r, h1r);
            let mut z2h = bmul64(y2r, h2r);
            z2 ^= z0 ^ z1;
            z2h ^= z0h ^ z1h;
            z0h = z0h.reverse_bits() >> 1;
            z1h = z1h.reverse_bits() >> 1;
            z2h = z2h.reverse_bits() >> 1;

            let v0 = z0;
            let mut v1 = z0h ^ z2;
            let mut v2 = z1 ^ z2h;
            let mut v3 = z1h;

            // Shift the 256-bit product left by one (reflected representation).
            v3 = (v3 << 1) | (v2 >> 63);
            v2 = (v2 << 1) | (v1 >> 63);
            v1 = (v1 << 1) | (v0 >> 63);
            let v0 = v0 << 1;

            // Reduce modulo x^128 + x^7 + x^2 + x + 1 (reflected: shifts right).
            v2 ^= v0 ^ (v0 >> 1) ^ (v0 >> 2) ^ (v0 >> 7);
            v1 ^= (v0 << 63) ^ (v0 << 62) ^ (v0 << 57);
            v3 ^= v1 ^ (v1 >> 1) ^ (v1 >> 2) ^ (v1 >> 7);
            v2 ^= (v1 << 63) ^ (v1 << 62) ^ (v1 << 57);

            self.y = [v2, v3];
        }

        /// Absorbs `data`, zero-padding the final partial block. Lengths are public.
        fn update(&mut self, data: &[u8]) {
            let mut chunks = data.chunks_exact(16);
            for c in &mut chunks {
                let mut b = [0u8; 16];
                b.copy_from_slice(c);
                self.block(&b);
            }
            let rem = chunks.remainder();
            if !rem.is_empty() {
                let mut b = [0u8; 16];
                b[..rem.len()].copy_from_slice(rem);
                self.block(&b);
                ct::zeroize(&mut b);
            }
        }

        /// Absorbs the length block and returns the GHASH value.
        fn finish(mut self, aad_len: usize, data_len: usize) -> [u8; 16] {
            let mut lb = [0u8; 16];
            lb[..8].copy_from_slice(&((aad_len as u64) << 3).to_be_bytes());
            lb[8..].copy_from_slice(&((data_len as u64) << 3).to_be_bytes());
            self.block(&lb);
            let mut out = [0u8; 16];
            out[..8].copy_from_slice(&self.y[1].to_be_bytes());
            out[8..].copy_from_slice(&self.y[0].to_be_bytes());
            out
        }
    }

    impl Drop for Ghash {
        fn drop(&mut self) {
            ct::zeroize_u64(&mut self.h);
            ct::zeroize_u64(&mut self.y);
        }
    }

    /// XORs the CTR keystream (counter starts at 2) into `data`.
    fn ctr_xor(cipher: &Aes256, nonce: &[u8; 12], data: &mut [u8]) {
        let mut ctr: u32 = 2;
        for chunk in data.chunks_mut(16) {
            let mut ks = [0u8; 16];
            ks[..12].copy_from_slice(nonce);
            ks[12..].copy_from_slice(&ctr.to_be_bytes());
            cipher.encrypt_block(&mut ks);
            for (d, k) in chunk.iter_mut().zip(ks.iter()) {
                *d ^= *k;
            }
            ct::zeroize(&mut ks);
            // The length limit guarantees the counter never wraps.
            ctr = ctr.wrapping_add(1);
        }
    }

    /// Computes the tag over `aad` and the ciphertext `ct_data`.
    fn compute_tag(cipher: &Aes256, nonce: &[u8; 12], aad: &[u8], ct_data: &[u8]) -> [u8; 16] {
        let mut h = [0u8; 16];
        cipher.encrypt_block(&mut h);
        let mut gh = Ghash::new(&h);
        ct::zeroize(&mut h);
        gh.update(aad);
        gh.update(ct_data);
        let mut s = gh.finish(aad.len(), ct_data.len());

        let mut ek = [0u8; 16];
        ek[..12].copy_from_slice(nonce);
        ek[15] = 1; // J0 = nonce || 0x00000001
        cipher.encrypt_block(&mut ek);
        for (t, k) in s.iter_mut().zip(ek.iter()) {
            *t ^= *k;
        }
        ct::zeroize(&mut ek);
        s
    }

    /// Encrypts `data` in place and returns the tag.
    ///
    /// The caller must never reuse a `nonce` with the same `key`: one repeat
    /// reveals the XOR of the plaintexts and lets an attacker forge tags.
    ///
    /// # Panics
    /// Panics if `data.len()` exceeds [`MAX_DATA_LEN`] (`(2^32 - 2)` blocks,
    /// the SP 800-38D limit). The length is public. The AAD limit (2^64 bits)
    /// cannot be exceeded by a slice on supported targets.
    pub fn seal(key: &[u8; 32], nonce: &[u8; 12], aad: &[u8], data: &mut [u8]) -> [u8; 16] {
        assert!(data.len() as u64 <= MAX_DATA_LEN, "AES-GCM plaintext exceeds 2^32-2 blocks");
        let cipher = Aes256::new(key);
        ctr_xor(&cipher, nonce, data);
        compute_tag(&cipher, nonce, aad, data)
    }

    /// Verifies the tag in constant time, then decrypts `data` in place. On
    /// failure returns `Err(VerificationFailed)` and leaves `data` as the
    /// ciphertext (never releases unauthenticated plaintext). Returns
    /// `Err(InvalidInput)` (data untouched) if `data.len()` exceeds
    /// [`MAX_DATA_LEN`].
    pub fn open(
        key: &[u8; 32],
        nonce: &[u8; 12],
        aad: &[u8],
        data: &mut [u8],
        tag: &[u8; 16],
    ) -> Result<(), crate::Error> {
        if data.len() as u64 > MAX_DATA_LEN {
            return Err(crate::Error::InvalidInput); // public length
        }
        let cipher = Aes256::new(key);
        let mut expected = compute_tag(&cipher, nonce, aad, data);
        let ok = ct::eq(&expected, tag);
        ct::zeroize(&mut expected);
        // DECLASSIFY: the accept/reject bit is the public output of AEAD
        // verification; it is revealed anyway by the return value.
        if ct::declassify_u8(ok) != 0xff {
            return Err(crate::Error::VerificationFailed);
        }
        ctr_xor(&cipher, nonce, data);
        Ok(())
    }
}

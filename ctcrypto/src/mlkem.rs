//! ML-KEM-1024 (FIPS 203), derandomized `*_internal` interface.
//!
//! Parameter set ML-KEM-1024: n = 256, q = 3329, k = 4, eta1 = eta2 = 2,
//! d_u = 11, d_v = 5. The caller supplies all randomness (d, z, m).
//!
//! Constant-time notes (crate rules in `lib.rs`):
//!
//! * Modular arithmetic uses Montgomery and Barrett reduction (multiply and
//!   shift only). `Compress_d` uses a multiply-and-shift reciprocal of 2q that
//!   is exact for every input that can occur (checked exhaustively in the unit
//!   tests); `Decompress_d` is a multiply, add and shift. No `/` or `%` is
//!   applied to any runtime value; the only `/` and `%` in this file are in
//!   `const` items evaluated at compile time on public constants.
//! * CBD sampling, message encoding/decoding and the canonical-range fix-up
//!   use bit arithmetic and sign masks; implicit rejection in [`decaps`] uses
//!   [`ct::eq`] and [`ct::cmov`].
//! * Arithmetic on secret-derived values uses `wrapping_*` operations, so that
//!   debug builds contain no overflow-check branches on secrets. Bounds are
//!   argued at each site and the result is checked by the tests.
//! * Branches occur only on public data: rho and the matrix A (rejection
//!   sampling from XOF(rho, i, j)), the encapsulation-key bytes, received
//!   ciphertext bytes, and the declassified results of the §7.2 / §7.3 input
//!   checks. Every point where a secret-derived value becomes public goes
//!   through `ct::declassify*` with a comment saying why.
//! * Secret temporaries are wiped before return; the Keccak sponge wipes its
//!   own state on drop.
//! * The 4x4 matrix A is never stored: each entry is sampled when it is used,
//!   so peak stack use stays at a few kilobytes of polynomials.

use crate::ct;
use crate::sha3::Sponge;
use crate::Error;

/// Length in bytes of an ML-KEM-1024 encapsulation key.
pub const EK_LEN: usize = 1568;
/// Length in bytes of an ML-KEM-1024 decapsulation key.
pub const DK_LEN: usize = 3168;
/// Length in bytes of an ML-KEM-1024 ciphertext.
pub const CT_LEN: usize = 1568;
/// Length in bytes of the shared secret.
pub const SS_LEN: usize = 32;

const N: usize = 256;
const Q: i16 = 3329;
const Q32: i32 = 3329;
const K: usize = 4;
const DU: u32 = 11;
const DV: u32 = 5;

/// Bytes of one ByteEncode_12 polynomial.
const POLY_BYTES: usize = 384;
/// Bytes of the K-PKE decryption key (= ByteEncode_12 of s-hat).
const PKE_DK_LEN: usize = K * POLY_BYTES; // 1536
/// Bytes of one compressed u-polynomial (32 * d_u).
const POLY_DU_BYTES: usize = 32 * DU as usize; // 352
/// Bytes of the compressed v-polynomial (32 * d_v).
const POLY_DV_BYTES: usize = 32 * DV as usize; // 160

// Layout of dk = dk_PKE || ek || H(ek) || z.
const DK_EK_OFF: usize = PKE_DK_LEN; // 1536
const DK_H_OFF: usize = DK_EK_OFF + EK_LEN; // 3104
const DK_Z_OFF: usize = DK_H_OFF + 32; // 3136

const _: () = assert!(EK_LEN == PKE_DK_LEN + 32);
const _: () = assert!(DK_LEN == DK_Z_OFF + 32);
const _: () = assert!(CT_LEN == K * POLY_DU_BYTES + POLY_DV_BYTES);

type Poly = [i16; N];

// ---------------------------------------------------------------------------
// Modular arithmetic (Montgomery R = 2^16, Barrett), multiply-and-shift only.
// ---------------------------------------------------------------------------

/// q^-1 mod 2^16, as a signed 16-bit value.
const QINV: i16 = -3327;

/// Montgomery reduction: for -2^15 q <= a < 2^15 q returns r = a * 2^-16 mod q with
/// |r| < q.
#[inline]
fn mont_reduce(a: i32) -> i16 {
    let t = (a as i16).wrapping_mul(QINV);
    (a.wrapping_sub((t as i32).wrapping_mul(Q32)) >> 16) as i16
}

/// a * b * 2^-16 mod q.
#[inline]
fn fqmul(a: i16, b: i16) -> i16 {
    mont_reduce((a as i32).wrapping_mul(b as i32))
}

/// Barrett reduction: for any i16 `a` returns the centered representative of
/// a mod q, in {-(q-1)/2, ..., (q-1)/2}.
#[inline]
fn barrett_reduce(a: i16) -> i16 {
    // Compile-time constant: round(2^26 / q) = 20159.
    const V: i32 = ((1 << 26) + Q32 / 2) / Q32;
    let t = (V.wrapping_mul(a as i32).wrapping_add(1 << 25)) >> 26;
    (a as i32).wrapping_sub(t.wrapping_mul(Q32)) as i16
}

/// Maps a centered representative (|a| < q) to [0, q) with a sign mask.
#[inline]
fn to_unsigned(a: i16) -> u16 {
    a.wrapping_add((a >> 15) & Q) as u16
}

// ---------------------------------------------------------------------------
// NTT. Twiddles are 17^brv7(i) * 2^16 mod q, centered, computed at compile
// time (public constants; the `%` below runs only in const evaluation).
// ---------------------------------------------------------------------------

const fn brv7(x: usize) -> usize {
    let mut r = 0;
    let mut i = 0;
    while i < 7 {
        r |= ((x >> i) & 1) << (6 - i);
        i += 1;
    }
    r
}

const ZETAS: [i16; 128] = {
    let mut z = [0i16; 128];
    let mut i = 0;
    while i < 128 {
        let e = brv7(i);
        let mut p: u32 = 1;
        let mut j = 0;
        while j < e {
            p = p * 17 % 3329;
            j += 1;
        }
        let mut v = (p * 65536 % 3329) as i32;
        if v > 3329 / 2 {
            v -= 3329;
        }
        z[i] = v as i16;
        i += 1;
    }
    z
};

/// Forward NTT (output in bit-reversed order). Input |a| < q gives output
/// |a| < 8q.
fn ntt(r: &mut Poly) {
    let mut k = 1;
    let mut len = 128;
    while len >= 2 {
        let mut start = 0;
        while start < N {
            let zeta = ZETAS[k];
            k += 1;
            for j in start..start + len {
                let t = fqmul(zeta, r[j + len]);
                r[j + len] = r[j].wrapping_sub(t);
                r[j] = r[j].wrapping_add(t);
            }
            start += 2 * len;
        }
        len >>= 1;
    }
}

/// Inverse NTT, multiplied by 2^16 (so a Montgomery factor from a base
/// multiplication is cancelled). Input |a| <= q/2 gives output |a| < q.
fn invntt(r: &mut Poly) {
    const F: i16 = 1441; // 2^32 / 128 mod q (mont^2 / 128)
    let mut k = 127;
    let mut len = 2;
    while len <= 128 {
        let mut start = 0;
        while start < N {
            let zeta = ZETAS[k];
            k -= 1;
            for j in start..start + len {
                let t = r[j];
                r[j] = barrett_reduce(t.wrapping_add(r[j + len]));
                r[j + len] = fqmul(zeta, r[j + len].wrapping_sub(t));
            }
            start += 2 * len;
        }
        len <<= 1;
    }
    for c in r.iter_mut() {
        *c = fqmul(*c, F);
    }
}

#[inline]
fn basemul(a0: i16, a1: i16, b0: i16, b1: i16, zeta: i16) -> (i16, i16) {
    let r0 = fqmul(fqmul(a1, b1), zeta).wrapping_add(fqmul(a0, b0));
    let r1 = fqmul(a0, b1).wrapping_add(fqmul(a1, b0));
    (r0, r1)
}

/// r += a ∘ b * 2^-16 (NTT-domain product). Each call adds less than 2q in
/// absolute value per coefficient; callers accumulate at most K = 4 products
/// from zero (< 8q < 2^15) and then reduce. Inputs must satisfy
/// |a * b| < 2^15 * q coefficient-wise (callers pass one operand < 2^12 and
/// the other Barrett-reduced, |x| <= q/2).
fn basemul_acc(r: &mut Poly, a: &Poly, b: &Poly) {
    for i in 0..N / 4 {
        let z = ZETAS[64 + i];
        let (x0, x1) = basemul(a[4 * i], a[4 * i + 1], b[4 * i], b[4 * i + 1], z);
        r[4 * i] = r[4 * i].wrapping_add(x0);
        r[4 * i + 1] = r[4 * i + 1].wrapping_add(x1);
        let (y0, y1) =
            basemul(a[4 * i + 2], a[4 * i + 3], b[4 * i + 2], b[4 * i + 3], z.wrapping_neg());
        r[4 * i + 2] = r[4 * i + 2].wrapping_add(y0);
        r[4 * i + 3] = r[4 * i + 3].wrapping_add(y1);
    }
}

fn poly_reduce(r: &mut Poly) {
    for c in r.iter_mut() {
        *c = barrett_reduce(*c);
    }
}

/// Multiplies by 2^16 mod q (into the Montgomery domain).
fn poly_tomont(r: &mut Poly) {
    const F: i16 = 1353; // 2^32 mod q
    for c in r.iter_mut() {
        *c = fqmul(*c, F);
    }
}

fn poly_add(r: &mut Poly, a: &Poly) {
    for (x, y) in r.iter_mut().zip(a.iter()) {
        *x = x.wrapping_add(*y);
    }
}

// ---------------------------------------------------------------------------
// Compression and byte encoding.
// ---------------------------------------------------------------------------

/// Reciprocal of 2q for the exact floor division in [`compress`]:
/// ceil(2^40 / 6658). For every numerator n < 2^24 the error term
/// n * (CM * 6658 - 2^40) stays below 2^40, so floor(n * CM / 2^40) equals
/// floor(n / 6658). Compile-time constant.
const CM: u64 = (1u64 << 40) / 6658 + 1;

/// Compress_d(x) = round_half_up(2^d * x / q) mod 2^d for x in [0, q),
/// computed as floor((2^(d+1) * x + q) / (2q)) with a multiply and a shift.
#[inline]
fn compress(x: u16, d: u32) -> u16 {
    let n = ((x as u64) << (d + 1)) + 3329;
    (((n * CM) >> 40) as u16) & ((1u16 << d) - 1)
}

/// Decompress_d(y) = round_half_up(q * y / 2^d) for y < 2^d.
#[inline]
fn decompress(y: u16, d: u32) -> i16 {
    (((y as u32) * 3329 + (1 << (d - 1))) >> d) as i16
}

/// Packs 256 values of `d` bits each, little-endian bit order, into
/// `out` (32 * d bytes). Loop structure depends only on the public `d`.
fn pack(vals: &[u16; N], d: u32, out: &mut [u8]) {
    debug_assert_eq!(out.len(), 32 * d as usize);
    let mut acc: u32 = 0;
    let mut bits: u32 = 0;
    let mut o = 0;
    for &v in vals.iter() {
        acc |= (v as u32) << bits;
        bits += d;
        while bits >= 8 {
            out[o] = acc as u8;
            o += 1;
            acc >>= 8;
            bits -= 8;
        }
    }
}

/// Inverse of [`pack`]: 256 values of `d` bits each from 32 * d bytes.
fn unpack(inp: &[u8], d: u32, out: &mut [u16; N]) {
    debug_assert_eq!(inp.len(), 32 * d as usize);
    let mask = (1u32 << d) - 1;
    let mut acc: u32 = 0;
    let mut bits: u32 = 0;
    let mut idx = 0;
    for v in out.iter_mut() {
        while bits < d {
            acc |= (inp[idx] as u32) << bits;
            idx += 1;
            bits += 8;
        }
        *v = (acc & mask) as u16;
        acc >>= d;
        bits -= d;
    }
}

/// ByteEncode_12 of a polynomial with coefficients |a| < q (any sign); the
/// coefficients are first mapped to [0, q). `tmp` is caller scratch.
fn encode12(p: &Poly, tmp: &mut [u16; N], out: &mut [u8]) {
    for (t, &c) in tmp.iter_mut().zip(p.iter()) {
        *t = to_unsigned(barrett_reduce(c));
    }
    pack(tmp, 12, out);
}

/// ByteDecode_12 without the final mod-q reduction: coefficients are the raw
/// 12-bit values (< 4096). They are only ever used as operands of
/// Montgomery multiplication, which is correct for any representative of the
/// residue class, so this equals FIPS 203's ByteDecode_12 (which reduces mod q)
/// up to congruence and all outputs are identical.
fn decode12(inp: &[u8], tmp: &mut [u16; N], out: &mut Poly) {
    unpack(inp, 12, tmp);
    for (o, &t) in out.iter_mut().zip(tmp.iter()) {
        *o = t as i16;
    }
}

/// Compress_d then ByteEncode_d of a polynomial with |a| < 2^15 (reduced here).
fn compress_encode(p: &Poly, d: u32, tmp: &mut [u16; N], out: &mut [u8]) {
    for (t, &c) in tmp.iter_mut().zip(p.iter()) {
        *t = compress(to_unsigned(barrett_reduce(c)), d);
    }
    pack(tmp, d, out);
}

/// ByteDecode_d then Decompress_d (public ciphertext input).
fn decode_decompress(inp: &[u8], d: u32, tmp: &mut [u16; N], out: &mut Poly) {
    unpack(inp, d, tmp);
    for (o, &t) in out.iter_mut().zip(tmp.iter()) {
        *o = decompress(t, d);
    }
}

/// Decompress_1(ByteDecode_1(m)): coefficient i is 1665 if bit i of m is set,
/// else 0, selected with a mask.
fn poly_frommsg(m: &[u8; 32], out: &mut Poly) {
    for i in 0..N {
        let bit = ((m[i >> 3] >> (i & 7)) & 1) as i16;
        out[i] = bit.wrapping_neg() & ((Q + 1) / 2);
    }
}

/// ByteEncode_1(Compress_1(p)) with mask arithmetic only.
fn poly_tomsg(p: &Poly, out: &mut [u8; 32]) {
    for (i, byte) in out.iter_mut().enumerate() {
        let mut b = 0u8;
        for j in 0..8 {
            let c = compress(to_unsigned(barrett_reduce(p[8 * i + j])), 1) as u8;
            b |= c << j;
        }
        *byte = b;
    }
}

// ---------------------------------------------------------------------------
// Sampling.
// ---------------------------------------------------------------------------

/// SampleNTT(XOF(rho || x || y)). All inputs and the XOF output are public, so
/// the data-dependent rejection loop is allowed.
fn sample_ntt(rho: &[u8; 32], x: u8, y: u8, a: &mut Poly) {
    let mut s = Sponge::shake128();
    s.absorb(rho);
    s.absorb(&[x, y]);
    let mut buf = [0u8; 168];
    let mut j = 0;
    while j < N {
        s.squeeze(&mut buf);
        for c in buf.chunks_exact(3) {
            let d1 = (c[0] as u16) | (((c[1] as u16) & 0x0f) << 8);
            let d2 = ((c[1] as u16) >> 4) | ((c[2] as u16) << 4);
            if d1 < Q as u16 && j < N {
                a[j] = d1 as i16;
                j += 1;
            }
            if d2 < Q as u16 && j < N {
                a[j] = d2 as i16;
                j += 1;
            }
        }
    }
}

/// SamplePolyCBD_2(PRF_2(seed, nonce)), bit arithmetic only. Output in [-2, 2].
fn prf_cbd2(seed: &[u8; 32], nonce: u8, p: &mut Poly) {
    let mut buf = [0u8; 128];
    let mut s = Sponge::shake256();
    s.absorb(seed);
    s.absorb(&[nonce]);
    s.squeeze(&mut buf);
    for i in 0..32 {
        let t = u32::from_le_bytes([buf[4 * i], buf[4 * i + 1], buf[4 * i + 2], buf[4 * i + 3]]);
        let d = (t & 0x5555_5555).wrapping_add((t >> 1) & 0x5555_5555);
        for j in 0..8 {
            let a = ((d >> (4 * j)) & 3) as i16;
            let b = ((d >> (4 * j + 2)) & 3) as i16;
            p[8 * i + j] = a.wrapping_sub(b);
        }
    }
    ct::zeroize(&mut buf);
}

// ---------------------------------------------------------------------------
// Hash functions G, H, J.
// ---------------------------------------------------------------------------

/// G(a || b) = SHA3-512.
fn g(a: &[u8], b: &[u8], out: &mut [u8; 64]) {
    let mut s = Sponge::sha3_512();
    s.absorb(a);
    s.absorb(b);
    s.squeeze(out);
}

/// H(x) = SHA3-256.
fn h(x: &[u8]) -> [u8; 32] {
    crate::sha3::sha3_256(x)
}

/// J(a || b) = SHAKE256(a || b, 32 bytes).
fn j(a: &[u8], b: &[u8], out: &mut [u8; 32]) {
    let mut s = Sponge::shake256();
    s.absorb(a);
    s.absorb(b);
    s.squeeze(out);
}

// ---------------------------------------------------------------------------
// K-PKE.
// ---------------------------------------------------------------------------

/// K-PKE.Encrypt(ek_PKE, m, r) into `out`. `ek` is the 1568-byte encryption
/// key; `rho` is its last 32 bytes, passed separately because the caller must
/// have marked it public (it drives rejection sampling). `m` and `r` are
/// secret; `out` is secret until the caller publishes or compares it.
fn pke_encrypt(ek: &[u8], rho: &[u8; 32], m: &[u8; 32], r: &[u8; 32], out: &mut [u8; CT_LEN]) {
    debug_assert_eq!(ek.len(), EK_LEN);
    let mut y = [[0i16; N]; K];
    let mut a = [0i16; N];
    let mut acc = [0i16; N];
    let mut e = [0i16; N];
    let mut tmp = [0u16; N];

    // y-hat = NTT(y), y_i from PRF(r, i), reduced to |x| <= q/2.
    for (i, yi) in y.iter_mut().enumerate() {
        prf_cbd2(r, i as u8, yi);
        ntt(yi);
        poly_reduce(yi);
    }

    // u_i = NTT^-1( sum_j A[j][i] * y-hat_j ) + e1_i, A[j][i] = SampleNTT(rho||i||j).
    for i in 0..K {
        acc.fill(0);
        for (jj, yj) in y.iter().enumerate() {
            sample_ntt(rho, i as u8, jj as u8, &mut a);
            basemul_acc(&mut acc, &a, yj); // a in [0,q), yj reduced
        }
        poly_reduce(&mut acc);
        invntt(&mut acc); // |acc| < q
        prf_cbd2(r, (K + i) as u8, &mut e);
        poly_add(&mut acc, &e); // < q + 2
        compress_encode(&acc, DU, &mut tmp, &mut out[i * POLY_DU_BYTES..(i + 1) * POLY_DU_BYTES]);
    }

    // v = NTT^-1( sum_j t-hat_j * y-hat_j ) + e2 + Decompress_1(m).
    acc.fill(0);
    for (jj, yj) in y.iter().enumerate() {
        decode12(&ek[jj * POLY_BYTES..(jj + 1) * POLY_BYTES], &mut tmp, &mut a); // < 4096
        basemul_acc(&mut acc, &a, yj);
    }
    poly_reduce(&mut acc);
    invntt(&mut acc); // |acc| < q
    prf_cbd2(r, (2 * K) as u8, &mut e);
    poly_add(&mut acc, &e);
    poly_frommsg(m, &mut e);
    poly_add(&mut acc, &e); // < q + 2 + 1665
    compress_encode(&acc, DV, &mut tmp, &mut out[K * POLY_DU_BYTES..]);

    for yi in y.iter_mut() {
        ct::zeroize_i16(yi);
    }
    ct::zeroize_i16(&mut acc);
    ct::zeroize_i16(&mut e);
    ct::zeroize_i16(&mut a);
    zeroize_u16(&mut tmp);
}

/// K-PKE.Decrypt(dk_PKE, c). `dk_pke` is secret; `c` is the received public
/// ciphertext. Returns m' (secret) in `m`.
fn pke_decrypt(dk_pke: &[u8], c: &[u8; CT_LEN], m: &mut [u8; 32]) {
    debug_assert_eq!(dk_pke.len(), PKE_DK_LEN);
    let mut u = [0i16; N];
    let mut s = [0i16; N];
    let mut w = [0i16; N];
    let mut tmp = [0u16; N];

    for i in 0..K {
        decode_decompress(&c[i * POLY_DU_BYTES..(i + 1) * POLY_DU_BYTES], DU, &mut tmp, &mut u);
        ntt(&mut u); // input <= 3328 < q
        poly_reduce(&mut u);
        decode12(&dk_pke[i * POLY_BYTES..(i + 1) * POLY_BYTES], &mut tmp, &mut s); // < 4096
        basemul_acc(&mut w, &s, &u);
    }
    poly_reduce(&mut w);
    invntt(&mut w); // |w| < q
    decode_decompress(&c[K * POLY_DU_BYTES..], DV, &mut tmp, &mut u); // v' in [0, q)
    for (x, y) in w.iter_mut().zip(u.iter()) {
        *x = y.wrapping_sub(*x); // v' - w, |.| < 2q
    }
    poly_tomsg(&w, m);

    ct::zeroize_i16(&mut s);
    ct::zeroize_i16(&mut w);
    ct::zeroize_i16(&mut u);
    zeroize_u16(&mut tmp);
}

/// Wipes a secret `u16` buffer. The crate's `ct` module has no u16 variant
/// and this module may not edit it; same construction as `ct::zeroize_i16`.
fn zeroize_u16(buf: &mut [u16]) {
    for b in buf.iter_mut() {
        *b = 0;
    }
    core::hint::black_box(buf);
}

// ---------------------------------------------------------------------------
// ML-KEM.
// ---------------------------------------------------------------------------

/// FIPS 203 Algorithm 16 ML-KEM.KeyGen_internal(d, z). Returns (ek, dk).
///
/// `d` and `z` are secret 32-byte seeds supplied by the caller (from an
/// approved RBG). `dk` is secret; `ek` is public.
pub fn keygen_internal(d: &[u8; 32], z: &[u8; 32]) -> ([u8; EK_LEN], [u8; DK_LEN]) {
    let mut ek = [0u8; EK_LEN];
    let mut dk = [0u8; DK_LEN];

    // (rho, sigma) = G(d || k).
    let mut gout = [0u8; 64];
    g(d, &[K as u8], &mut gout);
    let mut rho = [0u8; 32];
    rho.copy_from_slice(&gout[..32]);
    // DECLASSIFY: rho is the public matrix seed; FIPS 203 publishes it as the
    // last 32 bytes of ek. It must be public before it drives the
    // data-dependent rejection sampling of A.
    ct::declassify(&mut rho);
    let mut sigma = [0u8; 32];
    sigma.copy_from_slice(&gout[32..]);
    ct::zeroize(&mut gout);

    let mut s = [[0i16; N]; K];
    let mut a = [0i16; N];
    let mut acc = [0i16; N];
    let mut e = [0i16; N];
    let mut tmp = [0u16; N];

    // s-hat = NTT(s), s_i from PRF(sigma, i), reduced to |x| <= q/2.
    for (i, si) in s.iter_mut().enumerate() {
        prf_cbd2(&sigma, i as u8, si);
        ntt(si);
        poly_reduce(si);
    }

    // t-hat_i = sum_j A[i][j] * s-hat_j + e-hat_i, A[i][j] = SampleNTT(rho||j||i).
    for i in 0..K {
        acc.fill(0);
        for (jj, sj) in s.iter().enumerate() {
            sample_ntt(&rho, jj as u8, i as u8, &mut a);
            basemul_acc(&mut acc, &a, sj);
        }
        poly_reduce(&mut acc);
        poly_tomont(&mut acc); // cancel the 2^-16 of basemul; |acc| < q
        prf_cbd2(&sigma, (K + i) as u8, &mut e);
        ntt(&mut e);
        poly_reduce(&mut e);
        poly_add(&mut acc, &e); // < 1.5q
        encode12(&acc, &mut tmp, &mut ek[i * POLY_BYTES..(i + 1) * POLY_BYTES]);
    }
    ek[PKE_DK_LEN..].copy_from_slice(&rho);

    // dk_PKE = ByteEncode_12(s-hat).
    for (i, si) in s.iter().enumerate() {
        encode12(si, &mut tmp, &mut dk[i * POLY_BYTES..(i + 1) * POLY_BYTES]);
    }

    // DECLASSIFY: ek is the public encapsulation key (FIPS 203 output that is
    // published). Done after it is complete so that leaks while computing it
    // are still reported; it lets callers branch on ek (e.g. feed it to
    // encaps, whose rejection sampling branches on its rho).
    ct::declassify(&mut ek);

    // dk = dk_PKE || ek || H(ek) || z.
    dk[DK_EK_OFF..DK_H_OFF].copy_from_slice(&ek);
    let hek = h(&ek);
    dk[DK_H_OFF..DK_Z_OFF].copy_from_slice(&hek);
    dk[DK_Z_OFF..].copy_from_slice(z);

    for si in s.iter_mut() {
        ct::zeroize_i16(si);
    }
    ct::zeroize_i16(&mut acc);
    ct::zeroize_i16(&mut e);
    ct::zeroize_i16(&mut a);
    zeroize_u16(&mut tmp);
    ct::zeroize(&mut sigma);

    (ek, dk)
}

/// FIPS 203 §7.2 encapsulation-key modulus check: every ByteDecode_12
/// coefficient of the first 384k bytes must be < q (equivalently,
/// ByteEncode_12(ByteDecode_12(ek)) == ek). Returns all-ones if valid.
/// Evaluated without branches; the caller declassifies the single result.
fn ek_modulus_ok(ek: &[u8; EK_LEN]) -> u32 {
    let mut ok = u32::MAX;
    for c in ek[..PKE_DK_LEN].chunks_exact(3) {
        let d1 = (c[0] as u32) | (((c[1] as u32) & 0x0f) << 8);
        let d2 = ((c[1] as u32) >> 4) | ((c[2] as u32) << 4);
        ok &= ct::mask_lt_u32(d1, Q as u32) & ct::mask_lt_u32(d2, Q as u32);
    }
    ok
}

/// Algorithm 17 Encaps_internal, after the §7.2 encapsulation-key check (modulus check). Returns (ciphertext, shared secret).
///
/// Returns [`Error::InvalidInput`] if `ek` fails the modulus check. `m` is the
/// caller's secret 32-byte randomness; the shared secret is secret and the
/// ciphertext is public.
pub fn encaps_internal(
    ek: &[u8; EK_LEN],
    m: &[u8; 32],
) -> Result<([u8; CT_LEN], [u8; SS_LEN]), Error> {
    // DECLASSIFY: the result of the §7.2 modulus check on the public
    // encapsulation key; whether a key is malformed is public to the caller.
    let ok = ct::declassify_u32(ek_modulus_ok(ek));
    if ok != u32::MAX {
        return Err(Error::InvalidInput);
    }

    let mut rho = [0u8; 32];
    rho.copy_from_slice(&ek[PKE_DK_LEN..]); // public: part of ek

    // (K, r) = G(m || H(ek)).
    let hek = h(ek);
    let mut kr = [0u8; 64];
    g(m, &hek, &mut kr);
    let mut r = [0u8; 32];
    r.copy_from_slice(&kr[32..]);
    let mut ss = [0u8; SS_LEN];
    ss.copy_from_slice(&kr[..32]);

    let mut c = [0u8; CT_LEN];
    pke_encrypt(ek, &rho, m, &r, &mut c);

    // DECLASSIFY: the ciphertext is the public output of encapsulation
    // (FIPS 203 sends it to the other party). Not branched on here; marked so
    // callers may handle it as public data.
    ct::declassify(&mut c);

    ct::zeroize(&mut kr);
    ct::zeroize(&mut r);
    Ok((c, ss))
}

/// Algorithm 18 Decaps_internal, after the §7.3 decapsulation-key hash check.
///
/// Returns [`Error::InvalidInput`] if H(ek) embedded in `dk` does not match the
/// stored hash. Otherwise always returns `Ok`: an invalid ciphertext yields
/// the implicit-rejection key J(z || c), selected without branching.
pub fn decaps(dk: &[u8; DK_LEN], ct: &[u8; CT_LEN]) -> Result<[u8; SS_LEN], Error> {
    let dk_pke = &dk[..PKE_DK_LEN];
    let ek_pke = &dk[DK_EK_OFF..DK_H_OFF];
    let hstored = &dk[DK_H_OFF..DK_Z_OFF];
    let z = &dk[DK_Z_OFF..];

    // §7.3 hash check: H(ek) == h.
    let hek = h(ek_pke);
    // DECLASSIFY: the outcome of the §7.3 decapsulation-key check; a
    // malformed key is public knowledge to the caller (the call fails).
    let ok = ct::declassify_u8(ct::eq(&hek, hstored));
    if ok != 0xff {
        return Err(Error::InvalidInput);
    }

    let mut rho = [0u8; 32];
    rho.copy_from_slice(&ek_pke[PKE_DK_LEN..]);
    // DECLASSIFY: rho is part of the encapsulation key ek embedded in dk,
    // which FIPS 203 makes public. It drives the data-dependent rejection
    // sampling of A in the re-encryption.
    ct::declassify(&mut rho);

    // m' = K-PKE.Decrypt(dk_PKE, c).
    let mut mp = [0u8; 32];
    pke_decrypt(dk_pke, ct, &mut mp);

    // (K', r') = G(m' || h).
    let mut kr = [0u8; 64];
    g(&mp, hstored, &mut kr);
    let mut rp = [0u8; 32];
    rp.copy_from_slice(&kr[32..]);

    // K-bar = J(z || c): the implicit-rejection key, used as the default.
    let mut out = [0u8; SS_LEN];
    j(z, ct, &mut out);

    // c' = K-PKE.Encrypt(ek_PKE, m', r'); secret until compared.
    let mut cp = [0u8; CT_LEN];
    pke_encrypt(ek_pke, &rho, &mp, &rp, &mut cp);

    // If c == c' take K', else keep K-bar. The comparison result stays secret.
    let eq = ct::eq(ct, &cp);
    ct::cmov(&mut out, &kr[..32], eq);

    ct::zeroize(&mut cp);
    ct::zeroize(&mut kr);
    ct::zeroize(&mut rp);
    ct::zeroize(&mut mp);
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compress_exhaustive_matches_definition() {
        // Definition: Compress_d(x) = round_half_up(2^d * x / q) mod 2^d
        //           = floor((2^(d+1) x + q) / (2q)) mod 2^d   (exact rationals).
        for d in [1u32, 4, 5, 10, 11] {
            for x in 0u64..3329 {
                let want = (((x << (d + 1)) + 3329) / (2 * 3329)) % (1 << d);
                assert_eq!(compress(x as u16, d) as u64, want, "d={d} x={x}");
            }
        }
    }

    #[test]
    fn compress_matches_nearest_integer_search() {
        // Independent formulation: the y in [0, 2^d] minimising |y*q - 2^d*x|
        // (no ties since q is odd), taken mod 2^d.
        for d in [1u32, 5, 11] {
            for x in 0i64..3329 {
                let t = (1i64 << d) * x;
                let mut best = 0i64;
                for y in 0..=(1i64 << d) {
                    if (y * 3329 - t).abs() < (best * 3329 - t).abs() {
                        best = y;
                    }
                }
                assert_eq!(compress(x as u16, d) as i64, best % (1 << d), "d={d} x={x}");
            }
        }
    }

    #[test]
    fn decompress_exhaustive_matches_definition() {
        for d in [1u32, 4, 5, 10, 11] {
            for y in 0u64..(1 << d) {
                let want = (2 * 3329 * y + (1 << d)) / (1 << (d + 1));
                assert_eq!(decompress(y as u16, d) as u64, want, "d={d} y={y}");
            }
        }
    }

    #[test]
    fn barrett_all_i16() {
        for a in i16::MIN..=i16::MAX {
            let r = barrett_reduce(a);
            assert!((-1664..=1664).contains(&r), "a={a} r={r}");
            assert_eq!((a as i32 - r as i32).rem_euclid(3329), 0, "a={a}");
            let u = to_unsigned(r);
            assert!(u < 3329);
            assert_eq!((a as i32).rem_euclid(3329), u as i32);
        }
    }

    #[test]
    fn montgomery_range() {
        let lim = 3329i32 << 15;
        let mut x: u64 = 0x1234_5678_9abc_def0;
        for i in 0..2_000_000u32 {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            let a = match i {
                0 => lim - 1,
                1 => -lim,
                _ => ((x % (2 * lim as u64)) as i64 - lim as i64) as i32,
            };
            let r = mont_reduce(a) as i64;
            assert!(r.abs() < 3329, "a={a} r={r}");
            assert_eq!((r * 65536 - a as i64).rem_euclid(3329), 0);
        }
    }

    #[test]
    fn zetas_match_reference_table() {
        // First entries of the pq-crystals reference table.
        assert_eq!(&ZETAS[..8], &[-1044, -758, -359, -1517, 1493, 1422, 287, 202]);
        assert_eq!(ZETAS[127], 1628);
    }

    fn lcg(seed: &mut u64) -> u64 {
        *seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        *seed >> 33
    }

    #[test]
    fn ntt_multiplication_is_negacyclic_product() {
        let mut seed = 7u64;
        for _ in 0..50 {
            let mut a = [0i16; N];
            let mut b = [0i16; N];
            for i in 0..N {
                a[i] = (lcg(&mut seed) % 3329) as i16 - 1664;
                b[i] = (lcg(&mut seed) % 5) as i16 - 2;
            }
            // schoolbook in Z_q[X]/(X^256+1)
            let mut want = [0i64; N];
            for i in 0..N {
                for k in 0..N {
                    let p = a[i] as i64 * b[k] as i64;
                    if i + k < N {
                        want[i + k] += p;
                    } else {
                        want[i + k - N] -= p;
                    }
                }
            }
            let (mut ah, mut bh) = (a, b);
            ntt(&mut ah);
            poly_reduce(&mut ah);
            ntt(&mut bh);
            poly_reduce(&mut bh);
            let mut r = [0i16; N];
            basemul_acc(&mut r, &ah, &bh);
            poly_reduce(&mut r);
            invntt(&mut r);
            for i in 0..N {
                assert_eq!((r[i] as i64 - want[i]).rem_euclid(3329), 0, "i={i}");
            }
        }
    }

    #[test]
    fn pack_unpack_roundtrip() {
        let mut seed = 99u64;
        for d in [1u32, 5, 11, 12] {
            let mut v = [0u16; N];
            for x in v.iter_mut() {
                *x = (lcg(&mut seed) & ((1 << d) - 1)) as u16;
            }
            let mut buf = [0u8; 384];
            pack(&v, d, &mut buf[..32 * d as usize]);
            let mut w = [0u16; N];
            unpack(&buf[..32 * d as usize], d, &mut w);
            assert_eq!(v, w);
        }
    }
}

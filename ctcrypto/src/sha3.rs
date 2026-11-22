//! Keccak-f[1600], SHA3-256, SHA3-512, SHAKE128 and SHAKE256 (FIPS 202).
//! The permutation uses only XOR, AND, NOT and rotations, so it is constant
//! time in the state. Input and output lengths are treated as public.

#[path = "sha3_consts.rs"]
mod consts;
use consts::RC;

use crate::ct;

const RHO: [u32; 24] = [
    1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14, 27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44,
];
const PI: [usize; 24] = [
    10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4, 15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1,
];

/// The Keccak-f[1600] permutation.
pub fn keccak_f1600(a: &mut [u64; 25]) {
    for rc in RC.iter() {
        let mut c = [0u64; 5];
        for x in 0..5 {
            c[x] = a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20];
        }
        for x in 0..5 {
            let d = c[(x + 4) % 5] ^ c[(x + 1) % 5].rotate_left(1);
            for y in 0..5 {
                a[x + 5 * y] ^= d;
            }
        }
        let mut last = a[1];
        for i in 0..24 {
            let j = PI[i];
            let t = a[j];
            a[j] = last.rotate_left(RHO[i]);
            last = t;
        }
        for y in 0..5 {
            let mut row = [0u64; 5];
            row.copy_from_slice(&a[5 * y..5 * y + 5]);
            for x in 0..5 {
                a[5 * y + x] = row[x] ^ (!row[(x + 1) % 5] & row[(x + 2) % 5]);
            }
        }
        a[0] ^= *rc;
    }
}

/// A Keccak sponge with a fixed rate and domain-separation byte. Absorb with
/// [`Sponge::absorb`], then read with [`Sponge::squeeze`]; the first squeeze
/// pads and switches the sponge to output mode.
#[derive(Clone)]
pub struct Sponge {
    state: [u64; 25],
    rate: usize,
    pos: usize,
    ds: u8,
    squeezing: bool,
}

impl Sponge {
    fn with(rate: usize, ds: u8) -> Self {
        Self { state: [0; 25], rate, pos: 0, ds, squeezing: false }
    }

    /// SHAKE128 (rate 168 bytes).
    pub fn shake128() -> Self {
        Self::with(168, 0x1f)
    }

    /// SHAKE256 (rate 136 bytes).
    pub fn shake256() -> Self {
        Self::with(136, 0x1f)
    }

    /// SHA3-256 (read exactly 32 bytes).
    pub fn sha3_256() -> Self {
        Self::with(136, 0x06)
    }

    /// SHA3-512 (read exactly 64 bytes).
    pub fn sha3_512() -> Self {
        Self::with(72, 0x06)
    }

    #[inline]
    fn xor_byte(&mut self, i: usize, b: u8) {
        self.state[i / 8] ^= (b as u64) << (8 * (i % 8));
    }

    /// Absorbs `data`. Panics if called after squeezing started.
    pub fn absorb(&mut self, data: &[u8]) {
        assert!(!self.squeezing, "absorb after squeeze");
        for &b in data {
            self.xor_byte(self.pos, b);
            self.pos += 1;
            if self.pos == self.rate {
                keccak_f1600(&mut self.state);
                self.pos = 0;
            }
        }
    }

    fn pad(&mut self) {
        self.xor_byte(self.pos, self.ds);
        self.xor_byte(self.rate - 1, 0x80);
        keccak_f1600(&mut self.state);
        self.pos = 0;
        self.squeezing = true;
    }

    /// Writes the next `out.len()` output bytes.
    pub fn squeeze(&mut self, out: &mut [u8]) {
        if !self.squeezing {
            self.pad();
        }
        for o in out.iter_mut() {
            if self.pos == self.rate {
                keccak_f1600(&mut self.state);
                self.pos = 0;
            }
            *o = (self.state[self.pos / 8] >> (8 * (self.pos % 8))) as u8;
            self.pos += 1;
        }
    }
}

impl Drop for Sponge {
    fn drop(&mut self) {
        ct::zeroize_u64(&mut self.state);
    }
}

/// One-shot SHA3-256.
pub fn sha3_256(data: &[u8]) -> [u8; 32] {
    let mut s = Sponge::sha3_256();
    s.absorb(data);
    let mut out = [0u8; 32];
    s.squeeze(&mut out);
    out
}

/// One-shot SHA3-512.
pub fn sha3_512(data: &[u8]) -> [u8; 64] {
    let mut s = Sponge::sha3_512();
    s.absorb(data);
    let mut out = [0u8; 64];
    s.squeeze(&mut out);
    out
}

/// One-shot SHAKE128 into `out`.
pub fn shake128(data: &[u8], out: &mut [u8]) {
    let mut s = Sponge::shake128();
    s.absorb(data);
    s.squeeze(out);
}

/// One-shot SHAKE256 into `out`.
pub fn shake256(data: &[u8], out: &mut [u8]) {
    let mut s = Sponge::shake256();
    s.absorb(data);
    s.squeeze(out);
}

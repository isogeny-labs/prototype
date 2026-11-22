//! SHA-256, SHA-384 and SHA-512 (FIPS 180-4). The compression functions use
//! only additions, rotations and boolean operations, so they are constant time
//! in the message. Message length is treated as public.

#[path = "sha2_consts.rs"]
mod consts;
use consts::{IV256, IV384, IV512, K256, K512};

use crate::ct;

fn compress256(state: &mut [u32; 8], block: &[u8]) {
    let mut w = [0u32; 64];
    for (i, c) in block.chunks_exact(4).enumerate() {
        w[i] = u32::from_be_bytes([c[0], c[1], c[2], c[3]]);
    }
    for i in 16..64 {
        let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
        let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16].wrapping_add(s0).wrapping_add(w[i - 7]).wrapping_add(s1);
    }
    let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut h] = *state;
    for i in 0..64 {
        let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
        let ch = (e & f) ^ (!e & g);
        let t1 = h.wrapping_add(s1).wrapping_add(ch).wrapping_add(K256[i]).wrapping_add(w[i]);
        let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
        let maj = (a & b) ^ (a & c) ^ (b & c);
        let t2 = s0.wrapping_add(maj);
        h = g;
        g = f;
        f = e;
        e = d.wrapping_add(t1);
        d = c;
        c = b;
        b = a;
        a = t1.wrapping_add(t2);
    }
    for (s, v) in state.iter_mut().zip([a, b, c, d, e, f, g, h]) {
        *s = s.wrapping_add(v);
    }
    ct::zeroize_u32(&mut w);
}

fn compress512(state: &mut [u64; 8], block: &[u8]) {
    let mut w = [0u64; 80];
    for (i, c) in block.chunks_exact(8).enumerate() {
        w[i] = u64::from_be_bytes([c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7]]);
    }
    for i in 16..80 {
        let s0 = w[i - 15].rotate_right(1) ^ w[i - 15].rotate_right(8) ^ (w[i - 15] >> 7);
        let s1 = w[i - 2].rotate_right(19) ^ w[i - 2].rotate_right(61) ^ (w[i - 2] >> 6);
        w[i] = w[i - 16].wrapping_add(s0).wrapping_add(w[i - 7]).wrapping_add(s1);
    }
    let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut h] = *state;
    for i in 0..80 {
        let s1 = e.rotate_right(14) ^ e.rotate_right(18) ^ e.rotate_right(41);
        let ch = (e & f) ^ (!e & g);
        let t1 = h.wrapping_add(s1).wrapping_add(ch).wrapping_add(K512[i]).wrapping_add(w[i]);
        let s0 = a.rotate_right(28) ^ a.rotate_right(34) ^ a.rotate_right(39);
        let maj = (a & b) ^ (a & c) ^ (b & c);
        let t2 = s0.wrapping_add(maj);
        h = g;
        g = f;
        f = e;
        e = d.wrapping_add(t1);
        d = c;
        c = b;
        b = a;
        a = t1.wrapping_add(t2);
    }
    for (s, v) in state.iter_mut().zip([a, b, c, d, e, f, g, h]) {
        *s = s.wrapping_add(v);
    }
    ct::zeroize_u64(&mut w);
}

/// Incremental SHA-256.
#[derive(Clone)]
pub struct Sha256 {
    state: [u32; 8],
    buf: [u8; 64],
    pos: usize,
    len: u64,
}

impl Default for Sha256 {
    fn default() -> Self {
        Self::new()
    }
}

impl Sha256 {
    /// Output length in bytes.
    pub const OUTPUT_LEN: usize = 32;

    /// Creates an empty hash state.
    pub fn new() -> Self {
        Self { state: IV256, buf: [0; 64], pos: 0, len: 0 }
    }

    /// Absorbs `data`.
    pub fn update(&mut self, mut data: &[u8]) {
        self.len = self.len.wrapping_add(data.len() as u64);
        if self.pos > 0 {
            let take = core::cmp::min(64 - self.pos, data.len());
            self.buf[self.pos..self.pos + take].copy_from_slice(&data[..take]);
            self.pos += take;
            data = &data[take..];
            if self.pos < 64 {
                return;
            }
            let buf = self.buf;
            compress256(&mut self.state, &buf);
            self.pos = 0;
        }
        let mut chunks = data.chunks_exact(64);
        for block in &mut chunks {
            compress256(&mut self.state, block);
        }
        let rem = chunks.remainder();
        self.buf[..rem.len()].copy_from_slice(rem);
        self.pos = rem.len();
    }

    /// Finishes and returns the digest.
    pub fn finalize(mut self) -> [u8; 32] {
        let bits = self.len.wrapping_mul(8);
        self.buf[self.pos] = 0x80;
        self.buf[self.pos + 1..].fill(0);
        if self.pos + 1 > 56 {
            let buf = self.buf;
            compress256(&mut self.state, &buf);
            self.buf.fill(0);
        }
        self.buf[56..].copy_from_slice(&bits.to_be_bytes());
        let buf = self.buf;
        compress256(&mut self.state, &buf);
        let mut out = [0u8; 32];
        for (o, s) in out.chunks_exact_mut(4).zip(self.state.iter()) {
            o.copy_from_slice(&s.to_be_bytes());
        }
        out
    }

    /// One-shot digest.
    pub fn digest(data: &[u8]) -> [u8; 32] {
        let mut h = Self::new();
        h.update(data);
        h.finalize()
    }
}

impl Drop for Sha256 {
    fn drop(&mut self) {
        ct::zeroize_u32(&mut self.state);
        ct::zeroize(&mut self.buf);
    }
}

#[derive(Clone)]
struct Core512 {
    state: [u64; 8],
    buf: [u8; 128],
    pos: usize,
    len: u128,
}

impl Core512 {
    fn new(iv: [u64; 8]) -> Self {
        Self { state: iv, buf: [0; 128], pos: 0, len: 0 }
    }

    fn update(&mut self, mut data: &[u8]) {
        self.len = self.len.wrapping_add(data.len() as u128);
        if self.pos > 0 {
            let take = core::cmp::min(128 - self.pos, data.len());
            self.buf[self.pos..self.pos + take].copy_from_slice(&data[..take]);
            self.pos += take;
            data = &data[take..];
            if self.pos < 128 {
                return;
            }
            let buf = self.buf;
            compress512(&mut self.state, &buf);
            self.pos = 0;
        }
        let mut chunks = data.chunks_exact(128);
        for block in &mut chunks {
            compress512(&mut self.state, block);
        }
        let rem = chunks.remainder();
        self.buf[..rem.len()].copy_from_slice(rem);
        self.pos = rem.len();
    }

    fn finalize(&mut self) -> [u8; 64] {
        let bits = self.len.wrapping_mul(8);
        self.buf[self.pos] = 0x80;
        self.buf[self.pos + 1..].fill(0);
        if self.pos + 1 > 112 {
            let buf = self.buf;
            compress512(&mut self.state, &buf);
            self.buf.fill(0);
        }
        self.buf[112..].copy_from_slice(&bits.to_be_bytes());
        let buf = self.buf;
        compress512(&mut self.state, &buf);
        let mut out = [0u8; 64];
        for (o, s) in out.chunks_exact_mut(8).zip(self.state.iter()) {
            o.copy_from_slice(&s.to_be_bytes());
        }
        out
    }
}

impl Drop for Core512 {
    fn drop(&mut self) {
        ct::zeroize_u64(&mut self.state);
        ct::zeroize(&mut self.buf);
    }
}

/// Incremental SHA-512.
#[derive(Clone)]
pub struct Sha512(Core512);

impl Default for Sha512 {
    fn default() -> Self {
        Self::new()
    }
}

impl Sha512 {
    /// Output length in bytes.
    pub const OUTPUT_LEN: usize = 64;

    /// Creates an empty hash state.
    pub fn new() -> Self {
        Self(Core512::new(IV512))
    }

    /// Absorbs `data`.
    pub fn update(&mut self, data: &[u8]) {
        self.0.update(data);
    }

    /// Finishes and returns the digest.
    pub fn finalize(mut self) -> [u8; 64] {
        self.0.finalize()
    }

    /// One-shot digest.
    pub fn digest(data: &[u8]) -> [u8; 64] {
        let mut h = Self::new();
        h.update(data);
        h.finalize()
    }
}

/// Incremental SHA-384.
#[derive(Clone)]
pub struct Sha384(Core512);

impl Default for Sha384 {
    fn default() -> Self {
        Self::new()
    }
}

impl Sha384 {
    /// Output length in bytes.
    pub const OUTPUT_LEN: usize = 48;

    /// Creates an empty hash state.
    pub fn new() -> Self {
        Self(Core512::new(IV384))
    }

    /// Absorbs `data`.
    pub fn update(&mut self, data: &[u8]) {
        self.0.update(data);
    }

    /// Finishes and returns the digest.
    pub fn finalize(mut self) -> [u8; 48] {
        let mut full = self.0.finalize();
        let mut out = [0u8; 48];
        out.copy_from_slice(&full[..48]);
        ct::zeroize(&mut full);
        out
    }

    /// One-shot digest.
    pub fn digest(data: &[u8]) -> [u8; 48] {
        let mut h = Self::new();
        h.update(data);
        h.finalize()
    }
}

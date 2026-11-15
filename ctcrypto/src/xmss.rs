//! XMSS and XMSS^MT signature verification (RFC 8391, NIST SP 800-208).
//!
//! Verification only: there is no key generation or signing here. All inputs
//! are treated as public and possibly hostile, so every length is validated
//! against the parameter set before use and nothing allocates (the largest
//! working buffer is the 67-element WOTS+ public key, 2144 bytes).
//!
//! Supported parameter sets are the ones SP 800-208 approves, with the OIDs
//! from RFC 8391 (SHA2_*_256) and SP 800-208 Section 5 (the rest):
//!
//! | Hash          | XMSS OIDs (h = 10, 16, 20) | XMSS^MT OIDs                       |
//! |---------------|----------------------------|------------------------------------|
//! | SHA-256       | `0x01..0x03`               | `0x01..0x08`                       |
//! | SHA-256/192   | `0x0D..0x0F`               | `0x21..0x28`                       |
//! | SHAKE256/256  | `0x10..0x12`               | `0x29..0x30`                       |
//! | SHAKE256/192  | `0x13..0x15`               | `0x31..0x38`                       |
//!
//! The XMSS^MT parameter sets in each group are, in order, `h/d` = 20/2, 20/4,
//! 40/2, 40/4, 40/8, 60/3, 60/6, 60/12. The SHA-512, SHAKE128 and SHAKE256/512
//! sets of RFC 8391 are not approved by SP 800-208 and return
//! [`Error::Unsupported`].
//!
//! For the 192-bit sets `padding_len` is 4 bytes; for the 256-bit sets it is 32
//! (SP 800-208 Section 5).

use crate::ct;
use crate::sha2::Sha256;
use crate::sha3::Sponge;
use crate::Error;

/// Largest `n` of any supported parameter set.
const MAX_N: usize = 32;
/// Largest WOTS+ `len` of any supported parameter set (n = 32).
const MAX_LEN: usize = 67;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Family {
    Sha256,
    Shake256,
}

#[derive(Clone, Copy)]
struct Params {
    family: Family,
    /// Hash output size in bytes.
    n: usize,
    /// Length of the domain-separation prefix `toByte(x, padding_len)`.
    pad: usize,
    /// WOTS+ chain count `len1 + len2` (w = 16).
    len: usize,
    /// Total tree height.
    h: u32,
    /// Number of layers (1 for plain XMSS).
    d: u32,
}

impl Params {
    fn new(family: Family, n: usize, h: u32, d: u32) -> Self {
        let (pad, len) = if n == 32 { (32, 67) } else { (4, 51) };
        Params { family, n, pad, len, h, d }
    }
}

/// Parameter set for an XMSS OID, or `None` if unknown or not approved.
fn xmss_params(oid: u32) -> Option<Params> {
    let height = |k: u32| match k {
        0 => 10,
        1 => 16,
        _ => 20,
    };
    match oid {
        0x01..=0x03 => Some(Params::new(Family::Sha256, 32, height(oid - 0x01), 1)),
        0x0d..=0x0f => Some(Params::new(Family::Sha256, 24, height(oid - 0x0d), 1)),
        0x10..=0x12 => Some(Params::new(Family::Shake256, 32, height(oid - 0x10), 1)),
        0x13..=0x15 => Some(Params::new(Family::Shake256, 24, height(oid - 0x13), 1)),
        _ => None,
    }
}

/// Parameter set for an XMSS^MT OID, or `None` if unknown or not approved.
fn xmssmt_params(oid: u32) -> Option<Params> {
    // (h, d) in OID order within each group of eight.
    const HD: [(u32, u32); 8] = [(20, 2), (20, 4), (40, 2), (40, 4), (40, 8), (60, 3), (60, 6), (60, 12)];
    let (family, n, base) = match oid {
        0x01..=0x08 => (Family::Sha256, 32, 0x01),
        0x21..=0x28 => (Family::Sha256, 24, 0x21),
        0x29..=0x30 => (Family::Shake256, 32, 0x29),
        0x31..=0x38 => (Family::Shake256, 24, 0x31),
        _ => return None,
    };
    let (h, d) = *HD.get((oid - base) as usize)?;
    Some(Params::new(family, n, h, d))
}

/// Incremental hash; the output is truncated to `n` bytes.
enum Hasher {
    Sha(Sha256),
    Shake(Sponge),
}

impl Hasher {
    fn new(family: Family) -> Self {
        match family {
            Family::Sha256 => Hasher::Sha(Sha256::new()),
            Family::Shake256 => Hasher::Shake(Sponge::shake256()),
        }
    }

    fn update(&mut self, data: &[u8]) {
        match self {
            Hasher::Sha(h) => h.update(data),
            Hasher::Shake(s) => s.absorb(data),
        }
    }

    fn finish(self, n: usize) -> [u8; MAX_N] {
        let mut out = [0u8; MAX_N];
        let n = n.min(MAX_N);
        match self {
            Hasher::Sha(h) => out[..n].copy_from_slice(&h.finalize()[..n]),
            Hasher::Shake(mut s) => s.squeeze(&mut out[..n]),
        }
        out
    }
}

/// `T(toByte(tag, padding_len) || parts...)`, the shape of F, H, H_msg and PRF.
fn hash_tagged(p: &Params, tag: u8, parts: &[&[u8]]) -> [u8; MAX_N] {
    let mut h = Hasher::new(p.family);
    let mut pad = [0u8; MAX_N];
    pad[p.pad - 1] = tag;
    h.update(&pad[..p.pad]);
    for part in parts {
        h.update(part);
    }
    h.finish(p.n)
}

const TAG_F: u8 = 0;
const TAG_H: u8 = 1;
const TAG_HMSG: u8 = 2;
const TAG_PRF: u8 = 3;

const ADRS_OTS: u32 = 0;
const ADRS_LTREE: u32 = 1;
const ADRS_HASH_TREE: u32 = 2;

/// An RFC 8391 Section 2.5 address: eight big-endian 32-bit words.
#[derive(Clone, Copy)]
struct Adrs([u32; 8]);

impl Adrs {
    fn set_layer(&mut self, v: u32) {
        self.0[0] = v;
    }
    fn set_tree(&mut self, v: u64) {
        self.0[1] = (v >> 32) as u32;
        self.0[2] = v as u32;
    }
    /// Setting the type clears the three type-specific words and keyAndMask.
    fn set_type(&mut self, v: u32) {
        self.0[3] = v;
        self.0[4] = 0;
        self.0[5] = 0;
        self.0[6] = 0;
        self.0[7] = 0;
    }
    /// OTS address / L-tree address / (padding for hash-tree addresses).
    fn set_word4(&mut self, v: u32) {
        self.0[4] = v;
    }
    /// Chain address (OTS) / tree height (L-tree and hash tree).
    fn set_word5(&mut self, v: u32) {
        self.0[5] = v;
    }
    /// Hash address (OTS) / tree index (L-tree and hash tree).
    fn set_word6(&mut self, v: u32) {
        self.0[6] = v;
    }
    fn set_key_and_mask(&mut self, v: u32) {
        self.0[7] = v;
    }
    fn bytes(&self) -> [u8; 32] {
        let mut out = [0u8; 32];
        for (o, w) in out.chunks_exact_mut(4).zip(self.0.iter()) {
            o.copy_from_slice(&w.to_be_bytes());
        }
        out
    }
}

/// `PRF(SEED, ADRS)` with the given keyAndMask value.
fn prf(p: &Params, seed: &[u8], adrs: &mut Adrs, key_and_mask: u32) -> [u8; MAX_N] {
    adrs.set_key_and_mask(key_and_mask);
    hash_tagged(p, TAG_PRF, &[seed, &adrs.bytes()])
}

/// `RAND_HASH(LEFT, RIGHT, SEED, ADRS)` (RFC 8391 Algorithm 7).
fn rand_hash(p: &Params, left: &[u8], right: &[u8], seed: &[u8], adrs: &mut Adrs) -> [u8; MAX_N] {
    let n = p.n;
    let key = prf(p, seed, adrs, 0);
    let bm0 = prf(p, seed, adrs, 1);
    let bm1 = prf(p, seed, adrs, 2);
    let mut buf = [0u8; 2 * MAX_N];
    for k in 0..n {
        buf[k] = left.get(k).copied().unwrap_or(0) ^ bm0[k];
        buf[n + k] = right.get(k).copied().unwrap_or(0) ^ bm1[k];
    }
    hash_tagged(p, TAG_H, &[&key[..n], &buf[..2 * n]])
}

/// One WOTS+ chain, `steps` applications of F starting at position `start`
/// (RFC 8391 Algorithm 2). Requires `start + steps <= 15`.
fn chain(p: &Params, x: &mut [u8; MAX_N], start: u32, steps: u32, seed: &[u8], adrs: &mut Adrs) {
    let n = p.n;
    for j in start..start + steps {
        adrs.set_word6(j);
        let key = prf(p, seed, adrs, 0);
        let bm = prf(p, seed, adrs, 1);
        let mut masked = [0u8; MAX_N];
        for k in 0..n {
            masked[k] = x[k] ^ bm[k];
        }
        *x = hash_tagged(p, TAG_F, &[&key[..n], &masked[..n]]);
    }
}

/// Base-16 digits of the n-byte message followed by the 3-digit checksum
/// (RFC 8391 Algorithm 1 and Section 3.1.5), `len` digits in total.
fn wots_digits(p: &Params, msg: &[u8]) -> [u8; MAX_LEN] {
    let mut d = [0u8; MAX_LEN];
    let len1 = 2 * p.n;
    let mut csum: u32 = 0;
    for (k, b) in msg.iter().take(p.n).enumerate() {
        d[2 * k] = b >> 4;
        d[2 * k + 1] = b & 15;
    }
    for &x in d.iter().take(len1) {
        csum += 15 - u32::from(x);
    }
    // len2 = 3 digits = 12 bits, so csum is shifted left by 4 and stored in
    // two bytes; the first three nibbles are the checksum digits.
    let cs = ((csum << 4) & 0xffff) as u16;
    d[len1] = ((cs >> 12) & 15) as u8;
    d[len1 + 1] = ((cs >> 8) & 15) as u8;
    d[len1 + 2] = ((cs >> 4) & 15) as u8;
    d
}

/// `XMSS_rootFromSig` (RFC 8391 Algorithm 13) for one tree of height `th`.
/// `adrs` has its layer and tree address set. `sig` is the WOTS+ signature
/// followed by the authentication path (`(len + th) * n` bytes); `msg` is the
/// n-byte value being signed (message digest or root of the layer below).
fn root_from_sig(
    p: &Params,
    th: u32,
    idx: u32,
    sig: &[u8],
    msg: &[u8],
    seed: &[u8],
    adrs: &mut Adrs,
) -> [u8; MAX_N] {
    let n = p.n;
    let len = p.len;
    let (wots_sig, auth) = sig.split_at(len * n);

    // WOTS+ public key from signature (Algorithm 6).
    adrs.set_type(ADRS_OTS);
    adrs.set_word4(idx);
    let digits = wots_digits(p, msg);
    let mut pk = [[0u8; MAX_N]; MAX_LEN];
    for (i, (slot, s)) in pk.iter_mut().zip(wots_sig.chunks_exact(n)).take(len).enumerate() {
        slot[..n].copy_from_slice(s);
        adrs.set_word5(i as u32);
        let start = u32::from(digits[i]);
        chain(p, slot, start, 15 - start, seed, adrs);
    }

    // L-tree (Algorithm 8).
    adrs.set_type(ADRS_LTREE);
    adrs.set_word4(idx);
    let mut cur = len;
    let mut height = 0u32;
    while cur > 1 {
        adrs.set_word5(height);
        for i in 0..cur / 2 {
            adrs.set_word6(i as u32);
            let r = rand_hash(p, &pk[2 * i][..n], &pk[2 * i + 1][..n], seed, adrs);
            pk[i] = r;
        }
        if cur % 2 == 1 {
            pk[cur / 2] = pk[cur - 1];
        }
        cur = cur.div_ceil(2);
        height += 1;
    }
    let mut node = pk[0];

    // Authentication path to the root of the tree.
    adrs.set_type(ADRS_HASH_TREE);
    adrs.set_word6(idx);
    let mut tree_index = idx;
    for (k, a) in auth.chunks_exact(n).take(th as usize).enumerate() {
        adrs.set_word5(k as u32);
        if (idx >> k) & 1 == 0 {
            tree_index /= 2;
            adrs.set_word6(tree_index);
            node = rand_hash(p, &node[..n], a, seed, adrs);
        } else {
            tree_index = (tree_index - 1) / 2;
            adrs.set_word6(tree_index);
            node = rand_hash(p, a, &node[..n], seed, adrs);
        }
    }
    node
}

/// Big-endian integer from at most eight bytes.
fn be_u64(b: &[u8]) -> u64 {
    b.iter().fold(0u64, |a, &x| (a << 8) | u64::from(x))
}

/// Common front end: parses the public key (`OID || root || SEED`).
fn split_public_key(p: &Params, public_key: &[u8]) -> Result<(), Error> {
    if public_key.len() != 4 + 2 * p.n {
        return Err(Error::InvalidInput);
    }
    Ok(())
}

/// `M' = H_msg(r || root || toByte(idx, n), M)`.
fn message_digest(p: &Params, r: &[u8], root: &[u8], idx: u64, msg: &[u8]) -> [u8; MAX_N] {
    // toByte(idx, n): big-endian, zero-padded on the left to n bytes.
    let mut idx_bytes = [0u8; MAX_N];
    idx_bytes[p.n - 8..p.n].copy_from_slice(&idx.to_be_bytes());
    hash_tagged(p, TAG_HMSG, &[r, root, &idx_bytes[..p.n], msg])
}

fn finish(computed: &[u8], root: &[u8]) -> Result<(), Error> {
    if ct::eq(computed, root) == 0xff {
        Ok(())
    } else {
        Err(Error::VerificationFailed)
    }
}

/// Verifies an XMSS signature (RFC 8391 §4.1.10). public_key = 4-byte OID || root || SEED.
///
/// `signature` is `u32 idx_sig || r[n] || WOTS+ signature[len * n] ||
/// auth[h * n]`. Returns `Err(Error::Unsupported)` for an unknown OID or one
/// of the RFC 8391 parameter sets that SP 800-208 does not approve,
/// `Err(Error::InvalidInput)` for wrong lengths or an out-of-range index, and
/// `Err(Error::VerificationFailed)` for a well-formed signature that does not
/// verify.
pub fn verify(public_key: &[u8], msg: &[u8], signature: &[u8]) -> Result<(), Error> {
    let oid = public_key
        .get(..4)
        .map(|b| be_u64(b) as u32)
        .ok_or(Error::InvalidInput)?;
    let p = xmss_params(oid).ok_or(Error::Unsupported)?;
    split_public_key(&p, public_key)?;
    let n = p.n;
    let root = &public_key[4..4 + n];
    let seed = &public_key[4 + n..];

    if signature.len() != 4 + n + (p.len + p.h as usize) * n {
        return Err(Error::InvalidInput);
    }
    let idx = be_u64(&signature[..4]);
    if idx >= 1u64 << p.h {
        return Err(Error::InvalidInput);
    }
    let r = &signature[4..4 + n];
    let body = &signature[4 + n..];

    let digest = message_digest(&p, r, root, idx, msg);
    let mut adrs = Adrs([0; 8]);
    let computed = root_from_sig(&p, p.h, idx as u32, body, &digest[..n], seed, &mut adrs);
    finish(&computed[..n], root)
}

/// Verifies an XMSS^MT signature (RFC 8391 §4.2.5). public_key = 4-byte OID || root || SEED.
///
/// `signature` is `idx_sig[ceil(h/8)] || r[n] || d * (WOTS+ signature[len * n]
/// || auth[(h/d) * n])`. Errors are as for [`verify`].
pub fn verify_mt(public_key: &[u8], msg: &[u8], signature: &[u8]) -> Result<(), Error> {
    let oid = public_key
        .get(..4)
        .map(|b| be_u64(b) as u32)
        .ok_or(Error::InvalidInput)?;
    let p = xmssmt_params(oid).ok_or(Error::Unsupported)?;
    split_public_key(&p, public_key)?;
    let n = p.n;
    let root = &public_key[4..4 + n];
    let seed = &public_key[4 + n..];

    let th = p.h / p.d; // height of each subtree (5, 10 or 20)
    let idx_len = p.h.div_ceil(8) as usize;
    let layer_len = (p.len + th as usize) * n;
    if signature.len() != idx_len + n + p.d as usize * layer_len {
        return Err(Error::InvalidInput);
    }
    let idx = be_u64(&signature[..idx_len]);
    if idx >= 1u64 << p.h {
        return Err(Error::InvalidInput);
    }
    let r = &signature[idx_len..idx_len + n];
    let layers = &signature[idx_len + n..];

    let mut node = message_digest(&p, r, root, idx, msg);
    let mut idx_tree = idx;
    let mask = (1u64 << th) - 1;
    for (j, layer) in layers.chunks_exact(layer_len).take(p.d as usize).enumerate() {
        let idx_leaf = (idx_tree & mask) as u32;
        idx_tree >>= th;
        let mut adrs = Adrs([0; 8]);
        adrs.set_layer(j as u32);
        adrs.set_tree(idx_tree);
        node = root_from_sig(&p, th, idx_leaf, layer, &node[..n], seed, &mut adrs);
    }
    finish(&node[..n], root)
}

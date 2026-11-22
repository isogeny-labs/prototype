//! LMS / HSS signature verification (RFC 8554, NIST SP 800-208, RFC 9858).
//!
//! Verification only: there is no key generation or signing here. All inputs
//! (public key, message, signature) are treated as public and possibly
//! hostile, so every length is validated against the parameter set before it
//! is used and nothing allocates: the largest working buffer is a 34-byte
//! checksummed digest.
//!
//! Supported parameter sets (type codes from RFC 8554 and the IANA "Leighton-
//! Micali Signatures" registry, RFC 9858):
//!
//! | Hash          | LM-OTS `W1..W8` | LMS `H5..H25`        |
//! |---------------|-----------------|----------------------|
//! | SHA-256 (n32) | `0x01..0x04`    | `0x05..0x09` (M32)   |
//! | SHA-256/192   | `0x05..0x08`    | `0x0A..0x0E` (M24)   |
//! | SHAKE256/256  | `0x09..0x0C`    | `0x0F..0x13` (M32)   |
//! | SHAKE256/192  | `0x0D..0x10`    | `0x14..0x18` (M24)   |
//!
//! HSS supports 1 to 8 levels. Each level is verified with its own parameter
//! set, as RFC 8554 Section 6.3 allows.

use crate::ct;
use crate::sha2::Sha256;
use crate::sha3::Sponge;
use crate::Error;

/// Largest hash output (`n` / `m`) of any supported parameter set.
const MAX_N: usize = 32;
/// Size of the I (key pair identifier) field.
const I_LEN: usize = 16;
/// Maximum number of HSS levels.
const MAX_LEVELS: u32 = 8;

const D_PBLC: u16 = 0x8080;
const D_MESG: u16 = 0x8181;
const D_LEAF: u16 = 0x8282;
const D_INTR: u16 = 0x8383;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Family {
    Sha256,
    Shake256,
}

/// LM-OTS parameters (RFC 8554 Section 4.1, SP 800-208 Section 4).
#[derive(Clone, Copy)]
struct OtsParams {
    family: Family,
    n: usize,
    /// Winternitz width in bits.
    w: u32,
    p: usize,
    ls: u32,
}

/// LMS parameters (RFC 8554 Section 5.1, SP 800-208 Section 4).
#[derive(Clone, Copy)]
struct LmsParams {
    family: Family,
    m: usize,
    h: u32,
}

fn ots_params(code: u32) -> Option<OtsParams> {
    // (code - 1) / 4 selects family and n; (code - 1) % 4 selects W in {1,2,4,8}.
    if !(1..=16).contains(&code) {
        return None;
    }
    let c = code - 1;
    let (family, n) = match c / 4 {
        0 => (Family::Sha256, 32),
        1 => (Family::Sha256, 24),
        2 => (Family::Shake256, 32),
        _ => (Family::Shake256, 24),
    };
    let (w, p, ls) = match (n, c % 4) {
        (32, 0) => (1, 265, 7),
        (32, 1) => (2, 133, 6),
        (32, 2) => (4, 67, 4),
        (32, _) => (8, 34, 0),
        (_, 0) => (1, 200, 8),
        (_, 1) => (2, 101, 6),
        (_, 2) => (4, 51, 4),
        (_, _) => (8, 26, 0),
    };
    Some(OtsParams { family, n, w, p, ls })
}

fn lms_params(code: u32) -> Option<LmsParams> {
    if !(5..=0x18).contains(&code) {
        return None;
    }
    let c = code - 5;
    let (family, m) = match c / 5 {
        0 => (Family::Sha256, 32),
        1 => (Family::Sha256, 24),
        2 => (Family::Shake256, 32),
        _ => (Family::Shake256, 24),
    };
    Some(LmsParams { family, m, h: 5 * (c % 5 + 1) })
}

/// Incremental hash with the output truncated to `n` bytes.
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

    /// Returns the digest in the first `n` bytes (`n <= 32`); the rest is zero.
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

/// Starts a hash over `I || u32str(q) || u16str(tag)`, the common prefix of
/// every hash input in LMS and LM-OTS (except the leaf/interior ones, which use
/// the node number in place of `q`).
fn prefixed(family: Family, i: &[u8], q: u32, tag: u16) -> Hasher {
    let mut h = Hasher::new(family);
    h.update(i);
    h.update(&q.to_be_bytes());
    h.update(&tag.to_be_bytes());
    h
}

fn be32(b: &[u8]) -> Option<u32> {
    let a: [u8; 4] = b.get(..4)?.try_into().ok()?;
    Some(u32::from_be_bytes(a))
}

/// `coef(S, i, w)` of RFC 8554 Section 3.1.3 for `w` in {1, 2, 4, 8}.
fn coef(s: &[u8], i: usize, w: u32) -> u32 {
    let w = w as usize;
    let byte = s.get(i * w / 8).copied().unwrap_or(0) as u32;
    let shift = 8 - (w * (i % (8 / w)) + w);
    (byte >> shift) & ((1u32 << w) - 1)
}

/// LM-OTS signature length for the given parameters: `4 + n * (p + 1)`.
fn ots_sig_len(o: &OtsParams) -> usize {
    4 + o.n * (o.p + 1)
}

/// LMS public key length for the given LMS parameters: `4 + 4 + 16 + m`.
fn lms_pub_len(l: &LmsParams) -> usize {
    8 + I_LEN + l.m
}

/// Length of the LMS signature that starts at `sig[0]`, derived from its type
/// codes. Fails with `InvalidInput` if `sig` is too short to hold them and with
/// `Unsupported` for unknown type codes.
fn lms_sig_len(sig: &[u8]) -> Result<usize, Error> {
    let ots_code = sig.get(4..8).and_then(be32).ok_or(Error::InvalidInput)?;
    let ots = ots_params(ots_code).ok_or(Error::Unsupported)?;
    let off = 4 + ots_sig_len(&ots);
    let lms_code = sig.get(off..off + 4).and_then(be32).ok_or(Error::InvalidInput)?;
    let lms = lms_params(lms_code).ok_or(Error::Unsupported)?;
    Ok(off + 4 + lms.h as usize * lms.m)
}

/// Length of the LMS public key that starts at `pk[0]`.
fn lms_pub_len_at(pk: &[u8]) -> Result<usize, Error> {
    let code = pk.get(..4).and_then(be32).ok_or(Error::InvalidInput)?;
    let lms = lms_params(code).ok_or(Error::Unsupported)?;
    Ok(lms_pub_len(&lms))
}

/// Algorithm 4b of RFC 8554: the LM-OTS public key candidate `K_c`.
/// `y` holds `p * n` bytes.
fn ots_candidate(
    o: &OtsParams,
    i: &[u8],
    q: u32,
    c: &[u8],
    y: &[u8],
    msg: &[u8],
) -> [u8; MAX_N] {
    let n = o.n;
    // Q = H(I || u32str(q) || u16str(D_MESG) || C || message)
    let mut hq = prefixed(o.family, i, q, D_MESG);
    hq.update(c);
    hq.update(msg);
    let digest = hq.finish(n);

    // Q || Cksum(Q)
    let mut qc = [0u8; MAX_N + 2];
    qc[..n].copy_from_slice(&digest[..n]);
    let max = (1u32 << o.w) - 1;
    let mut sum: u32 = 0;
    for idx in 0..(n * 8 / o.w as usize) {
        sum += max - coef(&qc[..n], idx, o.w);
    }
    // sum <= 255 * 32 and ls <= 8 for every supported parameter set, so the
    // shifted value always fits in 16 bits.
    let ck = ((sum << o.ls) & 0xffff) as u16;
    qc[n..n + 2].copy_from_slice(&ck.to_be_bytes());

    // K = H(I || u32str(q) || u16str(D_PBLC) || z[0] || ... || z[p-1])
    let mut hk = prefixed(o.family, i, q, D_PBLC);
    for (idx, yi) in y.chunks_exact(n).take(o.p).enumerate() {
        let a = coef(&qc[..n + 2], idx, o.w);
        let mut tmp = [0u8; MAX_N];
        tmp[..n].copy_from_slice(yi);
        for j in a..max {
            // H(I || u32str(q) || u16str(i) || u8str(j) || tmp)
            let mut h = prefixed(o.family, i, q, idx as u16);
            h.update(&[j as u8]);
            h.update(&tmp[..n]);
            tmp = h.finish(n);
        }
        hk.update(&tmp[..n]);
    }
    hk.finish(n)
}

/// Algorithm 6a of RFC 8554: verify one LMS signature. `pk` is an LMS public
/// key (no `L` prefix).
fn lms_verify(pk: &[u8], msg: &[u8], sig: &[u8]) -> Result<(), Error> {
    // --- public key ---
    let pk_lms_code = pk.get(..4).and_then(be32).ok_or(Error::InvalidInput)?;
    let pk_ots_code = pk.get(4..8).and_then(be32).ok_or(Error::InvalidInput)?;
    let lms = lms_params(pk_lms_code).ok_or(Error::Unsupported)?;
    let ots = ots_params(pk_ots_code).ok_or(Error::Unsupported)?;
    // The LM-OTS and LMS parameter sets must use the same hash and size.
    if lms.family != ots.family || lms.m != ots.n {
        return Err(Error::InvalidInput);
    }
    if pk.len() != lms_pub_len(&lms) {
        return Err(Error::InvalidInput);
    }
    let i = &pk[8..8 + I_LEN];
    let t1 = &pk[8 + I_LEN..];

    // --- signature ---
    let q = sig.get(..4).and_then(be32).ok_or(Error::InvalidInput)?;
    let sig_ots_code = sig.get(4..8).and_then(be32).ok_or(Error::InvalidInput)?;
    let sig_ots = ots_params(sig_ots_code).ok_or(Error::Unsupported)?;
    if sig_ots_code != pk_ots_code {
        return Err(Error::VerificationFailed);
    }
    let n = ots.n;
    let ots_end = 4 + ots_sig_len(&sig_ots);
    let sig_lms_code = sig.get(ots_end..ots_end + 4).and_then(be32).ok_or(Error::InvalidInput)?;
    lms_params(sig_lms_code).ok_or(Error::Unsupported)?;
    if sig_lms_code != pk_lms_code {
        return Err(Error::VerificationFailed);
    }
    let h = lms.h as usize;
    if sig.len() != ots_end + 4 + h * lms.m {
        return Err(Error::InvalidInput);
    }
    if u64::from(q) >= (1u64 << lms.h) {
        return Err(Error::InvalidInput);
    }
    let c = &sig[8..8 + n];
    let y = &sig[8 + n..ots_end];
    let path = &sig[ots_end + 4..];

    // --- LM-OTS candidate, then the Merkle path ---
    let kc = ots_candidate(&ots, i, q, c, y, msg);

    let mut node_num: u32 = (1u32 << lms.h) + q;
    let mut tmp = {
        let mut hh = prefixed(lms.family, i, node_num, D_LEAF);
        hh.update(&kc[..n]);
        hh.finish(n)
    };
    for auth in path.chunks_exact(n) {
        let parent = node_num >> 1;
        let mut hh = prefixed(lms.family, i, parent, D_INTR);
        if node_num & 1 == 1 {
            hh.update(auth);
            hh.update(&tmp[..n]);
        } else {
            hh.update(&tmp[..n]);
            hh.update(auth);
        }
        tmp = hh.finish(n);
        node_num = parent;
    }

    if ct::eq(&tmp[..n], t1) == 0xff {
        Ok(())
    } else {
        Err(Error::VerificationFailed)
    }
}

/// Verifies a single-level LMS signature (RFC 8554 §5.4.2) with an LMS public key (no L prefix).
///
/// `public_key` is `u32 lms_type || u32 lmots_type || I[16] || T[1]`;
/// `signature` is `u32 q || LM-OTS signature || u32 lms_type || path`.
///
/// Returns `Ok(())` for a valid signature, `Err(Error::VerificationFailed)` for
/// a well-formed signature that does not verify, `Err(Error::InvalidInput)` for
/// malformed lengths or an out-of-range leaf number, and
/// `Err(Error::Unsupported)` for unknown LMS or LM-OTS type codes.
pub fn verify_lms(public_key: &[u8], msg: &[u8], signature: &[u8]) -> Result<(), Error> {
    lms_verify(public_key, msg, signature)
}

/// Verifies an HSS signature (RFC 8554 §6.3) over `msg` with an HSS public key (u32 L || LMS public key). Returns Ok(()) or Err(VerificationFailed / InvalidInput / Unsupported).
///
/// The signature is `u32 Nspk || (LMS sig || LMS pub)[Nspk] || LMS sig`, with
/// `Nspk = L - 1`. `L` must be between 1 and 8.
pub fn verify_hss(public_key: &[u8], msg: &[u8], signature: &[u8]) -> Result<(), Error> {
    let levels = public_key.get(..4).and_then(be32).ok_or(Error::InvalidInput)?;
    if levels == 0 || levels > MAX_LEVELS {
        return Err(Error::InvalidInput);
    }
    let top = &public_key[4..];
    if lms_pub_len_at(top)? != top.len() {
        return Err(Error::InvalidInput);
    }

    let nspk = signature.get(..4).and_then(be32).ok_or(Error::InvalidInput)?;
    if nspk != levels - 1 {
        return Err(Error::InvalidInput);
    }

    // Pass 1: walk the whole signature structure (cheap, no hashing) so that
    // every malformed or truncated input is rejected before any LM-OTS work.
    let mut walk = &signature[4..];
    for _ in 0..nspk {
        let sl = lms_sig_len(walk)?;
        let after_sig = walk.get(sl..).ok_or(Error::InvalidInput)?;
        let pl = lms_pub_len_at(after_sig)?;
        walk = after_sig.get(pl..).ok_or(Error::InvalidInput)?;
    }
    if lms_sig_len(walk)? != walk.len() {
        return Err(Error::InvalidInput);
    }

    // Pass 2: verify each level. The lengths were validated above.
    let mut rest = &signature[4..];
    let mut key = top;
    for _ in 0..nspk {
        // sig[i]
        let sl = lms_sig_len(rest)?;
        let (sig_i, after_sig) = rest.split_at_checked(sl).ok_or(Error::InvalidInput)?;
        // pub[i+1], which is the message signed by level i
        let pl = lms_pub_len_at(after_sig)?;
        let (next_pub, after_pub) = after_sig.split_at_checked(pl).ok_or(Error::InvalidInput)?;
        lms_verify(key, next_pub, sig_i)?;
        key = next_pub;
        rest = after_pub;
    }
    // sig[Nspk] covers the message and consumes the remaining bytes exactly
    // (lms_verify checks the exact length again).
    lms_verify(key, msg, rest)
}

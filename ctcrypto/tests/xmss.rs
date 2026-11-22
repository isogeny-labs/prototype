#![cfg(feature = "xmss")]
//! XMSS / XMSS^MT verification tests: differential vectors produced by the
//! independent xmss-reference C implementation (all four SP 800-208 hash
//! families), plus negative and robustness tests. RFC 8391 and the NIST ACVP
//! repository publish no XMSS signature vectors, so the reference
//! implementation is the independent evidence.

use ctcrypto::xmss::{verify, verify_mt};
use ctcrypto::Error;
use serde_json::Value;
use std::collections::BTreeSet;

struct Case {
    mt: bool,
    oid: u32,
    idx: u64,
    h: u32,
    pk: Vec<u8>,
    msg: Vec<u8>,
    sig: Vec<u8>,
}

fn load_cases() -> Vec<Case> {
    let path = format!("{}/tests/vectors/xmss_reference.json", env!("CARGO_MANIFEST_DIR"));
    let j: Value = serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    j["cases"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| Case {
            mt: c["mt"].as_u64().unwrap() == 1,
            oid: c["oid"].as_u64().unwrap() as u32,
            idx: c["idx"].as_u64().unwrap(),
            h: c["h"].as_u64().unwrap() as u32,
            pk: hex::decode(c["pk"].as_str().unwrap()).unwrap(),
            msg: hex::decode(c["msg"].as_str().unwrap()).unwrap(),
            sig: hex::decode(c["sig"].as_str().unwrap()).unwrap(),
        })
        .collect()
}

fn run(c: &Case, pk: &[u8], msg: &[u8], sig: &[u8]) -> Result<(), Error> {
    if c.mt {
        verify_mt(pk, msg, sig)
    } else {
        verify(pk, msg, sig)
    }
}

fn name(c: &Case) -> String {
    format!("{} oid={:#x} h={} idx={}", if c.mt { "XMSSMT" } else { "XMSS" }, c.oid, c.h, c.idx)
}

/// One case per (mt, oid), preferring a nonzero leaf index and a non-empty message.
fn one_per_set(cases: &[Case]) -> Vec<&Case> {
    let mut out: Vec<&Case> = Vec::new();
    for c in cases {
        match out.iter().position(|o| o.mt == c.mt && o.oid == c.oid) {
            None => out.push(c),
            Some(i) => {
                if out[i].idx == 0 && c.idx != 0 && !c.msg.is_empty() {
                    out[i] = c;
                }
            }
        }
    }
    out
}

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }
    fn below(&mut self, n: usize) -> usize {
        (self.next() % n as u64) as usize
    }
    fn bytes(&mut self, n: usize) -> Vec<u8> {
        (0..n).map(|_| self.next() as u8).collect()
    }
    fn rand_bytes(&mut self, max: usize) -> Vec<u8> {
        let n = self.below(max);
        self.bytes(n)
    }
}

#[test]
fn reference_vectors_verify() {
    let cases = load_cases();
    assert!(cases.len() >= 120);
    let mut sets = BTreeSet::new();
    for c in &cases {
        assert_eq!(run(c, &c.pk, &c.msg, &c.sig), Ok(()), "{}", name(c));
        sets.insert((c.mt, c.oid));
    }
    // The wrong entry point must reject the same vector, whichever OID space
    // the code falls into.
    for c in &cases {
        let other = if c.mt { verify(&c.pk, &c.msg, &c.sig) } else { verify_mt(&c.pk, &c.msg, &c.sig) };
        assert!(other.is_err(), "{} accepted by the wrong API", name(c));
    }
    // Every hash family, XMSS and XMSS^MT.
    for oid in [0x01u32, 0x0d, 0x10, 0x13] {
        assert!(sets.contains(&(false, oid)), "XMSS oid {oid:#x} not covered");
    }
    for oid in [0x01u32, 0x02, 0x04, 0x05, 0x07, 0x08]
        .into_iter()
        .chain([0x21, 0x22, 0x24, 0x25, 0x27, 0x28])
        .chain([0x29, 0x2a, 0x2c, 0x2d, 0x2f, 0x30])
        .chain([0x31, 0x32, 0x34, 0x35, 0x37, 0x38])
    {
        assert!(sets.contains(&(true, oid)), "XMSSMT oid {oid:#x} not covered");
    }
    // Leaf indices at the low and high end of the range were exercised.
    assert!(cases.iter().any(|c| c.idx == 0));
    assert!(cases.iter().any(|c| c.idx == (1u64 << c.h) - 2));
}

#[test]
fn wrong_message_and_modified_index_fail() {
    for c in one_per_set(&load_cases()) {
        let mut m = c.msg.clone();
        m.push(0);
        assert_eq!(run(c, &c.pk, &m, &c.sig), Err(Error::VerificationFailed), "{}", name(c));
        assert_eq!(run(c, &c.pk, b"", &c.sig).is_err(), !c.msg.is_empty(), "{}", name(c));
        // Flip the lowest bit of the leaf index (still in range): wrong leaf.
        let idx_len = if c.mt { c.h.div_ceil(8) as usize } else { 4 };
        let mut s = c.sig.clone();
        s[idx_len - 1] ^= 1;
        assert_eq!(run(c, &c.pk, &c.msg, &s), Err(Error::VerificationFailed), "{}", name(c));
    }
}

#[test]
fn index_range_is_checked() {
    for c in one_per_set(&load_cases()) {
        let idx_len = if c.mt { c.h.div_ceil(8) as usize } else { 4 };
        for bad in [1u64 << c.h, (1u64 << c.h) + 1, u64::MAX] {
            // Encode into idx_len big-endian bytes; skip values that do not fit.
            let bits = 8 * idx_len as u32;
            if bits < 64 && bad >> bits != 0 {
                continue;
            }
            let full = bad.to_be_bytes();
            let mut s = c.sig.clone();
            s[..idx_len].copy_from_slice(&full[8 - idx_len..]);
            assert_eq!(run(c, &c.pk, &c.msg, &s), Err(Error::InvalidInput), "{} bad idx {bad:#x}", name(c));
        }
        // An all-ones index field is out of range unless h fills the field
        // exactly (XMSS^MT with h = 40).
        if 8 * idx_len as u32 > c.h {
            let mut s = c.sig.clone();
            s[..idx_len].fill(0xff);
            assert_eq!(run(c, &c.pk, &c.msg, &s), Err(Error::InvalidInput), "{}", name(c));
        }
    }
}

#[test]
fn bit_flips_fail() {
    let mut rng = Rng(0x0bad_5eed_1234_5678);
    for c in one_per_set(&load_cases()) {
        let n = if c.pk.len() == 4 + 64 { 32 } else { 24 };
        // Signature: first and last byte, the r field, and a random sample.
        let mut pos = vec![0usize, c.sig.len() - 1, c.sig.len() / 2];
        let idx_len = if c.mt { c.h.div_ceil(8) as usize } else { 4 };
        pos.push(idx_len); // first byte of r
        pos.push(idx_len + n); // first byte of the first WOTS+ signature
        pos.extend((0..4).map(|_| rng.below(c.sig.len())));
        for p in pos {
            let b = rng.below(8);
            let mut s = c.sig.clone();
            s[p] ^= 1 << b;
            assert!(run(c, &c.pk, &c.msg, &s).is_err(), "{}: sig byte {p} bit {b}", name(c));
        }
        // Public key: OID, root and SEED.
        for p in [0usize, 3, 4, 4 + n - 1, 4 + n, c.pk.len() - 1] {
            let mut k = c.pk.clone();
            k[p] ^= 1 << rng.below(8);
            assert!(run(c, &k, &c.msg, &c.sig).is_err(), "{}: pk byte {p}", name(c));
        }
        // Message.
        if !c.msg.is_empty() {
            let mut m = c.msg.clone();
            let p = rng.below(m.len());
            m[p] ^= 1 << rng.below(8);
            assert!(run(c, &c.pk, &m, &c.sig).is_err(), "{}: msg", name(c));
        }
    }
}

#[test]
fn truncations_and_extensions_fail_without_panic() {
    for c in one_per_set(&load_cases()) {
        for len in 0..c.sig.len() {
            assert!(run(c, &c.pk, &c.msg, &c.sig[..len]).is_err(), "{}: sig len {len}", name(c));
        }
        for extra in [1usize, 2, 4, 8, 32, 100] {
            let mut s = c.sig.clone();
            s.extend(std::iter::repeat(0x5a).take(extra));
            assert!(run(c, &c.pk, &c.msg, &s).is_err(), "{}: sig +{extra}", name(c));
        }
        for len in 0..c.pk.len() {
            assert!(run(c, &c.pk[..len], &c.msg, &c.sig).is_err(), "{}: pk len {len}", name(c));
        }
        for extra in [1usize, 4, 32] {
            let mut k = c.pk.clone();
            k.extend(std::iter::repeat(0).take(extra));
            assert!(run(c, &k, &c.msg, &c.sig).is_err(), "{}: pk +{extra}", name(c));
        }
    }
}

#[test]
fn error_kinds() {
    let cases = load_cases();
    let x = cases.iter().find(|c| !c.mt && c.oid == 0x01).unwrap();
    let m = cases.iter().find(|c| c.mt && c.oid == 0x01).unwrap();
    for (c, f) in [(x, verify as fn(&[u8], &[u8], &[u8]) -> Result<(), Error>), (m, verify_mt)] {
        // Short or empty public key / signature -> InvalidInput.
        assert_eq!(f(&[], &c.msg, &c.sig), Err(Error::InvalidInput));
        assert_eq!(f(&c.pk[..3], &c.msg, &c.sig), Err(Error::InvalidInput));
        assert_eq!(f(&c.pk, &c.msg, &[]), Err(Error::InvalidInput));
        assert_eq!(f(&c.pk[..c.pk.len() - 1], &c.msg, &c.sig), Err(Error::InvalidInput));
        // Wrong message -> VerificationFailed.
        assert_eq!(f(&c.pk, b"x", &c.sig), Err(Error::VerificationFailed));
    }
    // Unsupported OIDs, with an otherwise plausible public key length.
    let unsupported_xmss: Vec<u32> = (0x04..=0x0c) // SHA-512, SHAKE128 and SHAKE256/512 sets of RFC 8391
        .chain([0, 0x16, 0x17, 0x100, 0x0100_0001, 0xffff_ffff])
        .collect();
    for oid in unsupported_xmss {
        for pk_len in [4 + 64, 4 + 48, 4 + 128] {
            let mut pk = vec![0u8; pk_len];
            pk[..4].copy_from_slice(&oid.to_be_bytes());
            assert_eq!(verify(&pk, b"", &x.sig), Err(Error::Unsupported), "xmss oid {oid:#x}");
        }
    }
    let unsupported_mt: Vec<u32> = (0x09..=0x20) // SHA-512, SHAKE128 and SHAKE256/512 sets of RFC 8391
        .chain([0, 0x39, 0x3a, 0xff, 0x100, 0x0100_0001, 0xffff_ffff])
        .collect();
    for oid in unsupported_mt {
        for pk_len in [4 + 64, 4 + 48, 4 + 128] {
            let mut pk = vec![0u8; pk_len];
            pk[..4].copy_from_slice(&oid.to_be_bytes());
            assert_eq!(verify_mt(&pk, b"", &m.sig), Err(Error::Unsupported), "xmssmt oid {oid:#x}");
        }
    }
}

#[test]
fn random_garbage_never_panics() {
    let mut rng = Rng(0xfeed_face_dead_beef);
    for _ in 0..4000 {
        let pk = rng.rand_bytes(90);
        let sig = rng.rand_bytes(300);
        let msg = rng.rand_bytes(70);
        let _ = verify(&pk, &msg, &sig);
        let _ = verify_mt(&pk, &msg, &sig);
    }
    // Garbage that starts with a supported OID and has the right lengths, so
    // the full verification path runs; it must report VerificationFailed
    // (or InvalidInput for an out-of-range leaf index), never succeed.
    let cases = load_cases();
    let sets = one_per_set(&cases);
    for it in 0..160 {
        let c = sets[it % sets.len()];
        let mut pk = c.pk.clone();
        let n = (pk.len() - 4) / 2;
        let tail = rng.bytes(2 * n);
        pk[4..].copy_from_slice(&tail);
        let mut sig = rng.bytes(c.sig.len());
        // Mostly in-range indices.
        let idx_len = if c.mt { c.h.div_ceil(8) as usize } else { 4 };
        if it % 4 != 0 {
            let v = (rng.next() & ((1u64 << c.h) - 1)).to_be_bytes();
            sig[..idx_len].copy_from_slice(&v[8 - idx_len..]);
        }
        let msg = rng.rand_bytes(100);
        let r = run(c, &pk, &msg, &sig);
        assert!(matches!(r, Err(Error::VerificationFailed) | Err(Error::InvalidInput)), "{}: {r:?}", name(c));
        // Cut at a random point: always InvalidInput.
        let cut = rng.below(sig.len());
        assert_eq!(run(c, &pk, &msg, &sig[..cut]), Err(Error::InvalidInput));
    }
}

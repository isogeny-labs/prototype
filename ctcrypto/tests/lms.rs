#![cfg(feature = "lms")]
//! LMS / HSS verification tests: RFC 8554 and RFC 9858 appendix vectors, NIST
//! ACVP sigVer/sigGen vectors, differential vectors from pyhsslms, and
//! negative / robustness tests.

use ctcrypto::lms::{verify_hss, verify_lms};
use ctcrypto::Error;
use serde_json::Value;

fn load(name: &str) -> Value {
    let path = format!("{}/tests/vectors/{}", env!("CARGO_MANIFEST_DIR"), name);
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path}: {e}"));
    serde_json::from_str(&text).unwrap()
}

fn hx(v: &Value, key: &str) -> Vec<u8> {
    hex::decode(v[key].as_str().unwrap()).unwrap()
}

/// Deterministic xorshift64* generator.
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
    fn rand_bytes(&mut self, max: usize) -> Vec<u8> {
        let n = self.below(max);
        self.bytes(n)
    }
    fn bytes(&mut self, n: usize) -> Vec<u8> {
        (0..n).map(|_| self.next() as u8).collect()
    }
}

/// A valid vector: HSS public key (with L prefix), message, HSS signature.
struct Vector {
    name: String,
    pk: Vec<u8>,
    msg: Vec<u8>,
    sig: Vec<u8>,
}

fn hss_vectors(file: &str) -> Vec<Vector> {
    let j = load(file);
    j["cases"]
        .as_array()
        .unwrap()
        .iter()
        .map(|c| Vector {
            name: c["name"].as_str().unwrap().to_string(),
            pk: hx(c, "public_key"),
            msg: hx(c, "message"),
            sig: hx(c, "signature"),
        })
        .collect()
}

/// Wraps an LMS public key / signature as an L = 1 HSS key / signature.
fn wrap_hss(pk: &[u8], sig: &[u8]) -> (Vec<u8>, Vec<u8>) {
    let mut p = 1u32.to_be_bytes().to_vec();
    p.extend_from_slice(pk);
    let mut s = 0u32.to_be_bytes().to_vec();
    s.extend_from_slice(sig);
    (p, s)
}

/// A small set of valid HSS vectors for the negative tests.
fn sample_vectors() -> Vec<Vector> {
    let mut v = hss_vectors("lms_rfc8554.json");
    v.extend(hss_vectors("lms_rfc9858.json"));
    // A few pyhsslms vectors covering every hash family, converted to HSS form.
    let j = load("lms_pyhsslms.json");
    let mut seen = std::collections::HashSet::new();
    for c in j["cases"].as_array().unwrap() {
        let pk = hx(c, "public_key");
        let sig = hx(c, "signature");
        let (pk, sig) = if c["kind"] == "lms" { wrap_hss(&pk, &sig) } else { (pk, sig) };
        let key = (pk[4..8].to_vec(), pk[8..12].to_vec(), c["kind"].as_str().unwrap().to_string());
        if sig.len() < 4000 && seen.insert(key) {
            v.push(Vector { name: c["name"].as_str().unwrap().to_string(), pk, msg: hx(c, "message"), sig });
        }
    }
    v
}

#[test]
fn rfc8554_appendix_f() {
    let v = hss_vectors("lms_rfc8554.json");
    assert_eq!(v.len(), 2);
    for t in &v {
        assert_eq!(verify_hss(&t.pk, &t.msg, &t.sig), Ok(()), "{}", t.name);
    }
}

#[test]
fn rfc9858_appendix_a() {
    let v = hss_vectors("lms_rfc9858.json");
    assert_eq!(v.len(), 4);
    for t in &v {
        assert_eq!(verify_hss(&t.pk, &t.msg, &t.sig), Ok(()), "{}", t.name);
        // The same vectors are L = 1: verify as plain LMS too.
        let mut sig = t.sig.clone();
        assert_eq!(&sig[..4], &[0, 0, 0, 0]);
        sig.drain(..4);
        assert_eq!(verify_lms(&t.pk[4..], &t.msg, &sig), Ok(()), "{}", t.name);
    }
}

#[test]
fn acvp_lms() {
    let j = load("lms_acvp.json");
    let cases = j["cases"].as_array().unwrap();
    assert_eq!(cases.len(), 78);
    let (mut pos, mut neg) = (0, 0);
    for c in cases {
        let pk = hx(c, "public_key");
        let msg = hx(c, "message");
        let sig = hx(c, "signature");
        let valid = c["valid"].as_bool().unwrap();
        let r = verify_lms(&pk, &msg, &sig);
        let (hpk, hsig) = wrap_hss(&pk, &sig);
        let rh = verify_hss(&hpk, &msg, &hsig);
        let id = format!("{} tg{} tc{} ({})", c["set"], c["tgId"], c["tcId"], c["reason"]);
        if valid {
            assert_eq!(r, Ok(()), "{id}");
            assert_eq!(rh, Ok(()), "{id} (HSS L=1)");
            pos += 1;
        } else {
            assert!(r.is_err(), "{id} must fail");
            assert!(rh.is_err(), "{id} (HSS L=1) must fail");
            neg += 1;
        }
    }
    assert_eq!((pos, neg), (66, 12));
}

#[test]
fn pyhsslms_differential() {
    let j = load("lms_pyhsslms.json");
    let cases = j["cases"].as_array().unwrap();
    assert!(cases.len() >= 80);
    let (mut lms, mut hss) = (0, 0);
    for c in cases {
        let pk = hx(c, "public_key");
        let msg = hx(c, "message");
        let sig = hx(c, "signature");
        let name = c["name"].as_str().unwrap();
        match c["kind"].as_str().unwrap() {
            "lms" => {
                assert_eq!(verify_lms(&pk, &msg, &sig), Ok(()), "{name}");
                let (hpk, hsig) = wrap_hss(&pk, &sig);
                assert_eq!(verify_hss(&hpk, &msg, &hsig), Ok(()), "{name} as HSS");
                lms += 1;
            }
            _ => {
                assert_eq!(verify_hss(&pk, &msg, &sig), Ok(()), "{name}");
                hss += 1;
            }
        }
    }
    assert!(lms >= 60 && hss >= 10);
}

#[test]
fn wrong_message_and_wrong_key_fail() {
    for t in sample_vectors() {
        let mut m = t.msg.clone();
        m.push(0);
        assert_eq!(verify_hss(&t.pk, &m, &t.sig), Err(Error::VerificationFailed), "{}", t.name);
        if !t.msg.is_empty() {
            let mut m = t.msg.clone();
            m[0] ^= 1;
            assert_eq!(verify_hss(&t.pk, &m, &t.sig), Err(Error::VerificationFailed), "{}", t.name);
        }
        assert!(verify_hss(&t.pk, &[], &t.sig).is_err() || t.msg.is_empty());
    }
}

#[test]
fn bit_flips_in_signature_public_key_and_message_fail() {
    let mut rng = Rng(0x1234_5678_9abc_def1);
    for t in sample_vectors() {
        // Signature: a sample of positions spread over the whole signature,
        // always including the first and last bytes of the signature.
        let mut positions: Vec<usize> = vec![0, 1, 3, 4, 7, 8, t.sig.len() - 1];
        positions.extend((0..40).map(|_| rng.below(t.sig.len())));
        for pos in positions {
            let bit = rng.below(8);
            let mut s = t.sig.clone();
            s[pos] ^= 1 << bit;
            assert!(verify_hss(&t.pk, &t.msg, &s).is_err(), "{}: sig byte {pos} bit {bit}", t.name);
        }
        // Public key: every bit of the first 12 bytes and a sample of the rest.
        let mut pk_bits: Vec<usize> = (0..12 * 8).collect();
        pk_bits.extend((0..16).map(|_| rng.below(t.pk.len() * 8)));
        for b in pk_bits {
            let mut p = t.pk.clone();
            p[b / 8] ^= 1 << (b % 8);
            assert!(verify_hss(&p, &t.msg, &t.sig).is_err(), "{}: pk bit {b}", t.name);
        }
        // Message.
        if !t.msg.is_empty() {
            for _ in 0..4 {
                let mut m = t.msg.clone();
                let pos = rng.below(m.len());
                m[pos] ^= 1 << rng.below(8);
                assert!(verify_hss(&t.pk, &m, &t.sig).is_err(), "{}: msg", t.name);
            }
        }
    }
}

#[test]
fn every_bit_of_a_small_signature_matters() {
    // RFC 9858 test case 1 (SHA-256/192, W8, H5): 784 bytes = 6272 bits.
    let t = &hss_vectors("lms_rfc9858.json")[0];
    let mut bad = 0;
    for byte in 0..t.sig.len() {
        // One rotating bit per byte keeps this fast but touches every byte.
        let mut s = t.sig.clone();
        s[byte] ^= 1 << (byte % 8);
        if verify_hss(&t.pk, &t.msg, &s).is_err() {
            bad += 1;
        }
    }
    assert_eq!(bad, t.sig.len());
}

#[test]
fn truncations_and_extensions_are_rejected_without_panic() {
    for t in sample_vectors() {
        for len in 0..t.sig.len() {
            assert!(verify_hss(&t.pk, &t.msg, &t.sig[..len]).is_err(), "{}: sig len {len}", t.name);
        }
        for extra in [1usize, 2, 3, 4, 32, 100] {
            let mut s = t.sig.clone();
            s.extend(std::iter::repeat(0xa5).take(extra));
            assert!(verify_hss(&t.pk, &t.msg, &s).is_err(), "{}: sig +{extra}", t.name);
        }
        for len in 0..t.pk.len() {
            assert!(verify_hss(&t.pk[..len], &t.msg, &t.sig).is_err(), "{}: pk len {len}", t.name);
        }
        for extra in [1usize, 4, 33] {
            let mut p = t.pk.clone();
            p.extend(std::iter::repeat(0).take(extra));
            assert!(verify_hss(&p, &t.msg, &t.sig).is_err(), "{}: pk +{extra}", t.name);
        }
    }
    // Same for the single-level API.
    let j = load("lms_acvp.json");
    let c = &j["cases"].as_array().unwrap()[4];
    let (pk, sig, msg) = (hx(c, "public_key"), hx(c, "signature"), hx(c, "message"));
    for len in 0..sig.len() {
        assert!(verify_lms(&pk, &msg, &sig[..len]).is_err());
    }
    for len in 0..pk.len() {
        assert!(verify_lms(&pk[..len], &msg, &sig).is_err());
    }
    assert!(verify_lms(&pk, &msg, &[sig.as_slice(), &[0]].concat()).is_err());
}

#[test]
fn error_kinds() {
    let t = &hss_vectors("lms_rfc9858.json")[0]; // L=1, LMS_SHA256_M24_H5 / LMOTS_SHA256_N24_W8
    let pk = &t.pk;
    let sig = &t.sig;
    assert_eq!(pk.len(), 4 + 8 + 16 + 24);

    // Wrong lengths -> InvalidInput.
    assert_eq!(verify_hss(&pk[..pk.len() - 1], &t.msg, sig), Err(Error::InvalidInput));
    assert_eq!(verify_hss(pk, &t.msg, &sig[..sig.len() - 1]), Err(Error::InvalidInput));
    assert_eq!(verify_hss(&[], &t.msg, sig), Err(Error::InvalidInput));
    assert_eq!(verify_hss(pk, &t.msg, &[]), Err(Error::InvalidInput));
    assert_eq!(verify_lms(&[], &t.msg, &[]), Err(Error::InvalidInput));

    // Number of levels outside 1..=8, or not matching Nspk -> InvalidInput.
    for l in [0u32, 9, 0xffff_ffff] {
        let mut p = pk.clone();
        p[..4].copy_from_slice(&l.to_be_bytes());
        assert_eq!(verify_hss(&p, &t.msg, sig), Err(Error::InvalidInput), "L={l}");
    }
    let mut p = pk.clone();
    p[..4].copy_from_slice(&2u32.to_be_bytes());
    assert_eq!(verify_hss(&p, &t.msg, sig), Err(Error::InvalidInput));
    let mut s = sig.clone();
    s[..4].copy_from_slice(&1u32.to_be_bytes());
    assert_eq!(verify_hss(pk, &t.msg, &s), Err(Error::InvalidInput));
    let mut s = sig.clone();
    s[..4].copy_from_slice(&0xffff_ffffu32.to_be_bytes());
    assert_eq!(verify_hss(pk, &t.msg, &s), Err(Error::InvalidInput));

    // Unknown public-key type codes -> Unsupported.
    for code in [0u32, 1, 4, 0x19, 0x1a, 0x0100_0000, 0xffff_ffff] {
        let mut p = pk.clone();
        p[4..8].copy_from_slice(&code.to_be_bytes());
        assert_eq!(verify_hss(&p, &t.msg, sig), Err(Error::Unsupported), "lms type {code:#x}");
    }
    for code in [0u32, 17, 18, 0x0100_0000, 0xffff_ffff] {
        let mut p = pk.clone();
        p[8..12].copy_from_slice(&code.to_be_bytes());
        assert_eq!(verify_hss(&p, &t.msg, sig), Err(Error::Unsupported), "ots type {code:#x}");
    }
    // Unknown type codes inside the signature -> Unsupported.
    for code in [0u32, 17, 0xffff_ffff] {
        let mut s = sig.clone();
        s[8..12].copy_from_slice(&code.to_be_bytes()); // LM-OTS type of the signature
        assert_eq!(verify_hss(pk, &t.msg, &s), Err(Error::Unsupported), "sig ots type {code:#x}");
    }
    let lms_type_off = 4 + 4 + 4 + 24 * 27; // Nspk, q, ots type, C + 26 y values
    for code in [0u32, 0x19, 0xffff_ffff] {
        let mut s = sig.clone();
        s[lms_type_off..lms_type_off + 4].copy_from_slice(&code.to_be_bytes());
        assert_eq!(verify_hss(pk, &t.msg, &s), Err(Error::Unsupported), "sig lms type {code:#x}");
    }
    // Known but different type codes inside the signature: verification fails.
    let mut s = sig.clone();
    s[lms_type_off..lms_type_off + 4].copy_from_slice(&0x0bu32.to_be_bytes());
    assert_eq!(verify_hss(pk, &t.msg, &s), Err(Error::VerificationFailed));

    // Mixed hash families / sizes in one key are malformed.
    let mut p = pk.clone();
    p[4..8].copy_from_slice(&0x0fu32.to_be_bytes()); // LMS_SHAKE_M32_H5, but OTS is N24 SHA-256
    assert_eq!(verify_hss(&p, &t.msg, sig), Err(Error::InvalidInput));

    // Leaf number out of range -> InvalidInput; in range but wrong -> VerificationFailed.
    for q in [32u32, 33, 0x8000_0000, 0xffff_ffff] {
        let mut s = sig.clone();
        s[4..8].copy_from_slice(&q.to_be_bytes());
        assert_eq!(verify_hss(pk, &t.msg, &s), Err(Error::InvalidInput), "q={q}");
    }
    let mut s = sig.clone();
    s[4..8].copy_from_slice(&6u32.to_be_bytes()); // genuine q is 5
    assert_eq!(verify_hss(pk, &t.msg, &s), Err(Error::VerificationFailed));

    // A wrong but well-formed signature.
    let mut m = t.msg.clone();
    m[0] ^= 0x80;
    assert_eq!(verify_hss(pk, &m, sig), Err(Error::VerificationFailed));
}

#[test]
fn hss_two_level_structure_is_checked() {
    let v = hss_vectors("lms_rfc8554.json");
    let t = &v[0]; // L = 2, all SHA-256/256
    // Dropping or duplicating the embedded public key breaks parsing.
    let mut s = t.sig.clone();
    s.drain(4 + 1292..4 + 1292 + 56);
    assert!(verify_hss(&t.pk, &t.msg, &s).is_err());
    // Swapping a level-1 public-key byte invalidates the level-0 signature.
    let mut s = t.sig.clone();
    s[4 + 1292 + 30] ^= 1;
    assert_eq!(verify_hss(&t.pk, &t.msg, &s), Err(Error::VerificationFailed));
    // Signature for a different message at level 1 fails.
    let mut m = t.msg.clone();
    m.push(b'!');
    assert_eq!(verify_hss(&t.pk, &m, &t.sig), Err(Error::VerificationFailed));
    // An L=2 signature cannot be used with an L=1 key made from the same root.
    let mut p = t.pk.clone();
    p[..4].copy_from_slice(&1u32.to_be_bytes());
    assert!(verify_hss(&p, &t.msg, &t.sig).is_err());
    // ... and the first-level signature alone is not a valid single-level
    // signature over the message.
    assert!(verify_lms(&t.pk[4..], &t.msg, &t.sig[4..4 + 1292]).is_err());
}

// (lms code, lm-ots code, n, p, h) for every supported parameter set, used to
// build well-formed garbage that exercises the hashing paths.
fn param_table() -> Vec<(u32, u32, usize, usize, usize)> {
    let mut v = Vec::new();
    for fam in 0..4u32 {
        let n = if fam % 2 == 0 { 32 } else { 24 };
        for w in 0..4u32 {
            let p = match (n, w) {
                (32, 0) => 265,
                (32, 1) => 133,
                (32, 2) => 67,
                (32, _) => 34,
                (_, 0) => 200,
                (_, 1) => 101,
                (_, 2) => 51,
                _ => 26,
            };
            for hi in 0..5u32 {
                // Heights 20 and 25 are exercised too: the Merkle path is
                // short and cheap compared with the OTS chains.
                v.push((5 + 5 * fam + hi, 1 + 4 * fam + w, n, p, 5 * (hi as usize + 1)));
            }
        }
    }
    v
}

#[test]
fn random_garbage_never_panics() {
    let mut rng = Rng(0xdead_beef_cafe_f00d);
    // Completely random inputs of random lengths (short, since the interesting
    // parsing happens in the first few bytes).
    for _ in 0..4000 {
        let pk = rng.rand_bytes(80);
        let sig = rng.rand_bytes(400);
        let msg = rng.rand_bytes(70);
        let _ = verify_hss(&pk, &msg, &sig);
        let _ = verify_lms(&pk, &msg, &sig);
    }
    // Random bytes behind well-formed headers, with and without exact lengths.
    let table = param_table();
    for it in 0..600 {
        let (lms, ots, n, p, h) = table[rng.below(table.len())];
        let mut pk = Vec::new();
        pk.extend_from_slice(&lms.to_be_bytes());
        pk.extend_from_slice(&ots.to_be_bytes());
        pk.extend(rng.bytes(16 + n));
        let q = if it % 3 == 0 { rng.next() as u32 } else { (rng.next() as u32) & ((1u32 << h) - 1) };
        let mut sig = Vec::new();
        sig.extend_from_slice(&q.to_be_bytes());
        sig.extend_from_slice(&ots.to_be_bytes());
        sig.extend(rng.bytes(n * (p + 1)));
        sig.extend_from_slice(&lms.to_be_bytes());
        sig.extend(rng.bytes(h * n));
        let msg = rng.rand_bytes(100);
        let r = verify_lms(&pk, &msg, &sig);
        assert!(r.is_err(), "random signature verified!");
        if it % 3 != 0 {
            assert_eq!(r, Err(Error::VerificationFailed));
        } else if u64::from(q) >= 1u64 << h {
            assert_eq!(r, Err(Error::InvalidInput));
        }
        // Wrong lengths of the same.
        let cut = rng.below(sig.len());
        assert!(verify_lms(&pk, &msg, &sig[..cut]).is_err());
        // As HSS with random level counts and random continuation.
        let mut hpk = ((rng.below(10)) as u32).to_be_bytes().to_vec();
        hpk.extend_from_slice(&pk);
        let mut hsig = ((rng.below(10)) as u32).to_be_bytes().to_vec();
        hsig.extend_from_slice(&sig);
        hsig.extend(rng.rand_bytes(300));
        assert!(verify_hss(&hpk, &msg, &hsig).is_err());
    }
}

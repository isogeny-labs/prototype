#![cfg(feature = "mldsa")]
//! ML-DSA-87 against NIST ACVP vectors (keyGen, sigGen, sigVer), round trips,
//! tampering and malformed-signature handling.
//!
//! `tests/vectors/mldsa_acvp.json` is a trimmed ML-DSA-87 extract of the ACVP
//! `internalProjection.json` files (sources and SHA-256 inside the file).
//! Set `MLDSA_ACVP_DIR` to a directory holding the untrimmed downloads
//! (`keyGen.json`, `sigGen.json`, `sigVer.json`) to also run every ML-DSA-87
//! case of every supported group with full byte comparison.
use ctcrypto::mldsa::{self, PK_LEN, SIG_LEN, SK_LEN};
use ctcrypto::sha2::Sha256;
use std::collections::{BTreeMap, BTreeSet};

const SIG_H_OFF: usize = 64 + 7 * 640;
const OMEGA: usize = 75;

fn hx(v: &serde_json::Value, k: &str) -> Vec<u8> {
    hex::decode(v[k].as_str().unwrap_or_else(|| panic!("missing {k}"))).unwrap()
}

fn arr<const LEN: usize>(v: Vec<u8>) -> [u8; LEN] {
    v.try_into().unwrap_or_else(|v: Vec<u8>| panic!("length {} != {}", v.len(), LEN))
}

fn sha256_hex(b: &[u8]) -> String {
    hex::encode(Sha256::digest(b))
}

fn vectors() -> serde_json::Value {
    serde_json::from_str(include_str!("vectors/mldsa_acvp.json")).unwrap()
}

/// Signs one sigGen case (any supported interface).
fn siggen_case(c: &serde_json::Value) -> [u8; SIG_LEN] {
    let sk: [u8; SK_LEN] = arr(hx(c, "sk"));
    let rnd: [u8; 32] = arr(hx(c, "rnd"));
    if c["externalMu"].as_bool().unwrap() {
        mldsa::sign_mu(&sk, &arr(hx(c, "mu")), &rnd)
    } else if c["interface"] == "internal" {
        mldsa::sign_internal(&sk, &hx(c, "message"), &rnd)
    } else {
        mldsa::sign(&sk, &hx(c, "message"), &hx(c, "context"), &rnd).unwrap()
    }
}

/// Verifies one sigVer case (any supported interface).
fn sigver_case(c: &serde_json::Value) -> bool {
    let pk: [u8; PK_LEN] = arr(hx(c, "pk"));
    let sig: [u8; SIG_LEN] = arr(hx(c, "signature"));
    if c["externalMu"].as_bool().unwrap() {
        mldsa::verify_mu(&pk, &arr(hx(c, "mu")), &sig)
    } else if c["interface"] == "internal" {
        mldsa::verify_internal(&pk, &hx(c, "message"), &sig)
    } else {
        mldsa::verify(&pk, &hx(c, "message"), &hx(c, "context"), &sig)
    }
}

#[test]
fn acvp_keygen() {
    let v = vectors();
    let cases = v["keyGen"].as_array().unwrap();
    for c in cases {
        let (pk, sk) = mldsa::keygen_internal(&arr(hx(c, "seed")));
        assert_eq!(sha256_hex(&pk), c["pk_sha256"], "keyGen pk tcId {}", c["tcId"]);
        assert_eq!(sha256_hex(&sk), c["sk_sha256"], "keyGen sk tcId {}", c["tcId"]);
    }
    println!("ACVP keyGen ML-DSA-87: {} cases passed", cases.len());
    assert_eq!(cases.len(), 25);
}

#[test]
fn acvp_siggen() {
    let v = vectors();
    let mut per_group: BTreeMap<u64, usize> = BTreeMap::new();
    for c in v["sigGen"].as_array().unwrap() {
        let sig = siggen_case(c);
        assert_eq!(sha256_hex(&sig), c["signature_sha256"], "sigGen tg {} tc {}", c["tgId"], c["tcId"]);
        *per_group.entry(c["tgId"].as_u64().unwrap()).or_default() += 1;
    }
    println!("ACVP sigGen ML-DSA-87 passed per tgId: {per_group:?}");
    // internal/external x deterministic/hedged, plus external-mu groups
    assert_eq!(per_group.keys().copied().collect::<Vec<_>>(), vec![5, 11, 12, 17, 23, 24]);
}

#[test]
fn acvp_sigver() {
    let v = vectors();
    let mut reasons: BTreeMap<String, (usize, bool)> = BTreeMap::new();
    let mut per_group: BTreeMap<u64, usize> = BTreeMap::new();
    for c in v["sigVer"].as_array().unwrap() {
        let expect = c["testPassed"].as_bool().unwrap();
        let reason = c["reason"].as_str().unwrap().to_string();
        assert_eq!(sigver_case(c), expect, "sigVer tg {} tc {} ({reason})", c["tgId"], c["tcId"]);
        let e = reasons.entry(reason).or_insert((0, expect));
        e.0 += 1;
        *per_group.entry(c["tgId"].as_u64().unwrap()).or_default() += 1;
    }
    println!("ACVP sigVer ML-DSA-87 passed per tgId: {per_group:?}");
    println!("ACVP sigVer reasons exercised: {reasons:?}");
    let expected: BTreeSet<&str> = [
        "valid signature and message - signature should verify successfully",
        "modified message",
        "modified signature - commitment",
        "modified signature - hint",
        "modified signature - z",
    ]
    .into_iter()
    .collect();
    assert_eq!(reasons.keys().map(|s| s.as_str()).collect::<BTreeSet<_>>(), expected);
    assert_eq!(per_group.values().sum::<usize>(), 45);
}

/// Runs every ML-DSA-87 case of every supported group from the untrimmed
/// ACVP files, comparing full bytes. Skipped (with a message) unless
/// `MLDSA_ACVP_DIR` is set.
#[test]
fn acvp_full_files_if_present() {
    let Ok(dir) = std::env::var("MLDSA_ACVP_DIR") else {
        println!("MLDSA_ACVP_DIR not set; full-file ACVP run skipped");
        return;
    };
    let load = |n: &str| -> serde_json::Value {
        serde_json::from_slice(&std::fs::read(format!("{dir}/{n}.json")).unwrap()).unwrap()
    };
    let (mut pass, mut skipped) = (BTreeMap::new(), BTreeMap::new());
    for g in load("keyGen")["testGroups"].as_array().unwrap() {
        if g["parameterSet"] != "ML-DSA-87" {
            continue;
        }
        for c in g["tests"].as_array().unwrap() {
            let (pk, sk) = mldsa::keygen_internal(&arr(hx(c, "seed")));
            assert_eq!(pk.to_vec(), hx(c, "pk"));
            assert_eq!(sk.to_vec(), hx(c, "sk"));
        }
        pass.insert(format!("keyGen tg{}", g["tgId"]), g["tests"].as_array().unwrap().len());
    }
    for (file, is_gen) in [("sigGen", true), ("sigVer", false)] {
        for g in load(file)["testGroups"].as_array().unwrap() {
            if g["parameterSet"] != "ML-DSA-87" {
                continue;
            }
            let n = g["tests"].as_array().unwrap().len();
            let name = format!("{file} tg{}", g["tgId"]);
            if g["preHash"] == "preHash" {
                skipped.insert(name, n);
                continue;
            }
            for c in g["tests"].as_array().unwrap() {
                let mut c = c.clone();
                c["interface"] = g["signatureInterface"].clone();
                c["externalMu"] = g["externalMu"].clone();
                if is_gen {
                    if c.get("rnd").is_none() {
                        c["rnd"] = serde_json::Value::String("00".repeat(32));
                    }
                    assert_eq!(siggen_case(&c).to_vec(), hx(&c, "signature"), "{name} tc {}", c["tcId"]);
                } else {
                    assert_eq!(sigver_case(&c), c["testPassed"].as_bool().unwrap(), "{name} tc {}", c["tcId"]);
                }
            }
            pass.insert(name, n);
        }
    }
    println!("full ACVP ML-DSA-87 passed: {pass:?}");
    println!("full ACVP ML-DSA-87 skipped (HashML-DSA): {skipped:?}");
}

// ---------------------------------------------------------------------------
// Round trips and tampering
// ---------------------------------------------------------------------------

/// Deterministic test byte generator (SHAKE256 of a label).
fn bytes(label: &str, i: u64, len: usize) -> Vec<u8> {
    let mut out = vec![0u8; len];
    let mut s = ctcrypto::sha3::Sponge::shake256();
    s.absorb(label.as_bytes());
    s.absorb(&i.to_le_bytes());
    s.squeeze(&mut out);
    out
}

#[test]
fn round_trip_many_seeds_and_lengths() {
    let lens = [0usize, 1, 2, 31, 32, 33, 135, 136, 137, 1000, 4097];
    let mut n_sigs = 0;
    for seed in 0..12u64 {
        let xi: [u8; 32] = arr(bytes("xi", seed, 32));
        let (pk, sk) = mldsa::keygen_internal(&xi);
        let (pk2, _) = mldsa::keygen_internal(&arr(bytes("xi", seed + 1000, 32)));
        let msg = bytes("msg", seed, lens[seed as usize % lens.len()]);
        let ctxs: [Vec<u8>; 3] = [vec![], bytes("ctx", seed, 1), bytes("ctx", seed, 255)];
        for (ci, ctx) in ctxs.iter().enumerate() {
            let rnd: [u8; 32] = if ci == 1 { [0; 32] } else { arr(bytes("rnd", seed * 3 + ci as u64, 32)) };
            let sig = mldsa::sign(&sk, &msg, ctx, &rnd).unwrap();
            n_sigs += 1;
            assert!(mldsa::verify(&pk, &msg, ctx, &sig));
            // same thing through the internal interface with M' built by hand
            let mut mp = vec![0u8, ctx.len() as u8];
            mp.extend_from_slice(ctx);
            mp.extend_from_slice(&msg);
            assert_eq!(mldsa::sign_internal(&sk, &mp, &rnd), sig);
            assert!(mldsa::verify_internal(&pk, &mp, &sig));
            // internal interface is not the external one
            assert!(!mldsa::verify_internal(&pk, &msg, &sig));
            // wrong context
            let mut ctx2 = ctx.clone();
            if ctx2.is_empty() {
                ctx2.push(0);
            } else {
                ctx2[0] ^= 1;
            }
            assert!(!mldsa::verify(&pk, &msg, &ctx2, &sig));
            // tampered message
            let mut m2 = msg.clone();
            if m2.is_empty() {
                m2.push(0);
            } else {
                let k = m2.len() / 2;
                m2[k] ^= 0x80;
            }
            assert!(!mldsa::verify(&pk, &m2, ctx, &sig));
            // wrong public key / tampered public key (rho and t1 regions)
            assert!(!mldsa::verify(&pk2, &msg, ctx, &sig));
            for pos in [0usize, 31, 32, 1000, PK_LEN - 1] {
                let mut p = pk;
                p[pos] ^= 0x04;
                assert!(!mldsa::verify(&p, &msg, ctx, &sig), "pk byte {pos}");
            }
            // tampered signature: c_tilde, z, hint area
            for pos in [0usize, 63, 64, 2000, SIG_H_OFF - 1, SIG_H_OFF, SIG_LEN - 1] {
                let mut s = sig;
                s[pos] ^= 0x01;
                assert!(!mldsa::verify(&pk, &msg, ctx, &s), "sig byte {pos}");
            }
        }
        // ctx too long
        assert_eq!(mldsa::sign(&sk, &msg, &[0u8; 256], &[0; 32]), Err(ctcrypto::Error::InvalidInput));
        let sig = mldsa::sign(&sk, &msg, &[], &[0; 32]).unwrap();
        assert!(!mldsa::verify(&pk, &msg, &[0u8; 256], &sig));
        // deterministic is deterministic; hedged differs
        assert_eq!(sig, mldsa::sign(&sk, &msg, &[], &[0; 32]).unwrap());
        assert_ne!(sig, mldsa::sign(&sk, &msg, &[], &[1; 32]).unwrap());
        // external-mu entry points agree with the others
        let mut mp = vec![0u8, 0];
        mp.extend_from_slice(&msg);
        let mut h = ctcrypto::sha3::Sponge::shake256();
        let mut tr = [0u8; 64];
        let mut th = ctcrypto::sha3::Sponge::shake256();
        th.absorb(&pk);
        th.squeeze(&mut tr);
        h.absorb(&tr);
        h.absorb(&mp);
        let mut mu = [0u8; 64];
        h.squeeze(&mut mu);
        assert_eq!(mldsa::sign_mu(&sk, &mu, &[0; 32]), sig);
        assert!(mldsa::verify_mu(&pk, &mu, &sig));
    }
    println!("round trip: {n_sigs} signatures over 12 keys");
}

// ---------------------------------------------------------------------------
// Malformed signatures
// ---------------------------------------------------------------------------

fn fixture() -> ([u8; PK_LEN], [u8; SIG_LEN], Vec<u8>) {
    // pick a key/message whose signature has >= 2 hints in some polynomial
    // and fewer than omega hints in total, so every malformation is reachable
    for i in 0..100u64 {
        let (pk, sk) = mldsa::keygen_internal(&arr(bytes("fx", i, 32)));
        let msg = bytes("fxm", i, 50);
        let sig = mldsa::sign(&sk, &msg, b"ctx", &[0; 32]).unwrap();
        let counts = &sig[SIG_H_OFF + OMEGA..];
        let total = counts[7] as usize;
        let mut prev = 0;
        let two = counts.iter().any(|&c| {
            let ok = c as usize - prev >= 2;
            prev = c as usize;
            ok
        });
        if two && (2..OMEGA).contains(&total) {
            assert!(mldsa::verify(&pk, &msg, b"ctx", &sig));
            return (pk, sig, msg);
        }
    }
    panic!("no fixture");
}

fn set_z_coeff(sig: &mut [u8; SIG_LEN], poly: usize, n: usize, packed: u32) {
    // 20-bit little-endian field: coefficient n of z[poly]
    let bit = (64 + poly * 640) * 8 + n * 20;
    for b in 0..20 {
        let byte = (bit + b) / 8;
        let sh = (bit + b) % 8;
        sig[byte] = (sig[byte] & !(1 << sh)) | ((((packed >> b) & 1) as u8) << sh);
    }
}

#[test]
fn malformed_signatures_rejected_without_panic() {
    let (pk, sig, msg) = fixture();
    let ok = |s: &[u8; SIG_LEN]| mldsa::verify(&pk, &msg, b"ctx", s);
    let h = SIG_H_OFF;
    let counts: Vec<usize> = sig[h + OMEGA..].iter().map(|&c| c as usize).collect();
    let total = counts[7];
    // first polynomial with >= 2 hints
    let (pi, start) = {
        let mut prev = 0;
        let mut found = None;
        for (i, &c) in counts.iter().enumerate() {
            if c - prev >= 2 {
                found = Some((i, prev));
                break;
            }
            prev = c;
        }
        found.unwrap()
    };

    // bad hint ordering: swap two indices of one polynomial (decreasing)
    let mut s = sig;
    s.swap(h + start, h + start + 1);
    assert!(!ok(&s), "decreasing hint indices");
    // repeated index (not strictly increasing)
    let mut s = sig;
    s[h + start + 1] = s[h + start];
    assert!(!ok(&s), "repeated hint index");
    // hint count beyond omega
    let mut s = sig;
    s[h + OMEGA + 7] = (OMEGA + 1) as u8;
    assert!(!ok(&s), "count > omega");
    let mut s = sig;
    s[h + OMEGA + pi] = 255;
    assert!(!ok(&s), "count 255");
    // counts decreasing across polynomials (count[i+1] < count[i])
    let mut s = sig;
    if pi < 7 {
        s[h + OMEGA + pi + 1] = (counts[pi] - 1) as u8;
    } else {
        s[h + OMEGA + 6] = (counts[7] + 1) as u8;
    }
    assert!(!ok(&s), "decreasing counts");
    // nonzero padding after the last used index
    for p in [total, OMEGA - 1] {
        let mut s = sig;
        s[h + p] = 1;
        assert!(!ok(&s), "nonzero padding at {p}");
    }
    // count claims more hints than were written (padding read as index) — a
    // zero index after a nonzero one is a decreasing order
    let mut s = sig;
    s[h + OMEGA + 7] = (total + 1) as u8;
    assert!(!ok(&s), "count past written indices");

    // z out of range: packed b = gamma1 - z
    for (packed, what) in [(120u32, "z = gamma1 - beta"), (0, "z = gamma1"), ((1 << 20) - 1, "z = -gamma1 + 1"), ((1 << 19) + (1 << 19) - 120, "z = -(gamma1 - beta)")] {
        for (poly, n) in [(0usize, 0usize), (6, 255), (3, 128)] {
            let mut s = sig;
            set_z_coeff(&mut s, poly, n, packed);
            assert!(!ok(&s), "{what} at z[{poly}][{n}]");
        }
    }
    // boundary inside the range does not trip the norm check by itself (it
    // fails only because the signature is now wrong): check no panic
    let mut s = sig;
    set_z_coeff(&mut s, 0, 0, 121);
    assert!(!ok(&s));

    // garbage signatures and keys: no panic, all false
    for fill in [0u8, 0xff, 0x80, 0x4b] {
        assert!(!ok(&[fill; SIG_LEN]));
        assert!(!mldsa::verify(&[fill; PK_LEN], &msg, b"ctx", &sig));
        assert!(!mldsa::verify_internal(&[fill; PK_LEN], &msg, &[fill; SIG_LEN]));
    }
    for i in 0..200u64 {
        let mut s: [u8; SIG_LEN] = arr(bytes("garbage", i, SIG_LEN));
        if i % 2 == 0 {
            // keep the hint area well formed-ish but random elsewhere
            s[h..].copy_from_slice(&sig[h..]);
        }
        assert!(!ok(&s));
    }
}

#[test]
fn garbage_secret_key_does_not_panic() {
    // skDecode accepts any bit pattern; signing must terminate without panic.
    for i in 0..3u64 {
        let sk: [u8; SK_LEN] = arr(bytes("sk", i, SK_LEN));
        let _ = mldsa::sign(&sk, b"m", b"", &[0; 32]).unwrap();
    }
}

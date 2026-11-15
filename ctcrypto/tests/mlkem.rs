#![cfg(feature = "mlkem")]
//! ML-KEM-1024 against NIST ACVP vectors (ML-KEM-1024 groups of the ACVP-Server
//! `internalProjection.json` files; sources and SHA-256 in the vector file),
//! a differential corpus from RustCrypto `ml-kem` 0.2.3, implicit rejection,
//! the §7.2 / §7.3 input checks, and keygen/encaps/decaps round trips.
use ctcrypto::mlkem::{self, CT_LEN, DK_LEN, EK_LEN, SS_LEN};
use ctcrypto::sha3;
use ctcrypto::Error;

fn hx(v: &serde_json::Value, k: &str) -> Vec<u8> {
    hex::decode(v[k].as_str().unwrap_or_else(|| panic!("missing {k}"))).unwrap()
}
fn arr<const L: usize>(v: &serde_json::Value, k: &str) -> [u8; L] {
    hx(v, k).try_into().unwrap_or_else(|_| panic!("bad length for {k}"))
}

fn acvp() -> serde_json::Value {
    serde_json::from_str(include_str!("vectors/mlkem_acvp.json")).unwrap()
}

fn group<'a>(j: &'a serde_json::Value, section: &str, function: &str) -> &'a serde_json::Value {
    let gs: Vec<_> = j[section]
        .as_array()
        .unwrap()
        .iter()
        .filter(|g| {
            g["parameterSet"] == "ML-KEM-1024"
                && (function.is_empty() || g["function"].as_str() == Some(function))
        })
        .collect();
    assert_eq!(gs.len(), 1, "{section}/{function}");
    gs[0]
}

/// J(z || c) computed independently with the crate's SHAKE256.
fn j_reject(dk: &[u8; DK_LEN], c: &[u8]) -> [u8; 32] {
    let mut inp = dk[DK_LEN - 32..].to_vec();
    inp.extend_from_slice(c);
    let mut out = [0u8; 32];
    sha3::shake256(&inp, &mut out);
    out
}

/// Deterministic test seeds: SHAKE256(label || i).
fn seed(label: &str, i: u32) -> [u8; 96] {
    let mut inp = label.as_bytes().to_vec();
    inp.extend_from_slice(&i.to_le_bytes());
    let mut out = [0u8; 96];
    sha3::shake256(&inp, &mut out);
    out
}
fn split(s: &[u8; 96]) -> ([u8; 32], [u8; 32], [u8; 32]) {
    (s[..32].try_into().unwrap(), s[32..64].try_into().unwrap(), s[64..].try_into().unwrap())
}

#[test]
fn sizes() {
    assert_eq!((EK_LEN, DK_LEN, CT_LEN, SS_LEN), (1568, 3168, 1568, 32));
}

#[test]
fn acvp_keygen() {
    let j = acvp();
    let g = group(&j, "keyGen", "");
    let tests = g["tests"].as_array().unwrap();
    for t in tests {
        let (ek, dk) = mlkem::keygen_internal(&arr(t, "d"), &arr(t, "z"));
        assert_eq!(ek.to_vec(), hx(t, "ek"), "tcId {}", t["tcId"]);
        assert_eq!(dk.to_vec(), hx(t, "dk"), "tcId {}", t["tcId"]);
    }
    assert_eq!(tests.len(), 25);
    eprintln!("ACVP ML-KEM-1024 keyGen: {} cases passed", tests.len());
}

#[test]
fn acvp_encapsulation() {
    let j = acvp();
    let g = group(&j, "encapDecap", "encapsulation");
    let tests = g["tests"].as_array().unwrap();
    for t in tests {
        let (c, k) = mlkem::encaps_internal(&arr(t, "ek"), &arr(t, "m")).unwrap();
        assert_eq!(c.to_vec(), hx(t, "c"), "tcId {}", t["tcId"]);
        assert_eq!(k.to_vec(), hx(t, "k"), "tcId {}", t["tcId"]);
        // and the matching dk decapsulates it
        let k2 = mlkem::decaps(&arr(t, "dk"), &c).unwrap();
        assert_eq!(k2, k, "tcId {}", t["tcId"]);
    }
    assert_eq!(tests.len(), 25);
    eprintln!("ACVP ML-KEM-1024 encapsulation: {} cases passed", tests.len());
}

#[test]
fn acvp_decapsulation() {
    let j = acvp();
    let g = group(&j, "encapDecap", "decapsulation");
    let tests = g["tests"].as_array().unwrap();
    let mut modified = 0;
    for t in tests {
        let dk: [u8; DK_LEN] = arr(t, "dk");
        let c: [u8; CT_LEN] = arr(t, "c");
        let k = mlkem::decaps(&dk, &c).unwrap();
        assert_eq!(k.to_vec(), hx(t, "k"), "tcId {}", t["tcId"]);
        if t["reason"] == "modified ciphertext" {
            modified += 1;
            assert_eq!(k, j_reject(&dk, &c), "tcId {}: expected J(z||c)", t["tcId"]);
        }
    }
    assert_eq!(tests.len(), 10);
    eprintln!(
        "ACVP ML-KEM-1024 decapsulation: {} cases passed ({} modified-ciphertext)",
        tests.len(),
        modified
    );
}

#[test]
fn acvp_encapsulation_key_check() {
    let j = acvp();
    let g = group(&j, "encapDecap", "encapsulationKeyCheck");
    let tests = g["tests"].as_array().unwrap();
    let mut rejected = 0;
    for t in tests {
        let pass = t["testPassed"].as_bool().unwrap();
        let r = mlkem::encaps_internal(&arr(t, "ek"), &[0x5a; 32]);
        assert_eq!(r.is_ok(), pass, "tcId {} ({})", t["tcId"], t["reason"]);
        if !pass {
            rejected += 1;
            assert_eq!(r, Err(Error::InvalidInput));
        }
    }
    assert_eq!(tests.len(), 10);
    assert!(rejected > 0);
    eprintln!(
        "ACVP ML-KEM-1024 encapsulationKeyCheck: {} cases passed ({} invalid)",
        tests.len(),
        rejected
    );
}

#[test]
fn acvp_decapsulation_key_check() {
    let j = acvp();
    let g = group(&j, "encapDecap", "decapsulationKeyCheck");
    let tests = g["tests"].as_array().unwrap();
    let mut rejected = 0;
    for t in tests {
        let pass = t["testPassed"].as_bool().unwrap();
        let r = mlkem::decaps(&arr(t, "dk"), &[0u8; CT_LEN]);
        assert_eq!(r.is_ok(), pass, "tcId {} ({})", t["tcId"], t["reason"]);
        if !pass {
            rejected += 1;
            assert_eq!(r, Err(Error::InvalidInput));
        }
    }
    assert_eq!(tests.len(), 10);
    assert!(rejected > 0);
    eprintln!(
        "ACVP ML-KEM-1024 decapsulationKeyCheck: {} cases passed ({} invalid)",
        tests.len(),
        rejected
    );
}

#[test]
fn differential_rustcrypto() {
    let j: serde_json::Value =
        serde_json::from_str(include_str!("vectors/mlkem_diff_rustcrypto.json")).unwrap();
    let cases = j["cases"].as_array().unwrap();
    for c in cases {
        let (ek, dk) = mlkem::keygen_internal(&arr(c, "d"), &arr(c, "z"));
        assert_eq!(sha3::sha3_256(&ek).to_vec(), hx(c, "ek_sha3"), "i {}", c["i"]);
        assert_eq!(sha3::sha3_256(&dk).to_vec(), hx(c, "dk_sha3"), "i {}", c["i"]);
        let (ct, k) = mlkem::encaps_internal(&ek, &arr(c, "m")).unwrap();
        assert_eq!(sha3::sha3_256(&ct).to_vec(), hx(c, "c_sha3"), "i {}", c["i"]);
        assert_eq!(k.to_vec(), hx(c, "k"), "i {}", c["i"]);
        assert_eq!(mlkem::decaps(&dk, &ct).unwrap(), k);
        let mut bad = ct;
        bad[c["flip_pos"].as_u64().unwrap() as usize] ^= c["flip_mask"].as_u64().unwrap() as u8;
        let kb = mlkem::decaps(&dk, &bad).unwrap();
        assert_eq!(kb.to_vec(), hx(c, "k_bad"), "i {}", c["i"]);
        assert_eq!(kb, j_reject(&dk, &bad));
    }
    assert!(cases.len() >= 300);
    eprintln!("differential vs RustCrypto ml-kem 0.2.3: {} cases passed", cases.len());
}

#[test]
fn implicit_rejection_bit_flips() {
    let mut n = 0;
    for i in 0..8u32 {
        let (d, z, m) = split(&seed("ctcrypto-mlkem-implicit", i));
        let (ek, dk) = mlkem::keygen_internal(&d, &z);
        let (ct, k) = mlkem::encaps_internal(&ek, &m).unwrap();
        assert_eq!(mlkem::decaps(&dk, &ct).unwrap(), k);
        // positions in every u-polynomial, the v-polynomial, and both ends
        let positions = [0usize, 1, 351, 352, 700, 1055, 1407, 1408, 1500, CT_LEN - 1];
        for (pi, &p) in positions.iter().enumerate() {
            for bit in [0u8, (pi as u8 + i as u8) % 8, 7] {
                let mut bad = ct;
                bad[p] ^= 1 << bit;
                let kb = mlkem::decaps(&dk, &bad).expect("decaps must return Ok on a bad ciphertext");
                assert_eq!(kb, j_reject(&dk, &bad), "seed {i} pos {p} bit {bit}");
                assert_ne!(kb, k);
                n += 1;
            }
        }
        // an all-zero and an all-ones ciphertext are also implicitly rejected
        for fill in [0u8, 0xff] {
            let bad = [fill; CT_LEN];
            assert_eq!(mlkem::decaps(&dk, &bad).unwrap(), j_reject(&dk, &bad));
            n += 1;
        }
    }
    eprintln!("implicit rejection: {n} modified ciphertexts gave Ok(J(z||c))");
}

/// Sets 12-bit coefficient `idx` of the t-hat encoding in `ek` to `v`.
fn set_coeff(ek: &mut [u8], idx: usize, v: u16) {
    let b = 3 * (idx / 2);
    if idx % 2 == 0 {
        ek[b] = v as u8;
        ek[b + 1] = (ek[b + 1] & 0xf0) | ((v >> 8) as u8 & 0x0f);
    } else {
        ek[b + 1] = (ek[b + 1] & 0x0f) | (((v & 0x0f) as u8) << 4);
        ek[b + 2] = (v >> 4) as u8;
    }
}

#[test]
fn ek_modulus_check_negative() {
    let (d, z, m) = split(&seed("ctcrypto-mlkem-ekcheck", 0));
    let (ek, _dk) = mlkem::keygen_internal(&d, &z);
    let mut n = 0;
    for idx in [0usize, 1, 2, 255, 256, 511, 767, 1000, 1022, 1023] {
        for v in [3329u16, 3330, 4000, 4095] {
            let mut bad = ek;
            set_coeff(&mut bad, idx, v);
            assert_eq!(mlkem::encaps_internal(&bad, &m), Err(Error::InvalidInput), "idx {idx} v {v}");
            n += 1;
        }
        for v in [0u16, 1, 3328] {
            let mut good = ek;
            set_coeff(&mut good, idx, v);
            assert!(mlkem::encaps_internal(&good, &m).is_ok(), "idx {idx} v {v}");
        }
    }
    // rho is not range-checked: any bytes there are valid.
    let mut r = ek;
    for b in r[EK_LEN - 32..].iter_mut() {
        *b = 0xff;
    }
    assert!(mlkem::encaps_internal(&r, &m).is_ok());
    eprintln!("ek modulus check: {n} out-of-range keys rejected");
}

#[test]
fn dk_hash_check_negative() {
    let (d, z, m) = split(&seed("ctcrypto-mlkem-dkcheck", 0));
    let (ek, dk) = mlkem::keygen_internal(&d, &z);
    let (ct, k) = mlkem::encaps_internal(&ek, &m).unwrap();
    let mut n = 0;
    // Corrupting the embedded ek (t-hat or rho) or the stored hash must fail.
    for p in [1536usize, 2000, 3071, 3072, 3103, 3104, 3120, 3135] {
        for bit in [0u8, 3, 7] {
            let mut bad = dk;
            bad[p] ^= 1 << bit;
            assert_eq!(mlkem::decaps(&bad, &ct), Err(Error::InvalidInput), "pos {p} bit {bit}");
            n += 1;
        }
    }
    // Corrupting z is not detected by the check: decaps of a valid ciphertext
    // still yields K; of an invalid one it yields J(z'||c).
    let mut zbad = dk;
    zbad[DK_LEN - 1] ^= 1;
    assert_eq!(mlkem::decaps(&zbad, &ct).unwrap(), k);
    eprintln!("dk hash check: {n} corrupted keys rejected");
}

#[test]
fn roundtrip_many_seeds() {
    let n = 200;
    for i in 0..n {
        let (d, z, m) = split(&seed("ctcrypto-mlkem-roundtrip", i));
        let (ek, dk) = mlkem::keygen_internal(&d, &z);
        assert_eq!(&dk[1536..3104], &ek[..]);
        assert_eq!(&dk[3104..3136], &sha3::sha3_256(&ek)[..]);
        assert_eq!(&dk[3136..], &z[..]);
        let (ct, k) = mlkem::encaps_internal(&ek, &m).unwrap();
        assert_eq!(mlkem::decaps(&dk, &ct).unwrap(), k, "seed {i}");
    }
    eprintln!("round trip: {n} seeds passed");
}

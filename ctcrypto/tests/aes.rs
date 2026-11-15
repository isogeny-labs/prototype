#![cfg(feature = "aes")]

use ctcrypto::aes::{gcm, inv_sbox_block, sbox_block, Aes256};
use ctcrypto::Error;
use serde_json::Value;

/// Reference S-box. It lives only in this test file; the library computes it.
const SBOX: [u8; 256] = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
];

fn h(s: &str) -> Vec<u8> {
    hex::decode(s).unwrap()
}
fn a32(v: &[u8]) -> [u8; 32] {
    v.try_into().unwrap()
}
fn a16(v: &[u8]) -> [u8; 16] {
    v.try_into().unwrap()
}
fn load(name: &str) -> Value {
    let p = format!("{}/tests/vectors/{}", env!("CARGO_MANIFEST_DIR"), name);
    serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
}
fn s<'a>(v: &'a Value, k: &str) -> &'a str {
    v[k].as_str().unwrap()
}

#[test]
fn fips197_c3() {
    let key: Vec<u8> = (0u8..32).collect();
    let pt = h("00112233445566778899aabbccddeeff");
    let ct = h("8ea2b7ca516745bfeafc49904b496089");
    let c = Aes256::new(&a32(&key));
    let mut b = a16(&pt);
    c.encrypt_block(&mut b);
    assert_eq!(b.to_vec(), ct);
    c.decrypt_block(&mut b);
    assert_eq!(b.to_vec(), pt);
}

#[test]
fn sbox_matches_reference_and_inverse() {
    for base in (0..256).step_by(16) {
        let mut inp = [0u8; 16];
        for (i, x) in inp.iter_mut().enumerate() {
            *x = (base + i) as u8;
        }
        let out = sbox_block(&inp);
        let back = inv_sbox_block(&out);
        for i in 0..16 {
            assert_eq!(out[i], SBOX[base + i], "sbox({:#04x})", base + i);
            assert_eq!(back[i], inp[i], "inv_sbox(sbox({:#04x}))", base + i);
        }
        // Inverse S-box applied to arbitrary inputs agrees with the reference inverse.
        let inv = inv_sbox_block(&inp);
        for i in 0..16 {
            assert_eq!(SBOX[inv[i] as usize], inp[i]);
        }
    }
}

#[test]
fn acvp_ecb_aft() {
    let v = load("aes_acvp.json");
    for (dir, n_expected) in [("encrypt", 415), ("decrypt", 415)] {
        let cases = v["ecb256"][dir].as_array().unwrap();
        assert_eq!(cases.len(), n_expected);
        for t in cases {
            let c = Aes256::new(&a32(&h(s(t, "key"))));
            let (src, dst) = if dir == "encrypt" { ("pt", "ct") } else { ("ct", "pt") };
            // MMT cases are multi-block; ECB processes each block independently.
            let mut data = h(s(t, src));
            assert_eq!(data.len() % 16, 0);
            for chunk in data.chunks_mut(16) {
                let mut b = a16(chunk);
                if dir == "encrypt" {
                    c.encrypt_block(&mut b);
                } else {
                    c.decrypt_block(&mut b);
                }
                chunk.copy_from_slice(&b);
            }
            assert_eq!(data, h(s(t, dst)), "ECB {} tcId {}", dir, t["tcId"]);
        }
        println!("ACVP ECB-AES-256 {dir} AFT: {} cases passed", cases.len());
    }
}

/// ACVP AES-ECB Monte Carlo test, AES-256 (SP 800-38 / ACVP spec §6.1.3).
fn mct(enc: bool, v: &Value) -> usize {
    let t = &v[0];
    let mut key = a32(&h(s(t, "key")));
    let mut text = a16(&h(s(t, "start")));
    let results = t["results"].as_array().unwrap();
    assert_eq!(results.len(), 100);
    for r in results {
        assert_eq!(key.to_vec(), h(s(r, "key")));
        let (inp, outp) = if enc { ("pt", "ct") } else { ("ct", "pt") };
        assert_eq!(text.to_vec(), h(s(r, inp)));
        let c = Aes256::new(&key);
        let mut prev = [0u8; 16];
        let mut cur = text;
        for _ in 0..1000 {
            prev = cur;
            if enc {
                c.encrypt_block(&mut cur);
            } else {
                c.decrypt_block(&mut cur);
            }
        }
        assert_eq!(cur.to_vec(), h(s(r, outp)));
        // Key[i+1] = Key[i] ^ (out[998] || out[999])
        for i in 0..16 {
            key[i] ^= prev[i];
            key[16 + i] ^= cur[i];
        }
        text = cur;
    }
    results.len()
}

#[test]
fn acvp_ecb_mct() {
    let v = load("aes_acvp.json");
    let n1 = mct(true, &v["ecb256"]["mct_encrypt"]);
    let n2 = mct(false, &v["ecb256"]["mct_decrypt"]);
    println!("ACVP ECB-AES-256 MCT: encrypt {n1} outer iterations, decrypt {n2} outer iterations passed");
}

#[test]
fn acvp_gcm_groups_present_are_noted() {
    // The downloaded ACVP-AES-GCM-1.0 internalProjection.json has no
    // keyLen=256 / ivLen=96 / tagLen=128 group, so there is nothing to run.
    let v = load("aes_acvp.json");
    let groups = v["gcm256"].as_array().unwrap();
    for g in groups {
        for t in g["tests"].as_array().unwrap() {
            let key = a32(&h(s(t, "key")));
            let iv: [u8; 12] = h(s(t, "iv")).try_into().unwrap();
            let aad = h(s(t, "aad"));
            let tag = a16(&h(s(t, "tag")));
            if g["direction"] == "encrypt" {
                let mut d = h(s(t, "pt"));
                let tg = gcm::seal(&key, &iv, &aad, &mut d);
                assert_eq!(d, h(s(t, "ct")));
                assert_eq!(tg, tag);
            } else {
                let mut d = h(s(t, "ct"));
                let r = gcm::open(&key, &iv, &aad, &mut d, &tag);
                if t["testPassed"].as_bool().unwrap() {
                    r.unwrap();
                    assert_eq!(d, h(s(t, "pt")));
                } else {
                    assert_eq!(r, Err(Error::VerificationFailed));
                }
            }
        }
    }
    println!("ACVP GCM keyLen=256 groups run: {}", groups.len());
}

#[test]
fn gcm_spec_test_cases_13_14() {
    // McGrew & Viega GCM spec test cases 13 and 14 (zero key, zero nonce).
    let key = [0u8; 32];
    let nonce = [0u8; 12];
    let mut d: [u8; 0] = [];
    assert_eq!(gcm::seal(&key, &nonce, &[], &mut d).to_vec(), h("530f8afbc74536b9a963b4f1c4cb738b"));
    let mut d = [0u8; 16];
    let tag = gcm::seal(&key, &nonce, &[], &mut d);
    assert_eq!(d.to_vec(), h("cea7403d4d606b6e074ec5d3baf39d18"));
    assert_eq!(tag.to_vec(), h("d0d1c8a799996bf0265b98b5d48ab919"));
}

#[test]
fn differential_vs_python_cryptography() {
    let v = load("aes_gcm_diff.json");
    let cases = v.as_array().unwrap();
    assert!(cases.len() >= 200);
    for (n, t) in cases.iter().enumerate() {
        let key = a32(&h(s(t, "key")));
        let nonce: [u8; 12] = h(s(t, "nonce")).try_into().unwrap();
        let aad = h(s(t, "aad"));
        let pt = h(s(t, "pt"));
        let ct = h(s(t, "ct"));
        let tag = a16(&h(s(t, "tag")));
        let mut d = pt.clone();
        let got = gcm::seal(&key, &nonce, &aad, &mut d);
        assert_eq!(d, ct, "case {n} ciphertext");
        assert_eq!(got, tag, "case {n} tag");
        gcm::open(&key, &nonce, &aad, &mut d, &tag).unwrap();
        assert_eq!(d, pt, "case {n} open");
    }
    println!("differential GCM cases passed: {}", cases.len());
}

#[test]
fn tamper_detection_leaves_data_unchanged() {
    let key = [0x42u8; 32];
    let nonce = [7u8; 12];
    let aad = b"header bytes".to_vec();
    let mut data: Vec<u8> = (0..70u8).collect();
    let tag = gcm::seal(&key, &nonce, &aad, &mut data);
    let ct = data.clone();

    // Flip each tag bit.
    for bit in 0..128 {
        let mut t = tag;
        t[bit / 8] ^= 1 << (bit % 8);
        let mut d = ct.clone();
        assert_eq!(gcm::open(&key, &nonce, &aad, &mut d, &t), Err(Error::VerificationFailed));
        assert_eq!(d, ct);
    }
    // Flip each ciphertext bit.
    for bit in 0..ct.len() * 8 {
        let mut d = ct.clone();
        d[bit / 8] ^= 1 << (bit % 8);
        let before = d.clone();
        assert_eq!(gcm::open(&key, &nonce, &aad, &mut d, &tag), Err(Error::VerificationFailed));
        assert_eq!(d, before);
    }
    // Flip each aad bit.
    for bit in 0..aad.len() * 8 {
        let mut a = aad.clone();
        a[bit / 8] ^= 1 << (bit % 8);
        let mut d = ct.clone();
        assert_eq!(gcm::open(&key, &nonce, &a, &mut d, &tag), Err(Error::VerificationFailed));
        assert_eq!(d, ct);
    }
    // Wrong nonce and wrong key.
    let mut d = ct.clone();
    assert!(gcm::open(&key, &[8u8; 12], &aad, &mut d, &tag).is_err());
    assert_eq!(d, ct);
    let mut k2 = key;
    k2[31] ^= 0x80;
    assert!(gcm::open(&k2, &nonce, &aad, &mut d, &tag).is_err());
    assert_eq!(d, ct);
    // Untampered still opens.
    gcm::open(&key, &nonce, &aad, &mut d, &tag).unwrap();
    assert_eq!(d, (0..70u8).collect::<Vec<_>>());
}

#[test]
fn block_roundtrip_many_keys() {
    let mut x = 0x9e37_79b9_7f4a_7c15u64;
    let mut next = || {
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        x
    };
    for _ in 0..50 {
        let mut key = [0u8; 32];
        let mut blk = [0u8; 16];
        key.chunks_mut(8).for_each(|c| c.copy_from_slice(&next().to_le_bytes()));
        blk.chunks_mut(8).for_each(|c| c.copy_from_slice(&next().to_le_bytes()));
        let c = Aes256::new(&key);
        let orig = blk;
        c.encrypt_block(&mut blk);
        assert_ne!(blk, orig);
        c.decrypt_block(&mut blk);
        assert_eq!(blk, orig);
    }
}

#[test]
#[ignore]
fn throughput_seal_1mb() {
    let key = [1u8; 32];
    let nonce = [2u8; 12];
    let mut data = vec![0u8; 1 << 20];
    let _ = gcm::seal(&key, &nonce, b"", &mut data); // warm-up
    let n = 5;
    let t = std::time::Instant::now();
    for _ in 0..n {
        let _ = gcm::seal(&key, &nonce, b"", &mut data);
    }
    let secs = t.elapsed().as_secs_f64() / n as f64;
    println!("seal 1 MiB: {:.3} ms, {:.2} MiB/s", secs * 1e3, 1.0 / secs);
}

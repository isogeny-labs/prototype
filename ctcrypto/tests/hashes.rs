//! SHA-2 and SHA-3 against CPython `hashlib` (OpenSSL) over boundary lengths,
//! with one-shot, split and byte-at-a-time absorption and split squeezing.
use ctcrypto::{sha2, sha3};

fn h(v: &serde_json::Value, k: &str) -> Vec<u8> {
    hex::decode(v[k].as_str().unwrap()).unwrap()
}

#[test]
fn against_hashlib() {
    let cases: serde_json::Value =
        serde_json::from_str(include_str!("vectors/hashes.json")).unwrap();
    for c in cases.as_array().unwrap() {
        let m = h(c, "msg");
        assert_eq!(sha2::Sha256::digest(&m).to_vec(), h(c, "sha256"));
        assert_eq!(sha2::Sha384::digest(&m).to_vec(), h(c, "sha384"));
        assert_eq!(sha2::Sha512::digest(&m).to_vec(), h(c, "sha512"));
        assert_eq!(sha3::sha3_256(&m).to_vec(), h(c, "sha3_256"));
        assert_eq!(sha3::sha3_512(&m).to_vec(), h(c, "sha3_512"));
        let mut o = [0u8; 400];
        sha3::shake128(&m, &mut o);
        assert_eq!(o.to_vec(), h(c, "shake128"));
        sha3::shake256(&m, &mut o);
        assert_eq!(o.to_vec(), h(c, "shake256"));

        // split and byte-wise absorption
        for split in [0, 1, m.len() / 2, m.len()] {
            let split = split.min(m.len());
            let mut a = sha2::Sha256::new();
            a.update(&m[..split]);
            a.update(&m[split..]);
            assert_eq!(a.finalize().to_vec(), h(c, "sha256"));
            let mut a = sha2::Sha512::new();
            a.update(&m[..split]);
            a.update(&m[split..]);
            assert_eq!(a.finalize().to_vec(), h(c, "sha512"));
        }
        let mut a = sha2::Sha384::new();
        let mut s = sha3::Sponge::shake256();
        for b in &m {
            a.update(core::slice::from_ref(b));
            s.absorb(core::slice::from_ref(b));
        }
        assert_eq!(a.finalize().to_vec(), h(c, "sha384"));
        // split squeezing across the rate boundary
        let mut o = [0u8; 400];
        let (x, y) = o.split_at_mut(135);
        s.squeeze(x);
        let (y1, y2) = y.split_at_mut(2);
        s.squeeze(y1);
        s.squeeze(y2);
        assert_eq!(o.to_vec(), h(c, "shake256"));
    }
}

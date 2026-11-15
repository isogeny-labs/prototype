//! AES-256-GCM against Project Wycheproof (key 256, nonce 96, tag 128),
//! including its forged-tag cases.
#![cfg(feature = "aes")]
use ctcrypto::aes::gcm;

#[test]
fn wycheproof_aes256_gcm() {
    let v: serde_json::Value =
        serde_json::from_str(include_str!("vectors/aes_gcm_wycheproof.json")).unwrap();
    let h = |t: &serde_json::Value, k: &str| hex::decode(t[k].as_str().unwrap()).unwrap();
    let (mut valid, mut invalid) = (0, 0);
    for t in v["tests"].as_array().unwrap() {
        let key: [u8; 32] = h(t, "key").try_into().unwrap();
        let iv: [u8; 12] = h(t, "iv").try_into().unwrap();
        let tag: [u8; 16] = h(t, "tag").try_into().unwrap();
        let (aad, msg, ct) = (h(t, "aad"), h(t, "msg"), h(t, "ct"));
        let id = t["tcId"].as_u64().unwrap();
        let mut buf = ct.clone();
        let r = gcm::open(&key, &iv, &aad, &mut buf, &tag);
        match t["result"].as_str().unwrap() {
            "valid" => {
                assert!(r.is_ok(), "tcId {id}");
                assert_eq!(buf, msg, "tcId {id}");
                let mut enc = msg.clone();
                assert_eq!(gcm::seal(&key, &iv, &aad, &mut enc), tag, "tcId {id}");
                assert_eq!(enc, ct, "tcId {id}");
                valid += 1;
            }
            "invalid" => {
                assert!(r.is_err(), "tcId {id}");
                assert_eq!(buf, ct, "tcId {id}: data changed on failure");
                invalid += 1;
            }
            other => panic!("unexpected result class {other}"),
        }
    }
    assert_eq!((valid, invalid), (39, 27));
}

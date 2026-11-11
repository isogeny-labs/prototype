"""Items in a file that this version doesn't check are listed as "skipped", never dropped silently.
And a failed upload leaves nothing imported."""
import json

from app.config import DEMO_CBOM
from app.importers import parse_cbom, parse_file

from conftest import csv_bytes, upload
from test_importers import cbom


def asset(ref, name, asset_type="algorithm", **props):
    key = {"algorithm": "algorithmProperties", "related-crypto-material": "relatedCryptoMaterialProperties",
           "certificate": "certificateProperties", "protocol": "protocolProperties"}[asset_type]
    return {"type": "cryptographic-asset", "bom-ref": ref, "name": name,
            "cryptoProperties": {"assetType": asset_type, key: props}}


def add_hash_and_cipher(doc):
    doc["components"] += [
        asset("alg-sha256", "SHA-256", primitive="hash", parameterSetIdentifier="256"),
        asset("alg-aes", "AES-256-GCM", primitive="ae", parameterSetIdentifier="256", mode="gcm"),
    ]
    doc["dependencies"].append({"ref": "lib-acme-sign", "dependsOn": ["alg-sha256", "alg-aes"]})


def test_demo_file_has_nothing_skipped():
    parsed = parse_file(DEMO_CBOM.name, DEMO_CBOM.read_bytes())
    assert len(parsed.claims) == 3
    # the public key and the ECDSA algorithm are what the certificate claim was read from, so they are not "skipped"
    assert parsed.skipped == []


def test_hash_and_cipher_assets_are_listed_as_skipped_and_claims_are_unchanged():
    parsed = parse_file("scan.json", cbom(add_hash_and_cipher))
    assert parsed.claims == parse_cbom(DEMO_CBOM.read_bytes())
    sha, aes = parsed.skipped
    assert (sha.name, sha.what, sha.reason) == ("SHA-256", "Hash algorithm", "Hash algorithms are not checked in this version")
    assert sha.source == "components[5] (bom-ref alg-sha256)"
    assert (aes.name, aes.what, aes.reason) == (
        "AES-256-GCM", "Encryption algorithm", "Encryption algorithms are not checked in this version")
    assert aes.source == "components[6] (bom-ref alg-aes)"


def test_csv_never_has_skipped_items():
    assert parse_file("claims.csv", csv_bytes("localhost:8443,tls,protocol_versions,TLS1.3")).skipped == []


def test_loose_keys_and_algorithms_only_named_by_a_certificate_or_protocol_are_listed():
    def m(doc):
        doc["components"] += [
            asset("key-old", "Old signing key", "related-crypto-material", type="private-key", value="not-shown"),
            asset("alg-rsa", "RSA-2048", primitive="signature", parameterSetIdentifier="2048"),
            asset("alg-x25519", "X25519", primitive="key-agree"),
            asset("alg-odd", "Thing", primitive="other"),
        ]
        cert = next(c for c in doc["components"] if c.get("bom-ref") == "cert-server")
        cert["cryptoProperties"]["certificateProperties"]["signatureAlgorithmRef"] = "alg-rsa"  # value comes from the key
        proto = next(c for c in doc["components"] if c.get("bom-ref") == "proto-tls13")
        proto["cryptoProperties"]["protocolProperties"]["cryptoRefArray"].append("alg-x25519")
        proto["cryptoProperties"]["protocolProperties"]["cipherSuites"] = [
            {"name": "TLS_AES_128_GCM_SHA256"}, {"name": "not a suite name!"}, {"identifiers": ["0x13", "0x02"]}]
    parsed = parse_file("scan.json", cbom(m))
    assert [c.kind for c in parsed.claims] == ["protocol_versions", "cipher_suites", "certificate", "signature_algorithm"]
    assert parsed.claims[2].claimed_value == "ECDSA P-256"
    got = [(s.name, s.what) for s in parsed.skipped]
    assert got == [("not a suite name!", "Cipher suite"), ("(no name)", "Cipher suite"), ("Old signing key", "Private key"),
                   ("RSA-2048", "Signature algorithm"), ("X25519", "Key-exchange algorithm"), ("Thing", "Algorithm")]
    assert "cipherSuites[1]" in parsed.skipped[0].source and "proto-tls13" in parsed.skipped[0].source
    assert all(s.reason and s.source for s in parsed.skipped)
    assert "not-shown" not in json.dumps([vars(s) for s in parsed.skipped])  # a key's value is never copied


def cbomkit_style() -> dict:
    """Shaped like a source-code scan (many algorithm assets, uuid refs, file-path occurrences)."""
    def found(a, path, line):
        a["evidence"] = {"occurrences": [{"location": path, "line": line, "offset": 12, "additionalContext": "java.security"}]}
        return a
    comps = [
        found(asset("a1", "SHA256", primitive="hash", parameterSetIdentifier="256", cryptoFunctions=["digest"]), "src/A.java", 10),
        found(asset("a2", "SHA384", primitive="hash", parameterSetIdentifier="384"), "src/A.java", 31),
        found(asset("a3", "AES128-GCM", primitive="ae", parameterSetIdentifier="128", mode="gcm"), "src/B.java", 7),
        found(asset("a4", "AES256-CBC-PKCS5", primitive="block-cipher", mode="cbc", padding="pkcs5"), "src/B.java", 44),
        found(asset("a5", "HMAC-SHA256", primitive="mac"), "src/C.java", 5),
        found(asset("a6", "PBKDF2", primitive="kdf"), "src/C.java", 19),
        found(asset("a7", "SHA256withRSA", primitive="signature", parameterSetIdentifier="2048"), "src/D.java", 3),
        found(asset("a8", "RSA-2048", primitive="pke", parameterSetIdentifier="2048"), "src/D.java", 9),
        found(asset("a9", "ECDH", primitive="key-agree", curve="secp256r1"), "src/E.java", 12),
        found(asset("a10", "SecureRandom", primitive="drbg"), "src/E.java", 40),
        found(asset("a11", "ChaCha20"), "src/F.java", 2),  # no primitive stated
        found(asset("k1", "secret-key@a3", "related-crypto-material", type="secret-key", algorithmRef="a3", size=128), "src/B.java", 8),
        found(asset("k2", "key@a8", "related-crypto-material", type="public-key", algorithmRef="a8", size=2048), "src/D.java", 10),
        found(asset("p1", "TLSv1.2", "protocol", type="tls", version="1.2", cipherSuites=[
            {"name": "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256", "algorithms": ["a9", "a3", "a1"]}]), "src/G.java", 1),
        {"type": "library", "bom-ref": "lib", "name": "bcprov-jdk18on", "version": "1.78"},
    ]
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": {"component": {"type": "application", "bom-ref": "app", "name": "example-app", "version": "0.1"}},
            "components": comps,
            "dependencies": [{"ref": "app", "dependsOn": ["lib", "a1", "a7"]}, {"ref": "k1", "dependsOn": ["a3"]},
                             {"ref": "a7", "dependsOn": ["a1"]}]}


def test_realistic_scan_file_imports_and_every_crypto_asset_is_in_a_claim_or_skipped():
    doc = cbomkit_style()
    parsed = parse_file("cbom.json", json.dumps(doc).encode())
    refs = [c["bom-ref"] for c in doc["components"] if c["type"] == "cryptographic-asset"]
    in_claims = {r for r in refs if any(f"(bom-ref {r})" in c.source for c in parsed.claims)}
    in_skipped = [r for r in refs if any(s.source.endswith(f"(bom-ref {r})") for s in parsed.skipped)]
    assert in_claims == {"a7", "p1"}  # a9 (ECDH) is only named inside the TLS entry, so it is listed as skipped
    assert not in_claims & set(in_skipped)
    assert len(in_claims) + len(in_skipped) == len(refs) == 14
    assert len(parsed.skipped) == len(in_skipped) == 12  # one entry per skipped asset, none twice
    whats = {s.name: s.what for s in parsed.skipped}
    assert whats["HMAC-SHA256"] == "Message authentication code (MAC)" and whats["PBKDF2"] == "Key derivation function"
    assert whats["secret-key@a3"] == "Secret key" and whats["ChaCha20"] == "Algorithm"


# ------------------------------------------------------------------ through the API

def test_api_returns_and_keeps_skipped_items(client):
    imp = client.post("/api/import/demo").json()
    assert imp["skipped"] == [] and len(imp["claims"]) == 3
    assert upload(client, "claims.csv", csv_bytes("localhost:8443,tls,protocol_versions,TLS1.3")).json()["skipped"] == []
    imp = upload(client, "scan.json", cbom(add_hash_and_cipher)).json()
    assert len(imp["claims"]) == 3
    assert imp["skipped"] == [
        {"name": "SHA-256", "what": "Hash algorithm", "source": "components[5] (bom-ref alg-sha256)",
         "reason": "Hash algorithms are not checked in this version"},
        {"name": "AES-256-GCM", "what": "Encryption algorithm", "source": "components[6] (bom-ref alg-aes)",
         "reason": "Encryption algorithms are not checked in this version"}]
    assert client.get("/api/import/current").json() == imp


def test_failed_upload_leaves_nothing_imported(client):
    assert client.post("/api/import/demo").status_code == 200
    assert client.get("/api/import/current").status_code == 200
    assert upload(client, "bad.json", b'{"specVersion": "1.6"}').status_code == 422
    assert client.get("/api/import/current").status_code == 404  # the old claims do not come back on a refresh
    assert upload(client, "huge.csv", b"location,type,claim,value\n" + b"x" * (1024 * 1024)).status_code == 422
    assert client.get("/api/import/current").status_code == 404
    imp = client.post("/api/import/demo").json()  # importing again works as usual
    assert client.get("/api/import/current").json()["id"] == imp["id"]


def test_upload_refused_for_not_being_logged_in_does_not_clear_the_import(client):
    assert client.post("/api/import/demo").status_code == 200
    cookies = dict(client.cookies)
    client.cookies.clear()
    assert upload(client, "bad.json", b"{").status_code == 401
    client.cookies.update(cookies)
    assert client.get("/api/import/current").status_code == 200


def test_empty_upload_of_any_file_type_is_refused_and_clears_the_import(client):
    # The screen sends an empty body when it refuses a file itself (wrong type, too large).
    for name in ("photo.png", "big.csv", "big.json"):
        assert client.post("/api/import/demo").status_code == 200
        assert upload(client, name, b"").status_code == 422
        assert client.get("/api/import/current").status_code == 404

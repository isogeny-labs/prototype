"""Curated catalog of established algorithms, libraries and implementation profiles.

Every entry is a published, standardised algorithm. Nothing here is invented, and no entry is described
as unconditionally secure or "quantum-proof". Sizes are definitional (from the standards); other
figures are qualitative and must be confirmed by evidence runs.

Purposes are kept strictly separate: a profile with purpose `firmware_signing` is never offered as a
replacement for `key_establishment` or `payload_encryption`, and vice versa.
"""

PURPOSES = {
    "firmware_signing": "Authenticating firmware images and update packages (digital signatures).",
    "token_signing": "Signing application tokens / API credentials (digital signatures).",
    "transport_security": "Protecting data in transit (TLS configuration).",
    "key_establishment": "Agreeing shared secrets (KEM / key exchange).",
    "payload_encryption": "Confidentiality + integrity of stored or transmitted payloads (AEAD).",
    "authentication": "Entity / message authentication (MACs, passwords).",
}

# family: classical security level claims come from the standards; quantum notes are qualitative.
PROFILES = {
    # ------------------------------------------------------------ firmware signing
    "rsa2048_pkcs1v15_sha256": {
        "purpose": "firmware_signing", "family": "RSA", "label": "RSA-2048 / PKCS#1 v1.5 / SHA-256",
        "standards": ["RFC 8017 (PKCS #1 v2.2)", "FIPS 186-5", "NIST SP 800-57 Part 1 Rev. 5 (112-bit strength)"],
        "sizes": {"signature_bytes": 256, "public_key_bytes": 294},
        "classical_security_bits": 112, "quantum": "Broken in principle by Shor's algorithm given a sufficiently large fault-tolerant quantum computer; no such machine is publicly known. No calendar date is asserted.",
        "transition_note": "NIST IR 8547 (draft, Nov 2024) proposes deprecating 112-bit-strength RSA/ECC after 2030 and disallowing after 2035.",
        "fixture": "firmware_signing", "fixture_params": {"scheme": "rsa2048_pkcs1v15_sha256"},
        "libraries": ["mbedTLS", "wolfSSL", "OpenSSL", "BoringSSL", "cryptography (Python)"],
        "platforms": ["Cortex-M (with bignum)", "Linux", "containers"],
        "implementation_notes": ["Verification requires a bignum implementation; verify is cheap relative to sign (e=65537).",
                                 "PKCS#1 v1.5 parsers have historically had lenient-padding bugs; verifying code must check the full encoded message."],
    },
    "rsa3072_pss_sha256": {
        "purpose": "firmware_signing", "family": "RSA", "label": "RSA-3072 / PSS / SHA-256",
        "standards": ["RFC 8017", "FIPS 186-5"], "sizes": {"signature_bytes": 384, "public_key_bytes": 422},
        "classical_security_bits": 128, "quantum": "Same exposure as all RSA to a large fault-tolerant quantum computer.",
        "transition_note": "128-bit strength: NIST IR 8547 draft proposes disallowing all quantum-vulnerable signatures after 2035.",
        "fixture": "firmware_signing", "fixture_params": {"scheme": "rsa3072_pss_sha256"},
        "libraries": ["mbedTLS", "wolfSSL", "OpenSSL"], "platforms": ["Cortex-M (with bignum)", "Linux"],
        "implementation_notes": ["PSS is the recommended RSA padding for new designs (RFC 8017 §8.1).", "Larger modulus increases verify time and key size relative to RSA-2048."],
    },
    "ecdsa_p256_sha256": {
        "purpose": "firmware_signing", "family": "ECDSA", "label": "ECDSA P-256 / SHA-256",
        "standards": ["FIPS 186-5", "SEC 2 v2 (secp256r1)", "RFC 6979 (deterministic nonces)"],
        "sizes": {"signature_bytes": 64, "public_key_bytes": 65}, "classical_security_bits": 128,
        "quantum": "Elliptic-curve discrete log is broken in principle by Shor's algorithm on a large fault-tolerant quantum computer.",
        "transition_note": "Same NIST IR 8547 draft timeline as RSA.",
        "fixture": "firmware_signing", "fixture_params": {"scheme": "ecdsa_p256_sha256"},
        "libraries": ["mbedTLS", "wolfSSL", "micro-ecc", "OpenSSL"], "platforms": ["Cortex-M0+/M3/M4", "Linux"],
        "implementation_notes": ["Small signatures and keys; verify cost higher than RSA verify on MCUs.", "Nonce generation quality is critical on the signer side; use RFC 6979 or hedged signing."],
    },
    "ed25519": {
        "purpose": "firmware_signing", "family": "EdDSA", "label": "Ed25519",
        "standards": ["RFC 8032", "FIPS 186-5 (EdDSA)"], "sizes": {"signature_bytes": 64, "public_key_bytes": 32},
        "classical_security_bits": 128, "quantum": "Same exposure as ECDSA.", "transition_note": "Same NIST IR 8547 draft timeline as RSA/ECDSA.",
        "fixture": "firmware_signing", "fixture_params": {"scheme": "ed25519"},
        "libraries": ["libsodium", "wolfSSL", "mbedTLS (3.x, via PSA)", "monocypher", "OpenSSL"], "platforms": ["Cortex-M", "Linux"],
        "implementation_notes": ["Deterministic signing; compact code in several embedded libraries.", "Signature malleability / verification-equation variants differ across libraries (RFC 8032 vs. ZIP-215 style); pick one and document it."],
    },
    "ml_dsa_44": {
        "purpose": "firmware_signing", "family": "ML-DSA", "label": "ML-DSA-44 (FIPS 204)",
        "standards": ["FIPS 204 (Aug 2024)"], "sizes": {"signature_bytes": 2420, "public_key_bytes": 1312},
        "classical_security_bits": None, "security_category": 2,
        "quantum": "Designed to resist known quantum attacks (lattice-based). Security is an active research area; no scheme is unconditionally secure.",
        "transition_note": "NIST-standardised post-quantum signature; CNSA 2.0 lists ML-DSA for software/firmware signing alongside LMS/XMSS.",
        "fixture": "firmware_signing", "fixture_params": {"scheme": "ml_dsa_44"},
        "libraries": ["liboqs", "pqm4 (Cortex-M4)", "wolfSSL (PQ build)", "mbedTLS (not yet, as of catalog date)", "dilithium-py (reference only)"],
        "platforms": ["Cortex-M4 with ~10s of KB RAM for verify", "Linux"],
        "implementation_notes": ["Signature ~2.4 KB: manifest/slot layout usually needs to change.", "Verification is fast on MCUs with vectorised implementations; stack usage must be measured on target."],
    },
    "ml_dsa_65": {
        "purpose": "firmware_signing", "family": "ML-DSA", "label": "ML-DSA-65 (FIPS 204)",
        "standards": ["FIPS 204 (Aug 2024)"], "sizes": {"signature_bytes": 3309, "public_key_bytes": 1952},
        "classical_security_bits": None, "security_category": 3,
        "quantum": "Designed to resist known quantum attacks (lattice-based); not unconditionally secure.",
        "transition_note": "Commonly recommended parameter set for general use; CNSA 2.0 lists ML-DSA-87 for national-security systems.",
        "fixture": "firmware_signing", "fixture_params": {"scheme": "ml_dsa_65"},
        "libraries": ["liboqs", "pqm4 (Cortex-M4)", "wolfSSL (PQ build)", "dilithium-py (reference only)"],
        "platforms": ["Cortex-M4+", "Linux"],
        "implementation_notes": ["Signature ~3.3 KB and public key ~2 KB: bootloader slot and flash layout must accommodate them."],
    },
    "ml_dsa_87": {
        "purpose": "firmware_signing", "family": "ML-DSA", "label": "ML-DSA-87 (FIPS 204)",
        "standards": ["FIPS 204 (Aug 2024)", "CNSA 2.0"], "sizes": {"signature_bytes": 4627, "public_key_bytes": 2592},
        "classical_security_bits": None, "security_category": 5,
        "quantum": "Designed to resist known quantum attacks; not unconditionally secure.", "transition_note": "CNSA 2.0 parameter set.",
        "fixture": "firmware_signing", "fixture_params": {"scheme": "ml_dsa_87"},
        "libraries": ["liboqs", "pqm4", "wolfSSL (PQ build)"], "platforms": ["Cortex-M4+ (RAM permitting)", "Linux"],
        "implementation_notes": ["Largest ML-DSA sizes; often impractical for small bootloader slots."],
    },
    "lms_sha256_h10_w8": {
        "purpose": "firmware_signing", "family": "LMS/HSS", "label": "LMS / HSS (SHA-256, H=10, W=8) — stateful hash-based",
        "standards": ["NIST SP 800-208", "RFC 8554", "CNSA 2.0 (recommended for firmware signing)"],
        "sizes": {"signature_bytes": 1456, "public_key_bytes": 56},
        "classical_security_bits": 128, "quantum": "Hash-based; security rests on the hash function. Widely regarded as the most conservative post-quantum signature option.",
        "transition_note": "CNSA 2.0 names LMS/XMSS as preferred for software/firmware signing; NIST requires HSM-grade state management for the signer.",
        "fixture": None, "fixture_params": {},
        "libraries": ["Cisco hash-sigs", "wolfSSL", "mbedTLS 3.x (LMS verify)", "OpenSSL 3.4+ (verify)"],
        "platforms": ["Cortex-M0+ and up (verify only needs SHA-256)", "Linux"],
        "implementation_notes": ["Signer must never reuse a one-time key: state management is the principal operational risk (SP 800-208 §8).",
                                 "No fixture in this MVP; evidence must be imported from a lab run or a future fixture."],
    },
    "slh_dsa_sha2_128s": {
        "purpose": "firmware_signing", "family": "SLH-DSA", "label": "SLH-DSA-SHA2-128s (FIPS 205) — stateless hash-based",
        "standards": ["FIPS 205 (Aug 2024)"], "sizes": {"signature_bytes": 7856, "public_key_bytes": 32},
        "classical_security_bits": 128, "quantum": "Hash-based; no signer state. Large signatures and slow signing.",
        "transition_note": "Conservative stateless option where ~8 KB signatures are acceptable.",
        "fixture": None, "fixture_params": {},
        "libraries": ["liboqs", "SPHINCS+ reference"], "platforms": ["Linux", "Cortex-M (verify)"],
        "implementation_notes": ["No fixture in this MVP; evidence must be imported."],
    },
    # ------------------------------------------------------------ application token signing
    "jws_rs256": {"purpose": "token_signing", "family": "RSA", "label": "JWS RS256 (RSA-2048 PKCS#1 v1.5 SHA-256)",
                  "standards": ["RFC 7518 §3.3", "RFC 8017"], "sizes": {"signature_bytes": 256, "public_key_bytes": 294},
                  "classical_security_bits": 112, "quantum": "Quantum-vulnerable (Shor).", "transition_note": "Same NIST IR 8547 draft timeline as RSA.",
                  "fixture": "app_service_crypto", "fixture_params": {"purpose": "token_signing", "profile": "rs256"},
                  "libraries": ["PyJWT", "jose", "jsonwebtoken", "OpenSSL"], "platforms": ["containers"],
                  "implementation_notes": ["Large tokens; slow signing relative to EdDSA.", "Verifier must pin the accepted `alg` list."]},
    "jws_ps256": {"purpose": "token_signing", "family": "RSA", "label": "JWS PS256 (RSA-2048 PSS SHA-256)",
                  "standards": ["RFC 7518 §3.5", "RFC 8017"], "sizes": {"signature_bytes": 256, "public_key_bytes": 294},
                  "classical_security_bits": 112, "quantum": "Quantum-vulnerable (Shor).", "transition_note": "Same as RS256.",
                  "fixture": "app_service_crypto", "fixture_params": {"purpose": "token_signing", "profile": "ps256"},
                  "libraries": ["PyJWT", "jose", "OpenSSL"], "platforms": ["containers"],
                  "implementation_notes": ["Randomised padding; preferred RSA padding for new designs."]},
    "jws_es256": {"purpose": "token_signing", "family": "ECDSA", "label": "JWS ES256 (ECDSA P-256 SHA-256)",
                  "standards": ["RFC 7518 §3.4", "FIPS 186-5"], "sizes": {"signature_bytes": 64, "public_key_bytes": 65},
                  "classical_security_bits": 128, "quantum": "Quantum-vulnerable (Shor).", "transition_note": "Same NIST IR 8547 draft timeline.",
                  "fixture": "app_service_crypto", "fixture_params": {"purpose": "token_signing", "profile": "es256"},
                  "libraries": ["PyJWT", "jose", "jsonwebtoken", "OpenSSL"], "platforms": ["containers"],
                  "implementation_notes": ["Compact tokens; widely supported by relying parties."]},
    "jws_eddsa": {"purpose": "token_signing", "family": "EdDSA", "label": "JWS EdDSA (Ed25519)",
                  "standards": ["RFC 8037", "RFC 8032"], "sizes": {"signature_bytes": 64, "public_key_bytes": 32},
                  "classical_security_bits": 128, "quantum": "Quantum-vulnerable (Shor).", "transition_note": "Same NIST IR 8547 draft timeline.",
                  "fixture": "app_service_crypto", "fixture_params": {"purpose": "token_signing", "profile": "eddsa"},
                  "libraries": ["PyJWT (>=2.0)", "jose", "OpenSSL >=1.1.1"], "platforms": ["containers"],
                  "implementation_notes": ["Fast signing and verification; relying parties must support EdDSA (RFC 8037)."]},
    # ------------------------------------------------------------ payload encryption
    "aead_aes128_gcm": {"purpose": "payload_encryption", "family": "AES-GCM", "label": "AES-128-GCM",
                        "standards": ["NIST SP 800-38D", "RFC 5116"], "sizes": {"key_bytes": 16, "overhead_bytes": 28},
                        "classical_security_bits": 128, "quantum": "Grover's algorithm gives at most a quadratic speed-up against the key; AES-128 is widely treated as acceptable but AES-256 is preferred where margin matters.",
                        "transition_note": "", "fixture": "app_service_crypto", "fixture_params": {"purpose": "payload_encryption", "profile": "aes128_gcm"},
                        "libraries": ["OpenSSL", "BoringSSL", "cryptography (Python)"], "platforms": ["containers", "x86 with AES-NI"],
                        "implementation_notes": ["Nonce reuse is catastrophic; 96-bit random nonces need a per-key message budget (SP 800-38D §8.3)."]},
    "aead_aes256_gcm": {"purpose": "payload_encryption", "family": "AES-GCM", "label": "AES-256-GCM",
                        "standards": ["NIST SP 800-38D", "RFC 5116", "CNSA 2.0"], "sizes": {"key_bytes": 32, "overhead_bytes": 28},
                        "classical_security_bits": 256, "quantum": "Larger key margin against Grover-type attacks; CNSA 2.0 choice.",
                        "transition_note": "", "fixture": "app_service_crypto", "fixture_params": {"purpose": "payload_encryption", "profile": "aes256_gcm"},
                        "libraries": ["OpenSSL", "BoringSSL", "cryptography (Python)"], "platforms": ["containers", "x86 with AES-NI"],
                        "implementation_notes": ["Same nonce discipline as AES-128-GCM."]},
    "aead_chacha20_poly1305": {"purpose": "payload_encryption", "family": "ChaCha20-Poly1305", "label": "ChaCha20-Poly1305",
                               "standards": ["RFC 8439"], "sizes": {"key_bytes": 32, "overhead_bytes": 28},
                               "classical_security_bits": 256, "quantum": "Symmetric; Grover-type speed-up only.",
                               "transition_note": "", "fixture": "app_service_crypto", "fixture_params": {"purpose": "payload_encryption", "profile": "chacha20_poly1305"},
                               "libraries": ["OpenSSL", "libsodium", "cryptography (Python)"], "platforms": ["containers", "CPUs without AES acceleration"],
                               "implementation_notes": ["Constant-time in software without special instructions; often faster than AES-GCM where AES-NI is absent."]},
    # ------------------------------------------------------------ key establishment (catalog only, no fixture)
    "kem_ecdh_p256": {"purpose": "key_establishment", "family": "ECDH", "label": "ECDH P-256", "standards": ["NIST SP 800-56A Rev. 3"],
                      "sizes": {"public_key_bytes": 65, "shared_secret_bytes": 32}, "classical_security_bits": 128,
                      "quantum": "Quantum-vulnerable (Shor).", "transition_note": "NIST IR 8547 draft timeline.", "fixture": None, "fixture_params": {},
                      "libraries": ["OpenSSL", "mbedTLS"], "platforms": ["all"], "implementation_notes": ["No fixture in this MVP."]},
    "kem_x25519": {"purpose": "key_establishment", "family": "X25519", "label": "X25519", "standards": ["RFC 7748"],
                   "sizes": {"public_key_bytes": 32, "shared_secret_bytes": 32}, "classical_security_bits": 128,
                   "quantum": "Quantum-vulnerable (Shor).", "transition_note": "NIST IR 8547 draft timeline.", "fixture": None, "fixture_params": {},
                   "libraries": ["OpenSSL", "libsodium"], "platforms": ["all"], "implementation_notes": ["No fixture in this MVP."]},
    "kem_ml_kem_768": {"purpose": "key_establishment", "family": "ML-KEM", "label": "ML-KEM-768 (FIPS 203)", "standards": ["FIPS 203 (Aug 2024)"],
                       "sizes": {"public_key_bytes": 1184, "ciphertext_bytes": 1088, "shared_secret_bytes": 32}, "classical_security_bits": None, "security_category": 3,
                       "quantum": "Designed to resist known quantum attacks (lattice-based); not unconditionally secure.", "transition_note": "Commonly deployed in hybrid with X25519 (e.g. X25519MLKEM768 in TLS).",
                       "fixture": None, "fixture_params": {}, "libraries": ["liboqs", "OpenSSL 3.5+", "BoringSSL"], "platforms": ["Linux", "containers"],
                       "implementation_notes": ["No fixture in this MVP; a KEM is never a substitute for a signature scheme."]},
}

LIBRARIES = {
    "mbedTLS": {"vendor": "Arm / TrustedFirmware", "notes": "Common on Cortex-M. 2.x branch is end-of-life; 3.x adds PSA Crypto API. PQC signature support not available in mainline as of the catalog date."},
    "wolfSSL": {"vendor": "wolfSSL Inc.", "notes": "Embedded TLS/crypto library with optional PQC builds (ML-DSA/ML-KEM via liboqs or native)."},
    "OpenSSL": {"vendor": "OpenSSL Project", "notes": "3.5+ includes ML-KEM/ML-DSA/SLH-DSA."},
    "liboqs": {"vendor": "Open Quantum Safe", "notes": "Reference-quality PQC implementations for prototyping; check per-algorithm maturity notes before production use."},
    "pqm4": {"vendor": "pqm4 project", "notes": "Optimised PQC implementations for Cortex-M4; research code, used for benchmarking."},
    "cryptography (Python)": {"vendor": "PyCA", "notes": "OpenSSL-backed Python library used by the application fixture."},
    "dilithium-py": {"vendor": "community", "notes": "Pure-Python ML-DSA reference used by the fixtures. NOT production-grade; timing not representative."},
}

# Qualitative cost classes used ONLY to rank remediation candidates when a timing/throughput requirement failed.
# They are catalog hints, not measurements; every recommendation says the figure must be confirmed by a run.
PERF_CLASS = {
    "RSA": {"sign": "slow", "verify": "fast"},
    "ECDSA": {"sign": "fast", "verify": "medium"},
    "EdDSA": {"sign": "fast", "verify": "fast"},
    "ML-DSA": {"sign": "medium", "verify": "fast"},
    "LMS/HSS": {"sign": "medium", "verify": "fast"},
    "SLH-DSA": {"sign": "slow", "verify": "medium"},
    "AES-GCM": {"encrypt": "fast", "decrypt": "fast"},
    "ChaCha20-Poly1305": {"encrypt": "fast", "decrypt": "fast"},
}
for _pid, _p in PROFILES.items():
    _p["perf_class"] = PERF_CLASS.get(_p["family"], {})

CATALOG_DATE = "2026-10"


def profiles_for_purpose(purpose: str) -> dict:
    return {k: v for k, v in PROFILES.items() if v["purpose"] == purpose}


def profile(pid: str) -> dict | None:
    p = PROFILES.get(pid)
    return {"id": pid, **p} if p else None


def catalog_summary() -> dict:
    return {"catalog_date": CATALOG_DATE, "purposes": PURPOSES,
            "profiles": [{"id": k, **v} for k, v in PROFILES.items()], "libraries": LIBRARIES}


def quantum_vulnerable(pid: str) -> bool:
    p = PROFILES.get(pid, {})
    return p.get("family") in ("RSA", "ECDSA", "EdDSA", "ECDH", "X25519")


def guess_profile(algorithm: str, parameters: dict | None, purpose: str | None) -> str | None:
    """Map a free-text inventory algorithm to a catalog profile id (best effort, never authoritative)."""
    a = (algorithm or "").lower().replace("_", "-").replace(" ", "")
    params = parameters or {}
    bits = str(params.get("modulus_bits") or params.get("key_bits") or params.get("bits") or "")
    purpose = purpose or ""
    if "rsa" in a:
        if purpose == "token_signing":
            return "jws_ps256" if "pss" in a or "pss" in str(params).lower() else "jws_rs256"
        if "3072" in a or bits == "3072":
            return "rsa3072_pss_sha256"
        return "rsa2048_pkcs1v15_sha256"
    if "ecdsa" in a or "p-256" in a or "p256" in a or "secp256r1" in a:
        return "jws_es256" if purpose == "token_signing" else "ecdsa_p256_sha256"
    if "ed25519" in a or "eddsa" in a:
        return "jws_eddsa" if purpose == "token_signing" else "ed25519"
    if "ml-dsa" in a or "dilithium" in a:
        for lvl in ("44", "65", "87"):
            if lvl in a:
                return f"ml_dsa_{lvl}"
        return "ml_dsa_65"
    if "lms" in a or "hss" in a:
        return "lms_sha256_h10_w8"
    if "slh" in a or "sphincs" in a:
        return "slh_dsa_sha2_128s"
    if "aes" in a and "gcm" in a:
        return "aead_aes256_gcm" if "256" in a or bits == "256" else "aead_aes128_gcm"
    if "chacha" in a:
        return "aead_chacha20_poly1305"
    if "x25519" in a:
        return "kem_x25519"
    if "ecdh" in a:
        return "kem_ecdh_p256"
    if "ml-kem" in a or "kyber" in a:
        return "kem_ml_kem_768"
    return None

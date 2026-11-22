"""TLS SignatureScheme numbers (IANA), the names shown on screen, and which family each belongs to (phase 4b).
Pure data with no imports, so that both the TLS engine (pqtls.py) and the reviewer can use it."""

SIGNATURE_SCHEMES = {
    0x0403: "ECDSA P-256 with SHA-256",
    0x0503: "ECDSA P-384 with SHA-384",
    0x0603: "ECDSA P-521 with SHA-512",
    0x0804: "RSA-PSS with SHA-256",
    0x0805: "RSA-PSS with SHA-384",
    0x0806: "RSA-PSS with SHA-512",
    0x0809: "RSA-PSS (PSS key) with SHA-256",
    0x080A: "RSA-PSS (PSS key) with SHA-384",
    0x080B: "RSA-PSS (PSS key) with SHA-512",
    0x0401: "RSA PKCS#1 with SHA-256",
    0x0501: "RSA PKCS#1 with SHA-384",
    0x0601: "RSA PKCS#1 with SHA-512",
    0x0807: "Ed25519",
    0x0808: "Ed448",
    0x0904: "ML-DSA-44",
    0x0905: "ML-DSA-65",
    0x0906: "ML-DSA-87",
}
POST_QUANTUM_SCHEMES = (0x0904, 0x0905, 0x0906)


def scheme_family(number: int | None) -> str | None:
    """ "post_quantum", "classical", or None when the number is not one this version knows."""
    if number in POST_QUANTUM_SCHEMES:
        return "post_quantum"
    return "classical" if number in SIGNATURE_SCHEMES else None

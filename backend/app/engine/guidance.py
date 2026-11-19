"""Current NIST guidance, kept as a config value with its source links (not hard-coded into a rule).
The whole value is copied into the locked certificate test, so a result always says which guidance it used."""
from __future__ import annotations

from typing import Any

NIST_GUIDANCE = {
    "id": "nist-2026",
    "minimum_bits": {"RSA": 2048, "EC": 224},
    "minimum_source": {"title": "NIST SP 800-131A Rev. 2", "url": "https://csrc.nist.gov/pubs/sp/800/131/a/r2/final"},
    "notes": [
        {"applies_to": ["ECDSA P-256", "ECDSA P-384", "ECDSA P-521", "RSA"],
         "text": "NIST plans to retire this algorithm as part of the move to post-quantum cryptography. "
                 "Under NIST IR 8547 (final, Oct 2026), ECDSA including P-256 is deprecated after 2030 and disallowed after 2035.",
         "source": {"title": "NIST IR 8547 (final, published October 27, 2026)", "url": "https://csrc.nist.gov/pubs/ir/8547/final"}},
    ],
}

# Links the app is willing to show (only our own config, never a link taken from a file or a result).
OWN_LINKS = (NIST_GUIDANCE["minimum_source"]["url"], NIST_GUIDANCE["notes"][0]["source"]["url"])

# Phase 4a. Published sizes of the post-quantum algorithms, each with its source, for numbers that were not measured.
# A number on screen is always tagged: "measured" (on the system), "measured on our test server", or "published: <source>".
PQ_PUBLISHED = {
    "ml_kem_768": {"encapsulation_key_bytes": 1184, "ciphertext_bytes": 1088, "tag": "published: FIPS 203",
                   "source": {"title": "FIPS 203, Module-Lattice-Based Key-Encapsulation Mechanism Standard (ML-KEM-768 sizes)",
                              "url": "https://csrc.nist.gov/pubs/fips/203/final"}},
    # X25519MLKEM768: the ML-KEM-768 key (or ciphertext) and a 32-byte X25519 share, sent together.
    "x25519_ml_kem_768": {"client_share_bytes": 1216, "server_share_bytes": 1120, "tag": "published: FIPS 203 + X25519",
                          "source": {"title": "FIPS 203 (ML-KEM-768) plus a 32-byte X25519 share (RFC 7748)",
                                     "url": "https://csrc.nist.gov/pubs/fips/203/final"}},
    "ml_dsa_65": {"public_key_bytes": 1952, "signature_bytes": 3309, "tag": "published: FIPS 204",
                  "source": {"title": "FIPS 204, Module-Lattice-Based Digital Signature Standard (ML-DSA-65 sizes)",
                             "url": "https://csrc.nist.gov/pubs/fips/204/final"}},
}
# NIST's dates for today's public-key algorithms (the note above carries the source).
PQ_DATES = {"deprecated_after": 2030, "disallowed_after": 2035, "tag": "reference: NIST IR 8547",
            "source": NIST_GUIDANCE["notes"][0]["source"]}
OWN_LINKS = OWN_LINKS + tuple(v["source"]["url"] for v in PQ_PUBLISHED.values())

# Phase 6d (Change watch). Names of old cryptography that a flag looks for in the lines a developer's change adds.
# A flag is something to look at, never a result: the app has not tested what such a line does. Each name carries the
# publication that retired or restricted it, and the ways it is commonly written (regular expressions, matched without
# regard to upper and lower case). Kept as a config value with its sources, like the NIST guidance above.
_NOT_MORE = r"(?![A-Za-z0-9]|[._]\d)"     # the name ends here: "TLS 1.0" is not found inside "TLS 1.0.2" or "TLSv1.2"
_SP_800_131A = {"title": "NIST SP 800-131A Rev. 2", "url": "https://csrc.nist.gov/pubs/sp/800/131/a/r2/final"}   # (the minimum's source above)
OLD_CRYPTOGRAPHY: list[dict[str, Any]] = [
    {"word": "SSL 3.0", "written": [r"ssl[ _-]?v?3(?:[._]0)?" + _NOT_MORE],
     "source": {"title": "RFC 7568, Deprecating Secure Sockets Layer Version 3.0", "url": "https://www.rfc-editor.org/rfc/rfc7568"}},
    {"word": "TLS 1.0", "written": [r"tls[ _-]?v?1(?:[._]0)?" + _NOT_MORE],
     "source": {"title": "RFC 8996, Deprecating TLS 1.0 and TLS 1.1", "url": "https://www.rfc-editor.org/rfc/rfc8996"}},
    {"word": "TLS 1.1", "written": [r"tls[ _-]?v?1[._]1" + _NOT_MORE],
     "source": {"title": "RFC 8996, Deprecating TLS 1.0 and TLS 1.1", "url": "https://www.rfc-editor.org/rfc/rfc8996"}},
    {"word": "SHA-1", "written": [r"sha[ _-]?1(?!\d)"],
     "source": dict(_SP_800_131A)},
    {"word": "MD5", "written": [r"md[ _-]?5(?!\d)"],
     "source": {"title": "RFC 6151, Updated Security Considerations for the MD5 Message-Digest and the HMAC-MD5 Algorithms",
                "url": "https://www.rfc-editor.org/rfc/rfc6151"}},
    {"word": "RC4", "written": [r"rc[ _-]?4(?!\d)", r"arcfour"],
     "source": {"title": "RFC 7465, Prohibiting RC4 Cipher Suites", "url": "https://www.rfc-editor.org/rfc/rfc7465"}},
    {"word": "3DES", "written": [r"3[ _-]?des", r"triple[ _-]?des", r"des[ _-]?ede3?", r"tdea"],
     "source": dict(_SP_800_131A)},
]
OWN_LINKS = OWN_LINKS + tuple(sorted({w["source"]["url"] for w in OLD_CRYPTOGRAPHY} - set(OWN_LINKS)))

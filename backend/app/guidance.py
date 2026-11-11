"""Current NIST guidance, kept as a config value with its source links (not hard-coded into a rule).
The whole value is copied into the locked certificate test, so a result always says which guidance it used."""
from __future__ import annotations

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

"""Real crypto libraries as test subjects (phase 4c): software written by others, in exact published versions.

Everything about them is fixed here: which library versions exist, which container image each runs in, where
the library's own files come from and their fingerprints, and the public advisories that are known for a
version. Nothing in an uploaded file can add to these tables.

A real library runs ONLY in isolated mode, each family in its own locked-down container image. The image is
built by `python -m app.prepare` (the only code that may download): on the pinned Python base, with the
library's own files copied in from its pinned source, plus one short wrapper that translates the adapter's
JSON to the library's own calls (demo/real-libraries/<family>/). The crypto is the library's.

An advisory shown beside a result is information from its publisher. It never sets a result: results come
only from the tests."""
from __future__ import annotations

from app.config import DEMO_DIR, OPENSSL_IMAGE

REAL_DIR = DEMO_DIR / "real-libraries"
NEEDS_ISOLATED = "Real software from outside runs only in isolated mode (Docker)"
IMAGE_REPOSITORY = "evidence-lab-real"

# ---------------------------------------------------------------- where each family's files come from (pinned)
JDK_AFFECTED_IMAGE = "eclipse-temurin@sha256:1db19705a14622cc0bcdd19bf4c9c3b3224aad3ffb37867029d3330c92c02c68"   # 17.0.2_8-jdk-alpine
JDK_FIXED_IMAGE = "eclipse-temurin@sha256:85c33b8a96bf36a5335adf754b45575df7df7935a84db560aa8ec16fd40dbf36"      # 17.0.3_7-jdk-alpine
NODE_IMAGE = "node@sha256:1314fb30ec37592d5845e5a160d522c0e680972aa534549940b8d73bde88481a"                       # 22-alpine (Node 22.23.5)
_PYPI = "https://files.pythonhosted.org/packages"
_NPM = "https://registry.npmjs.org"


def _npm(name: str, version: str, integrity: str) -> dict:
    return {"file": f"{name}-{version}.tgz", "url": f"{_NPM}/{name}/-/{name}-{version}.tgz", "sha512_base64": integrity}


# family -> the folder of its wrapper, the pinned images its Dockerfile copies the library from (as build
# arguments), and the pinned files the prepare step downloads into the build (checked before they are used).
FAMILIES: dict[str, dict] = {
    "openssl": {"label": "OpenSSL", "images": {"LIBRARY_IMAGE": OPENSSL_IMAGE}, "downloads": []},
    "java": {"label": "Java", "images": {"JDK_AFFECTED": JDK_AFFECTED_IMAGE, "JDK_FIXED": JDK_FIXED_IMAGE}, "downloads": []},
    "python-ecdsa": {"label": "python-ecdsa", "images": {}, "downloads": [
        {"file": "ecdsa-0.13.2-py2.py3-none-any.whl",
         "url": f"{_PYPI}/23/a8/8aa68e70959e1287da9154e5164bb8bd5dd7025e41ae54e8d177b8d165c9/ecdsa-0.13.2-py2.py3-none-any.whl",
         "sha256": "20c17e527e75acad8f402290e158a6ac178b91b881f941fc6ea305bfdfb9657c"},
        {"file": "ecdsa-0.13.3-py2.py3-none-any.whl",
         "url": f"{_PYPI}/a6/81/2b170b460c84fdc8700cf08aa077ac6a9ff41f4ad3f05d0b3a64ba9f8f2e/ecdsa-0.13.3-py2.py3-none-any.whl",
         "sha256": "9814e700890991abeceeb2242586024d4758c8fc18445b194a49bd62d85861db"}]},
    "elliptic": {"label": "elliptic", "images": {"NODE_IMAGE": NODE_IMAGE}, "downloads": [
        _npm("elliptic", "6.5.6", "mpzdtpeCLuS3BmE3pO3Cpp5bbjlOPY2Q0PgoF+Od1XZrHLYI28Xe3ossCmYCQt11FQKEYd9+PF8jymTvtWJSHQ=="),
        _npm("elliptic", "6.5.7", "ESVCtTwiA+XhY3wyh24QqRGBoP3rEdDUl3EDUUo9tft074fi19IrdpH7hLCMMP3CIj7jb3W96rn8lt/BqIlt5Q=="),
        _npm("bn.js", "4.12.5", "3aRg6/JxfffFD+OlOjOFR3Vo79l39ooBTFucxx+MT3dhCtzn3EmiUPQo+6/OZuI2jbXi3YKgmiTFBgChQMwIRQ=="),
        _npm("brorand", "1.1.0", "cKV8tMCEpQs4hK/ik71d6LrPOnpkpGBR0wzxqr68g2m/LB2GxVYQroAjMJZRVM1Y4BCjCKc3vAamxSzOY2RP+w=="),
        _npm("hash.js", "1.1.7", "taOaskGt4z4SOANNseOviYDvjEJinIkRgmp7LbKP2YTTmVxWBl87s/uzK9r+44BclBSp2X7K1hqeNfz9JbBeXA=="),
        _npm("hmac-drbg", "1.0.1", "Tti3gMqLdZfhOQY1Mzf/AanLiqh1WTiJgEj26ZuYQ9fbkLomzGchCws4FyrSd4VkpBfiNhaE1On+lOz894jvXg=="),
        _npm("inherits", "2.0.4", "k/vGaX4/Yla3WzyMCvTQOXYeIHvqOKtnqBduzTHpzpQZzAskKMhZ2K+EnBiSM9zGSoIFeMpXKxa4dYeZIQqewQ=="),
        _npm("minimalistic-assert", "1.0.1", "UtJcAD4yEaGtjPezWuO9wC4nwUnVH/8/Im3yEHQP4b67cXlD/Qr9hdITCU1xDbSEXg2XKNaP8jsReV7vQd00/A=="),
        _npm("minimalistic-crypto-utils", "1.0.1", "JIYlbt6g8i5jKfJ3xz7rF0LXmv2TkDxBLUkiBeZ7bAx4GnnNMr8xFpGnOxn6GhTEHx3SjRrZEoU+j04prX1ktg==")]},
}

# ---------------------------------------------------------------- public advisories (information, never a result)
ADVISORIES: dict[str, dict] = {
    "CVE-2022-21449": {"text": "Java 15 to 18 accept a blank ECDSA signature (r = 0, s = 0). Fixed in 17.0.3.",
                       "link": "OpenJDK advisory, 19 April 2022", "url": "https://openjdk.org/groups/vulnerability/advisories/2022-04-19",
                       "covered": "The Independent exam and the Attacker tricks test both try a blank signature."},
    "CVE-2019-14859": {"text": "python-ecdsa before 0.13.3 accepts signatures with malformed encodings. Fixed in 0.13.3.",
                       "link": "GitHub advisory GHSA-8qxj-f9rh-9fg2", "url": "https://github.com/advisories/GHSA-8qxj-f9rh-9fg2",
                       "covered": "The Independent exam tries many malformed encodings; Attacker tricks tries a few."},
    "CVE-2019-14853": {"text": "python-ecdsa before 0.13.3 can stop with an unexpected error on a malformed signature. Fixed in 0.13.3.",
                       "link": "NVD, CVE-2019-14853", "url": "https://nvd.nist.gov/vuln/detail/CVE-2019-14853",
                       "covered": "These tests ask accept or reject only. A crash is not accepted, so it shows as a note under Also noticed, not as a result.",
                       "missed_by": ()},
    "CVE-2024-42460": {"text": "elliptic 6.5.6 does not check the leading bit of r and s in an ECDSA signature. Fixed in 6.5.7.",
                       "link": "GitHub advisory GHSA-977x-g7h5-7qgw", "url": "https://github.com/advisories/GHSA-977x-g7h5-7qgw",
                       "covered": "The Independent exam has one such case (a number written without its leading zero). Attacker tricks has none: a known gap of our short list.",
                       "missed_by": ("bad_signatures",)},
    "CVE-2024-42461": {"text": "elliptic 6.5.6 allows BER-encoded ECDSA signatures. Fixed in 6.5.7.",
                       "link": "GitHub advisory GHSA-49q7-c7j4-3p7m", "url": "https://github.com/advisories/GHSA-49q7-c7j4-3p7m",
                       "covered": "Not caught by these tests. The loose length form it allows needs a signature longer than 127 bytes, and a P-256 signature is at most 72.",
                       "missed_by": ("official_vectors", "bad_signatures")},
    "CVE-2024-42459": {"text": "elliptic 6.5.6 does not check the length of an EdDSA signature. Fixed in 6.5.7.",
                       "link": "GitHub advisory GHSA-f7q4-pwc6-w24p", "url": "https://github.com/advisories/GHSA-f7q4-pwc6-w24p",
                       "covered": "Not caught by these tests. It is in EdDSA, and this wrapper covers ECDSA P-256 only.",
                       "missed_by": ("official_vectors", "bad_signatures")},
}
ADVISORY_LINKS = tuple(a["url"] for a in ADVISORIES.values())

# ---------------------------------------------------------------- the libraries, as a file names them
# name -> family, the screen name, its versions oldest first, the algorithms its wrapper offers, which version
# fixes which, the advisories known for a version, and whether it can make post-quantum signatures at all.
LIBRARIES: dict[str, dict] = {
    "openjdk": {"family": "java", "label": "Java (OpenJDK, Temurin build)", "versions": ["17.0.2", "17.0.3"],
                "algorithms": ("ECDSA P-256",), "fixed_in": {"17.0.2": "17.0.3"},
                "advisories": {"17.0.2": ("CVE-2022-21449",)}, "distribution": {"17.0.2": "Temurin 17.0.2+8", "17.0.3": "Temurin 17.0.3+7"}},
    "python-ecdsa": {"family": "python-ecdsa", "label": "python-ecdsa", "versions": ["0.13.2", "0.13.3"],
                     "algorithms": ("ECDSA P-256",), "fixed_in": {"0.13.2": "0.13.3"},
                     "advisories": {"0.13.2": ("CVE-2019-14859", "CVE-2019-14853")}, "distribution": {}},
    "elliptic": {"family": "elliptic", "label": "elliptic (npm)", "versions": ["6.5.6", "6.5.7"],
                 "algorithms": ("ECDSA P-256",), "fixed_in": {"6.5.6": "6.5.7"},
                 "advisories": {"6.5.6": ("CVE-2024-42460", "CVE-2024-42461", "CVE-2024-42459")}, "distribution": {}},
    "openssl": {"family": "openssl", "label": "OpenSSL", "versions": ["3.5.9"],
                "algorithms": ("ECDSA P-256", "ML-DSA-65", "ML-KEM-768"), "fixed_in": {}, "advisories": {}, "distribution": {}},
}
PQ_SIGNATURE = "ML-DSA-65"
PQ_KEY_EXCHANGE = "ML-KEM-768"


def library(name: object, version: object) -> dict | None:
    """Exact match on name and version only, as for the demo components."""
    if not isinstance(name, str) or not isinstance(version, str):
        return None
    found = LIBRARIES.get(name)
    return found if found is not None and version in found["versions"] else None


def subject_key(name: str, version: str) -> str:
    if library(name, version) is None:
        raise ValueError("not a registered real library")
    return f"{name}-{version}"


def family_of(name: object, version: object) -> str | None:
    found = library(name, version)
    return found["family"] if found else None


def family_of_subject(key: str) -> str | None:
    """The family whose image holds this subject key ("openjdk-17.0.2", "control-slow:openjdk-17.0.2")."""
    bare = key.split(":", 1)[-1]
    for name, lib in LIBRARIES.items():
        if any(bare == f"{name}-{v}" for v in lib["versions"]):
            return lib["family"]
    return None


def advisories(name: object, version: object) -> list[dict]:
    found = library(name, version)
    return [{"id": cve, **ADVISORIES[cve]} for cve in (found["advisories"].get(version, ()) if found else ())]


def fixed_version(name: object, version: object) -> str | None:
    found = library(name, version)
    return found["fixed_in"].get(version) if found else None


def offers(name: object, version: object, algorithm: str) -> bool:
    found = library(name, version)
    return bool(found) and algorithm in found["algorithms"]

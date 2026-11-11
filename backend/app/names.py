"""Turning the many spellings of algorithm, TLS version and group names into one plain spelling."""
from __future__ import annotations

import re

TLS_VERSIONS = ["TLS 1.0", "TLS 1.1", "TLS 1.2", "TLS 1.3"]

_CURVES = {
    "P256": "P-256", "SECP256R1": "P-256", "PRIME256V1": "P-256", "NISTP256": "P-256",
    "P384": "P-384", "SECP384R1": "P-384", "NISTP384": "P-384",
    "P521": "P-521", "SECP521R1": "P-521", "NISTP521": "P-521",
}
# Key-exchange groups we can probe on TLS 1.3 -> name the openssl command line understands.
GROUPS = {
    "X25519": "X25519", "P-256": "P-256", "P-384": "P-384", "P-521": "P-521",
    "X448": "X448", "ffdhe2048": "ffdhe2048", "ffdhe3072": "ffdhe3072",
}


def _compact(text: object) -> str:
    return re.sub(r"[\s_\-./@]+", "", str(text or "")).upper()


def normalize_tls_version(text: object) -> str | None:
    c = re.sub(r"[\s\-]+", "", str(text or "")).upper().replace("_", ".")
    m = re.fullmatch(r"(?:TLS)?V?(1(?:\.[0-3])?)", c)
    if not m:
        return None
    v = m.group(1)
    return f"TLS {v if '.' in v else v + '.0'}"


def normalize_curve(text: object) -> str | None:
    return _CURVES.get(_compact(text))


def normalize_group(text: object) -> str | None:
    c = _compact(text)
    if c in _CURVES:
        return _CURVES[c]
    for name in GROUPS:
        if _compact(name) == c:
            return name
    return None


def normalize_algorithm(name: object, curve: object = None, size: object = None) -> str | None:
    """'ECDSA-P256', 'ecdsa' + 'secp256r1', 'SHA256withECDSA' + 'prime256v1' -> 'ECDSA P-256'.
    'RSA-2048' -> 'RSA 2048'. Returns None when the spelling is not one we know for certain."""
    c = _compact(name)
    if not c:
        return None
    if "ED25519" in c:
        return "Ed25519"
    if "ED448" in c:
        return "Ed448"
    stripped = re.sub(r"SHA3?\d{1,3}", "", c).replace("WITH", "")
    if "ECDSA" in stripped or stripped in ("EC", "ECC"):
        found = normalize_curve(curve) if curve else None
        if not found:
            rest = stripped.replace("ECDSA", "")
            found = _CURVES.get(rest)
        return f"ECDSA {found}" if found else None
    if "RSA" in stripped:
        bits = None
        if size is not None and re.fullmatch(r"\d{3,5}", str(size).strip()):
            bits = int(str(size).strip())
        else:
            m = re.search(r"(\d{3,5})", stripped)
            if m:
                bits = int(m.group(1))
        return f"RSA {bits}" if bits else None
    return None


def same_algorithm(a: object, b: object) -> bool:
    """Exact match after normalising spelling. Unknown names must match letter for letter."""
    na, nb = normalize_algorithm(a), normalize_algorithm(b)
    if na or nb:
        return na is not None and na == nb
    return bool(_compact(a)) and _compact(a) == _compact(b)


def clean_text(value: object, limit: int = 200) -> str:
    """File content shown on screen: printable, single line, bounded length. It is only ever data."""
    s = "".join(ch if ch.isprintable() else " " for ch in str(value))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def join_and(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]

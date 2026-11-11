"""One exact way to write a record as bytes, so its SHA-256 means something.

canonical_bytes: keys sorted, no spaces, UTF-8, no NaN. loads_strict: reads JSON and refuses
duplicate keys, NaN / Infinity and anything after the value."""
from __future__ import annotations

import hashlib
import json


def canonical_bytes(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_hex(obj: object) -> str:
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate key {key!r}")
        out[key] = value
    return out


def _no_constant(name):
    raise ValueError(f"{name} is not allowed")


def loads_strict(raw: bytes) -> object:
    """Parse UTF-8 JSON. Raises ValueError for duplicate keys, NaN / Infinity, bad UTF-8 or trailing data."""
    if isinstance(raw, str):
        text = raw
    else:
        try:
            text = bytes(raw).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("not valid UTF-8") from exc
    return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)

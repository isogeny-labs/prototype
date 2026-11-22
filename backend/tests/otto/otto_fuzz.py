"""Damaged copies for the seeded fuzz tests of Otto's file readers (the snapshot, a recorded answer, a test pack).
No new package: random only."""
from __future__ import annotations

import random

ODD = [None, 0, -1, 1e308, True, "", "x" * 5000, [], {}, [None], {"a": {"b": []}}, "../../etc/passwd", "sha256:" + "0" * 64,
       "https://example.invalid/x", "CVE-0000-0000", ["168", "99999"], "0" * 64, "2026-13-45", {"schema": "other"}]


def damage_bytes(rng: random.Random, data: bytes) -> bytes:
    b = bytearray(data)
    for _ in range(rng.randint(1, 8)):
        op = rng.randrange(4)
        i = rng.randrange(len(b)) if b else 0
        if op == 0 and b:
            del b[i:i + rng.randint(1, 40)]
        elif op == 1:
            b[i:i] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 12)))
        elif op == 2 and b:
            b[i] = rng.randrange(256)
        else:
            b = b[: rng.randrange(len(b) + 1)]
    return bytes(b)


def damage_json(rng: random.Random, value):
    """Change one value somewhere in the document to an odd one, keeping it JSON."""
    if isinstance(value, dict) and value and rng.random() < 0.85:
        k = rng.choice(list(value))
        return {**value, k: damage_json(rng, value[k])}
    if isinstance(value, list) and value and rng.random() < 0.85:
        i = rng.randrange(len(value))
        return value[:i] + [damage_json(rng, value[i])] + value[i + 1:]
    return rng.choice(ODD)

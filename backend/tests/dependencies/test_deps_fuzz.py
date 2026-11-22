"""Phase 4d: a seeded run of damaged copies of the demo lists through the reader. The only allowed outcomes are a
plain refusal (one ImportFileError) or a normal read, each within a time limit. No new package: random only."""
import json
import random
import time
from pathlib import Path

import pytest

from app.dependencies.tree import build_tree
from app.importer.common import ImportFileError
from app.importer.sbom import read_dependency_list
from app.knowledge.base import knowledge_base

DEMO = Path(__file__).resolve().parents[3] / "demo"
SEEDS = {"dependencies-demo.cdx.json": 20261116, "dependencies-demo.spdx.json": 20261117}
COPIES = 300
TIME_LIMIT = 2.0


def _damage_bytes(rng: random.Random, data: bytes) -> bytes:
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


ODD = [None, 0, -1, 1e308, True, "", "x" * 2000, [], {}, [None], {"a": {"b": []}}, "pkg:", "../../etc/passwd", "1.0" * 50]


def _damage_json(rng: random.Random, value):
    """Change one value somewhere in the document to an odd one, keeping it JSON."""
    if isinstance(value, dict) and value and rng.random() < 0.85:
        k = rng.choice(list(value))
        return {**value, k: _damage_json(rng, value[k])}
    if isinstance(value, list) and value and rng.random() < 0.85:
        i = rng.randrange(len(value))
        return value[:i] + [_damage_json(rng, value[i])] + value[i + 1:]
    return rng.choice(ODD)


@pytest.mark.parametrize("name", sorted(SEEDS))
def test_damaged_copies_are_read_or_refused_plainly(name):
    original = (DEMO / name).read_bytes()
    doc = json.loads(original)
    rng = random.Random(SEEDS[name])
    kb = knowledge_base()
    outcomes = {"read": 0, "refused": 0}
    for n in range(COPIES):
        data = _damage_bytes(rng, original) if n % 2 else json.dumps(_damage_json(rng, doc)).encode()
        start = time.monotonic()
        try:
            dl = read_dependency_list(data)
            tree = build_tree(dl, [("acme-sign", "1.4.2")])
            for r in tree.rows:                      # the lookup must take whatever the list says, too
                kb.look_up(r.purl, r.name, r.version)
            outcomes["read"] += 1
        except ImportFileError as exc:
            message = str(exc)
            assert message and "\n" not in message and "Traceback" not in message and len(message) < 400
            outcomes["refused"] += 1
        assert time.monotonic() - start < TIME_LIMIT, f"copy {n} took too long"
    assert outcomes["read"] > 0 and outcomes["refused"] > 0, outcomes

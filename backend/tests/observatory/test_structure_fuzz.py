"""A seeded run of damaged copies of the demo scanner file through the reader of its structure, and on to the map's
layout. The only allowed outcomes are a plain refusal (one ImportFileError, the claim reader's own or this reader's) or
a normal read, each within a time limit. Whatever is read is still only data: short text, known kinds, references
between things the file holds. No new package: random only."""

import json
import random
import time

from app.config import DEMO_CBOM
from app.importer import structure as S
from app.importer.cbom import read_cbom
from app.importer.common import ImportFileError
from app.observatory import layout as L

SEED = 20261126
COPIES = 400
TIME_LIMIT = 2.0
ODD = [
    None,
    0,
    -1,
    1e308,
    True,
    "",
    "x" * 5000,
    [],
    {},
    [None],
    {"a": {"b": []}},
    "../../etc/passwd",
    "a\x00b",
    "https://localhost:99999",
    "localhost:8443",
    "alg-ecdsa-p256",
    "svc-token-signing",
    ["alg-ecdsa-p256", "cert-server", "cert-server", 7, None],
    {"bom-ref": "lib-acme-sign", "name": "again"},
    "\ud800",
]
KINDS = {S.ALGORITHM, S.PROTOCOL, S.CERTIFICATE, S.MATERIAL}


def _damage_bytes(rng: random.Random, data: bytes) -> bytes:
    b = bytearray(data)
    for _ in range(rng.randint(1, 8)):
        op = rng.randrange(4)
        i = rng.randrange(len(b)) if b else 0
        if op == 0 and b:
            del b[i : i + rng.randint(1, 40)]
        elif op == 1:
            b[i:i] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 12)))
        elif op == 2 and b:
            b[i] = rng.randrange(256)
        else:
            b = b[: rng.randrange(len(b) + 1)]
    return bytes(b)


def _damage_json(rng: random.Random, value):
    """Change one value somewhere in the document to an odd one, keeping it JSON."""
    if isinstance(value, dict) and value and rng.random() < 0.85:
        k = rng.choice(list(value))
        return {**value, k: _damage_json(rng, value[k])}
    if isinstance(value, list) and value and rng.random() < 0.85:
        i = rng.randrange(len(value))
        return value[:i] + [_damage_json(rng, value[i])] + value[i + 1 :]
    return rng.choice(ODD)


def _is_whole(found: S.Structure) -> None:
    """What was read is only data, and holds together."""
    parts = [*found.services, *found.software, *([found.top] if found.top is not None else [])]
    known = {p.key for p in parts} | {a.key for a in found.assets}
    assert len(known) == len(parts) + len(found.assets)  # every key names one thing
    for p in parts:
        assert isinstance(p.name, str) and 0 < len(p.name) <= 100 and "\n" not in p.name and "\x00" not in p.name
        assert p.version is None or (isinstance(p.version, str) and len(p.version) <= 50)
        assert all(isinstance(a, str) and ":" in a for a in p.addresses)
    for a in found.assets:
        assert a.kind in KINDS and len(a.name) <= 80
        assert a.kind != S.ALGORITHM or (isinstance(a.algorithm, str) and a.algorithm)
    assert all(e.source in known and e.target in known and e.source != e.target for e in found.edges)
    algorithms = {a.key for a in found.assets if a.kind == S.ALGORITHM}
    for use in found.uses:
        assert use.algorithm in algorithms
        assert use.place_kind == S.ADDRESS or use.place in known
    for lines in found.lines.values():
        assert len(lines) <= S.MAX_LINES and all(len(text) <= S.LINE_LIMIT and "\n" not in text for _, text in lines)


def test_damaged_copies_of_the_demo_scanner_file_are_read_or_refused_plainly():
    original = DEMO_CBOM.read_bytes()
    doc = json.loads(original)
    rng = random.Random(SEED)
    outcomes = {"read": 0, "refused": 0}
    for n in range(COPIES):
        data = (
            _damage_bytes(rng, original)
            if n % 2
            else json.dumps(_damage_json(rng, doc)).encode("utf-8", "surrogatepass")
        )
        start = time.monotonic()
        try:
            found = S.read_structure(data)
        except ImportFileError as refusal:
            outcomes["refused"] += 1
            message = str(refusal)
            assert message and "\n" not in message and "Traceback" not in message and len(message) < 400
        else:
            outcomes["read"] += 1
            _is_whole(found)
            claims = [
                {
                    "id": i,
                    "ref": c.ref,
                    "location": c.location,
                    "location_kind": c.location_kind,
                    "kind": c.kind,
                    "claimed_value": c.claimed_value,
                    "text": c.text,
                    "source": c.source,
                    "detail": c.detail,
                }
                for i, c in enumerate(read_cbom(data)[0], start=1)
            ]
            laid = L.lay_out(claims, found, None)  # and the map can be laid out from whatever was read
            keys = set(laid.boxes) | {a["key"] for a in laid.algorithms} | {c.key for c in laid.containers}
            assert all(line["from"] in keys and line["to"] in keys for line in laid.lines)
            placed = sum(len(b.claims) for b in laid.boxes.values()) + len(laid.unplaced)
            assert placed == len(claims)  # every claim is on a box, or listed as on none: never dropped
        assert time.monotonic() - start < TIME_LIMIT, f"copy {n} took too long"
    assert outcomes["read"] >= 20 and outcomes["refused"] > COPIES // 4, outcomes


def test_a_file_with_very_many_references_is_read_or_refused_within_the_time_limit():
    """The most a 1 MB file can hold: thousands of assets that name each other in long chains, under many services."""
    n = 1500
    assets = [
        {
            "type": "cryptographic-asset",
            "bom-ref": f"k{i}",
            "name": f"key {i}",
            "cryptoProperties": {
                "assetType": "related-crypto-material",
                "relatedCryptoMaterialProperties": {"type": "public-key", "algorithmRef": "a0"},
            },
        }
        for i in range(n)
    ]
    algorithms = [
        {
            "type": "cryptographic-asset",
            "bom-ref": f"a{i}",
            "name": f"ECDSA-P256-{i}",
            "cryptoProperties": {"assetType": "algorithm", "algorithmProperties": {"primitive": "signature"}},
        }
        for i in range(40)
    ]
    cert = {
        "type": "cryptographic-asset",
        "bom-ref": "cert",
        "name": "cert",
        "cryptoProperties": {"assetType": "certificate", "certificateProperties": {"signatureAlgorithmRef": "a0"}},
    }
    deps = [{"ref": f"k{i}", "dependsOn": [f"k{i + 1}", f"k{(i * 7) % n}", f"a{i % 40}"]} for i in range(n - 1)]
    services = [{"bom-ref": f"s{i}", "name": f"s{i}", "endpoints": [f"h{i}.example:443"]} for i in range(300)]
    deps += [{"ref": f"s{i}", "dependsOn": ["cert", f"k{i}"]} for i in range(300)]
    data = json.dumps(
        {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "components": [cert, *assets, *algorithms],
            "services": services,
            "dependencies": deps,
        }
    ).encode()
    assert len(data) < 1024 * 1024
    start = time.monotonic()
    try:
        found = S.read_structure(data)
    except ImportFileError as refusal:
        assert str(refusal) == S.TOO_MANY
    else:
        _is_whole(found)
    assert time.monotonic() - start < TIME_LIMIT

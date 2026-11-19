"""Phase 6d: seeded runs of damaged copies through the two new readers. The only allowed outcomes are a plain refusal
or a normal read, each within a time limit. No new package: random only.

- the reader of a bundled demo change (`demo_changes.read_change`): damaged copies of the two files in demo/changes/;
- the reader of the word list for the flags (`flags.read_words`), and the flag rule on odd lines.
"""
import json
import random
import re
import time

import pytest

from app.changewatch import demo_changes, flags
from app.engine.guidance import OLD_CRYPTOGRAPHY

SEEDS = {"revert-range-check": 20261119, "allow-tls-1-0": 20261120}
COPIES = 400
TIME_LIMIT = 2.0
ODD = [None, 0, -1, 1e308, True, "", "x" * 5000, [], {}, [None], {"a": {"b": []}}, "../../etc/passwd", "a\x00b", "dev/../main", ".lock",
       {"name": "acme_sign.py", "text": "print('hi')\n"}, {"name": "acme-sign", "version": "9.9.9"}, "a{2,1}", "[", "\ud800"]


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


def _damage_json(rng: random.Random, value):
    """Change one value somewhere in the document to an odd one, keeping it JSON."""
    if isinstance(value, dict) and value and rng.random() < 0.85:
        k = rng.choice(list(value))
        return {**value, k: _damage_json(rng, value[k])}
    if isinstance(value, list) and value and rng.random() < 0.85:
        i = rng.randrange(len(value))
        return value[:i] + [_damage_json(rng, value[i])] + value[i + 1:]
    return rng.choice(ODD)


def _as_bytes(value) -> bytes:
    return json.dumps(value).encode("utf-8", "surrogatepass")


@pytest.mark.parametrize("key", sorted(SEEDS))
def test_damaged_copies_of_a_demo_change_are_read_or_refused_plainly(key):
    original = (demo_changes.CHANGES_DIR / f"{key}.json").read_bytes()
    doc = json.loads(original)
    rng = random.Random(SEEDS[key])
    outcomes = {"read": 0, "refused": 0}
    for n in range(COPIES):
        data = _damage_bytes(rng, original) if n % 2 else _as_bytes(_damage_json(rng, doc))
        start = time.monotonic()
        try:
            change = demo_changes.read_change(data)
        except demo_changes.DemoChangeError as refusal:
            outcomes["refused"] += 1
            assert str(refusal) and "Traceback" not in str(refusal) and len(str(refusal)) < 200
        else:
            outcomes["read"] += 1
            # what was read is whole, and still holds no program text: a .py file can only be a registered program by name
            assert change.branch and change.title and change.files and change.offered in demo_changes.OFFERED
            for file in change.files:
                assert (file.text is None) != (file.registered is None)
                assert file.registered is not None or not file.name.endswith(".py")
            demo_changes.content(change)        # and its bytes can be made (a registered program's are read from the registry)
        assert time.monotonic() - start < TIME_LIMIT
    assert outcomes["refused"] > COPIES // 2 and outcomes["read"] >= 1, outcomes


def test_a_demo_change_cannot_carry_a_program_of_its_own_under_a_registered_name():
    doc = json.loads((demo_changes.CHANGES_DIR / "revert-range-check.json").read_bytes())
    # the registered program under another file name, and a version that is not registered: both refused
    for files in ([{"name": "other.py", "registered": {"name": "acme-sign", "version": "1.4.2"}}],
                  [{"name": "acme_sign.py", "registered": {"name": "acme-sign", "version": "9.9.9"}}],
                  [{"name": "acme_sign.py", "registered": {"name": "../acme-sign", "version": "1.4.2"}}],
                  [{"name": "../acme_sign.py", "text": "x\n"}],
                  [{"name": "acme_sign.py", "text": "print('a program written out in the change')\n"}],
                  [{"name": "helper.py", "text": "x = 1\n"}], [{"name": "run.SH", "text": "echo hi\n"}],
                  [{"name": "a.conf", "text": "x\n", "registered": {"name": "acme-sign", "version": "1.4.2"}}],
                  [{"name": "a.conf", "text": "no line break at the end"}],
                  [{"name": "a.conf", "text": "x\n"}, {"name": "a.conf", "text": "y\n"}],
                  []):
        with pytest.raises(demo_changes.DemoChangeError):
            demo_changes.read_change(json.dumps({**doc, "files": files}).encode())
    for field, value in (("branch", "dev/../main"), ("branch", "main.lock"), ("key", "Revert"), ("offered", "always"), ("schema", "other"),
                         ("title", ""), ("title", "x" * 81), ("message", "a\x00b")):
        with pytest.raises(demo_changes.DemoChangeError):
            demo_changes.read_change(json.dumps({**doc, field: value}).encode())
    with pytest.raises(demo_changes.DemoChangeError):
        demo_changes.read_change(json.dumps({**doc, "extra": 1}).encode())
    with pytest.raises(demo_changes.DemoChangeError):
        demo_changes.read_change(b"x" * (demo_changes.MAX_BYTES + 1))


def test_a_missing_or_damaged_bundled_change_is_left_out_of_the_menu(tmp_path):
    good = (demo_changes.CHANGES_DIR / "allow-tls-1-0.json").read_bytes()
    (tmp_path / "allow-tls-1-0.json").write_bytes(good)
    (tmp_path / "revert-range-check.json").write_bytes(b"{ not json")
    (tmp_path / "something-else.json").write_bytes(good)                      # not one of our keys: never read
    assert [c.key for c in demo_changes.bundled(tmp_path)] == ["allow-tls-1-0"]
    # a file whose own key is another one's is not taken under this name
    (tmp_path / "revert-range-check.json").write_bytes(good)
    assert [c.key for c in demo_changes.bundled(tmp_path)] == ["allow-tls-1-0"]
    assert demo_changes.bundled(tmp_path / "nowhere") == []


def test_damaged_word_lists_are_read_or_refused_plainly_and_the_rule_reads_odd_lines():
    rng = random.Random(20261121)
    outcomes = {"read": 0, "refused": 0}
    lines = ["TLS 1.0", "x" * 5000, "", "\x00\x01", "tls" * 2000, "TLSv1" + "." * 3000, "sha" + "-" * 3000 + "1", "ssl 3" * 500, "🙂 TLS 1.0 🙂"]
    for _ in range(COPIES):
        damaged = _damage_json(rng, OLD_CRYPTOGRAPHY)
        start = time.monotonic()
        try:
            words = flags.read_words(damaged)
        except ValueError as refusal:
            outcomes["refused"] += 1
            assert str(refusal) and len(str(refusal)) < 200
        else:
            outcomes["read"] += 1
            for n, line in enumerate(lines):
                for flag in flags.named_in("f.conf", [(n + 1, line)], words):
                    assert flag["kind"] == "old_cryptography" and flag["line"] == n + 1 and len(flag["text"]) <= 200
        assert time.monotonic() - start < TIME_LIMIT
    assert outcomes["refused"] >= 1 and outcomes["read"] >= 1, outcomes
    # the built-in list on the odd lines: quick, and never more than one flag for a name on a line
    start = time.monotonic()
    for n, line in enumerate(lines * 20):
        found = flags.named_in("f.conf", [(n + 1, line)])
        assert len({f["word"] for f in found}) == len(found)
    assert time.monotonic() - start < TIME_LIMIT
    for bad in (None, [], "x", [{}], [{"word": "A", "written": ["("], "source": {"title": "t", "url": "u"}}],
                [{"word": "", "written": ["a"], "source": {"title": "t", "url": "u"}}],
                [{"word": "A", "written": [], "source": {"title": "t", "url": "u"}}],
                [{"word": "A", "written": ["a"], "source": {"title": "t"}}]):
        with pytest.raises(ValueError):
            flags.read_words(bad)
    assert isinstance(flags.read_words(OLD_CRYPTOGRAPHY)[0][1][0], re.Pattern)

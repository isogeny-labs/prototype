"""The known-answer check of a piece of asking code (sandbox research). An instrument check, never a result.

Before a trial is registered, the asking code has to show that it really asks the library: on every copy of its set it
is given fresh signatures that our reference library made, which a library that works must accept, and the same
signatures spoiled in a plain way (one character of the message changed; or made with another key), which it must
refuse. Nothing here is a published case, and nothing here is about any weakness.

    qualify.py --set sandbox/<advisory>/set-a-<id>.json --seed <64 hex characters> --out sandbox/<advisory>/known-a-<id>.json
               [--only VERSION]

With --only, one copy of the set is asked and no other. That is how a DRAFT is checked: on the fixed copy alone, so a
draft never runs on the affected copy and nothing about that copy can reach its author. Once the code is frozen, the
check is made again without --only, on every copy, with a new seed.

The questions are a pure function of the seed, which is drawn after the asking code is frozen, so they can't be
anticipated and can be made again by anyone. Only the questions go into the container; the answers stay here.

The check has a control of its own: two dummy pieces of asking code of ours, one that says yes to everything and one
that says no to everything, go through it every time. This script only counts. Whether the counts are good enough is
decided by the fixed rule in ottolab/sandbox.py, and the dummies must fail that rule.

A container that could not run is not a count: the script stops with an error (exit code 3).
"""
import argparse
import dataclasses
import hashlib
import json
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = Path(os.environ.get("EVIDENCE_LAB_BACKEND") or HERE.parents[1] / "backend")
sys.path.insert(0, str(BACKEND))

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from app.config import load_settings  # noqa: E402
from app.run import runner  # noqa: E402
from app.sandbox import copies  # noqa: E402

NOT_A_RESULT = 3
SCHEMA = "isogeny.sandbox-known-answers/1"
PAIRS = 12                       # fresh valid signatures; and as many spoiled ones
ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _stop(text: str) -> None:
    print(f"not a result: {text}", file=sys.stderr)
    raise SystemExit(NOT_A_RESULT)


def _inside(path: str) -> Path:
    full = (HERE / path).resolve()
    if HERE not in full.parents:
        _stop("the file is outside the lab folder")
    return full


def _key(seed: str, n: int):
    number = int.from_bytes(hashlib.sha256(f"{seed}:{n}".encode("ascii")).digest(), "big") % (ORDER - 1) + 1
    return ec.derive_private_key(number, ec.SECP256R1())


def _point(key) -> str:
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint).hex()


def cases(seed: str) -> list[dict]:
    """The questions for one seed: [{"id", "public_key", "message", "signature", "must"}], `must` kept on this side."""
    rng = random.Random(seed)
    out = []
    for n in range(PAIRS):
        key = _key(seed, n)
        text = "".join(rng.choice(LETTERS) for _ in range(rng.randint(6, 40)))
        message = text.encode("ascii")
        signature = key.sign(message, ec.ECDSA(hashes.SHA256(), deterministic_signing=True)).hex()
        out.append({"id": f"valid-{n}", "public_key": _point(key), "message": message.hex(), "signature": signature, "must": "accept"})
        if n % 2 == 0:      # the same signature, for a message with one character changed
            at = rng.randrange(len(text))
            other = rng.choice([c for c in LETTERS if c != text[at]])
            changed = (text[:at] + other + text[at + 1:]).encode("ascii")
            out.append({"id": f"spoiled-message-{n}", "public_key": _point(key), "message": changed.hex(), "signature": signature, "must": "reject"})
        else:               # a signature another key made for the same message
            stranger = _key(seed, n + 1000)
            forged = stranger.sign(message, ec.ECDSA(hashes.SHA256(), deterministic_signing=True)).hex()
            out.append({"id": f"spoiled-key-{n}", "public_key": _point(key), "message": message.hex(), "signature": forged, "must": "reject"})
    return out


def count(asked: list[dict], lines: dict) -> dict:
    accepted = sum(1 for c in asked if c["must"] == "accept" and (lines.get(c["id"]) or {}).get("valid") is True)
    rejected = sum(1 for c in asked if c["must"] == "reject" and (lines.get(c["id"]) or {}).get("valid") is False)
    unanswered = sum(1 for c in asked if not isinstance((lines.get(c["id"]) or {}).get("valid"), bool))
    notes: dict[str, int] = {}
    for c in asked:
        line = lines.get(c["id"]) or {}
        said = line.get("note") or line.get("error")
        if isinstance(said, str) and said:
            notes[said[:60]] = notes.get(said[:60], 0) + 1
    return {"accepted_valid": accepted, "rejected_spoiled": rejected, "no_answer": unanswered, "notes": dict(sorted(notes.items())[:6])}


def main() -> None:
    parser = argparse.ArgumentParser(prog="qualify.py")
    parser.add_argument("--set", required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--only", default=None)
    args = parser.parse_args()
    if len(args.seed) != 64 or any(c not in "0123456789abcdef" for c in args.seed):
        _stop("the seed is not 64 hex characters")
    try:
        record = copies.read_set(_inside(args.set).read_bytes())
    except (OSError, copies.CopyError) as exc:
        _stop(f"the copy set's record could not be read ({exc})")
    if not copies.image_is(record["image"]["tag"], record["image"]["id"]):
        _stop("the image of the public copies is not on this computer, or is not the one its record names")
    family = copies.family_of(record)
    mode = runner.detect_mode(load_settings(data_dir=HERE / ".known-answers-scratch"))
    if mode.name != "isolated":
        _stop("isolated mode is not available, and a public copy runs nowhere else")
    ask = runner.ComponentRunner(dataclasses.replace(mode, real_images={**mode.real_images, family: record["image"]["tag"]}))
    asked = cases(args.seed)
    job_cases = [{k: c[k] for k in ("id", "public_key", "message", "signature")} for c in asked]
    written = record["asking"]["kind"] == "written"
    out = {"schema": SCHEMA, "set": record["id"], "seed": args.seed, "valid": PAIRS, "spoiled": PAIRS, "versions": {}, "dummies": {}}
    if args.only is not None and args.only not in copies.versions_of(record):
        _stop("the copy set does not hold that version")
    for version in ([args.only] if args.only is not None else copies.versions_of(record)):
        key = f"{record['library']}-{version}"
        subjects = [key] + ([f"dummy-yes:{key}", f"dummy-no:{key}"] if written else [])
        batch = ask.run_job({"op": "verify_batch", "subjects": subjects, "cases": job_cases}, time_limit=300.0, family=family)
        if not batch.ok:
            _stop(f"the copy of {key} could not be asked ({batch.problem})")
        by_subject: dict[str, dict] = {}
        for line in batch.lines:
            by_subject.setdefault(str(line.get("subject")), {})[str(line.get("id"))] = line
        out["versions"][version] = count(asked, by_subject.get(key, {}))
        if written:
            out["dummies"][version] = {"yes": count(asked, by_subject.get(f"dummy-yes:{key}", {})),
                                       "no": count(asked, by_subject.get(f"dummy-no:{key}", {}))}
    target = _inside(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__":
    main()

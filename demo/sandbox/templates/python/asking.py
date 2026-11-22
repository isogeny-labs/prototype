#!/usr/bin/env python3
"""The asking program of a sandbox copy (Python). Ours, and the same for every library.

    python asking.py <library folder> <asking code folder> verify|info        (JSON on stdin, JSON on stdout)

It reads one question and writes one answer. It holds no cryptography and knows no library: the part that does is
asking_code.py in the folder named second, which gives a refusal list (OWN_REFUSALS) and one function,
check_signature(public_key, message, signature), made of straight-line calls into the library.

How a "no" is reported, as for every wrapper (docs/ADAPTER.md): any error raised while the library checks a signature
means "not accepted": {"valid": false}. One of the library's own refusals adds no note; any other error adds
"general error: <ClassName>" (that is how a crash is recorded without being counted as an answer). Only the library's
own True counts as accepted.

What the copy says it is (name and version) was read from the package's own description file when the copy was made,
and is kept beside the library folder (<library folder>.says.json). The right answers are never given to this program.
"""
import json
import sys

COMMANDS = ("verify", "info")
USAGE = "usage: asking.py <library folder> <asking code folder> " + "|".join(COMMANDS) + "  (JSON on stdin, JSON on stdout)"


def cmd_info(library_dir):
    with open(library_dir.rstrip("/") + ".says.json", "r", encoding="utf-8") as handle:
        says = json.load(handle)
    python = ".".join(map(str, sys.version_info[:3]))
    return {"name": str(says["name"]), "version": str(says["version"]), "algorithm": "ECDSA P-256", "hash": "SHA-256",
            "signature_format": "DER", "public_key_format": "uncompressed point, hex (04 || X || Y)",
            "commands": list(COMMANDS), "library": f"{says['package']} {says['version']} on Python {python}"}


def cmd_verify(library_dir, code_dir, req):
    point, message, signature = (bytes.fromhex(req[f]) for f in ("public_key", "message", "signature"))
    if len(point) != 65 or point[:1] != b"\x04":
        return {"valid": False, "note": "not an uncompressed P-256 point"}
    sys.path.insert(0, library_dir)
    sys.path.insert(0, code_dir)
    try:
        import asking_code
        refusals = tuple(asking_code.OWN_REFUSALS)
    except Exception as exc:
        return {"error": "the asking code could not be loaded: " + type(exc).__name__}
    try:
        return {"valid": asking_code.check_signature(point, message, signature) is True}
    except refusals:
        return {"valid": False}
    except Exception as exc:   # a crash inside the library, or a question it can't take: not an answer, recorded as a note
        return {"valid": False, "note": "general error: " + type(exc).__name__}


def main(argv):
    if len(argv) != 4 or argv[3] not in COMMANDS:
        print(json.dumps({"error": USAGE}))
        return 2
    try:
        text = sys.stdin.read()
        req = json.loads(text) if text.strip() else {}
        if not isinstance(req, dict):
            raise ValueError("input must be a JSON object")
        out = cmd_info(argv[1]) if argv[3] == "info" else cmd_verify(argv[1], argv[2], req)
    except Exception as exc:
        print(json.dumps({"error": "bad input: " + type(exc).__name__}))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""control-accept-all -- A DELIBERATELY BROKEN CONTROL. DO NOT USE FOR ANYTHING REAL.

Part of the Isogeny Evidence Lab demo. Every test of a signing component also runs this
broken signer. Its `verify` command answers {"valid": true} to anything at all, without
looking at the key, the message or the signature. A test that is working must catch it:
if this control "passes", the test run can't be trusted.

It speaks the same five commands as acme-sign (keygen | sign | verify | info | bench):
JSON on standard input, JSON on standard output. keygen, sign and bench are borrowed from
the demo component acme-sign 1.4.3 next door. Standard library only.
"""
import importlib.util
import json
import os
import sys

NAME = "control-accept-all"
BORROWED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "acme-sign-1.4.3", "acme_sign.py")
USAGE = "usage: accept_all.py keygen|sign|verify|info|bench  (JSON on stdin, JSON on stdout)"


def cmd_verify(_req):
    return {"valid": True}  # the deliberate fault: nothing is checked


def main(argv):
    if len(argv) != 2 or argv[1] not in ("keygen", "sign", "verify", "info", "bench"):
        print(json.dumps({"error": USAGE}))
        return 2
    if argv[1] == "verify":
        sys.stdin.read()
        print(json.dumps(cmd_verify(None)))
        return 0
    spec = importlib.util.spec_from_file_location("borrowed_component", BORROWED)
    real = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real)
    real.cmd_verify = cmd_verify  # bench uses the broken verify too
    real.COMMANDS["verify"] = cmd_verify
    real.COMMANDS["info"] = lambda _req: {
        "name": NAME, "version": "control", "algorithm": real.ALGORITHM, "hash": "SHA-256", "signature_format": "DER",
        "public_key_format": "uncompressed point, hex (04 || X || Y)",
        "commands": ["keygen", "sign", "verify", "info", "bench"],
        "control": "deliberately broken: verify accepts everything"}
    return real.main(["accept_all.py", argv[1]])


if __name__ == "__main__":
    sys.exit(main(sys.argv))

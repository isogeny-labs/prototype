#!/usr/bin/env python3
"""Isogeny Evidence Lab — standalone evidence-bundle verifier. Needs only Python 3 and `cryptography`; no platform account.

  python -m iel_tools.verify bundle.json --trusted-key platform.pub --trusted-key runner_key.pem.pub [--json]

Checks: bundle structure, DSSE signature against the EXPLICITLY supplied trusted keys (keys inside the bundle are never
trusted), artifact digests against the statement subjects, and reports what was verified and what remains unverified.
Exit code 0 = all checks passed, 1 = a check failed, 2 = unsupported input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from iel_tools import attest  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle")
    ap.add_argument("--trusted-key", action="append", default=[], help="PEM file of a trusted Ed25519 public key (repeatable)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        doc = json.loads(Path(a.bundle).read_text())
    except Exception as e:  # noqa: BLE001
        print(f"unsupported input: cannot read JSON ({type(e).__name__})"); return 2
    trusted = {}
    for p in a.trusted_key:
        try:
            pub = attest.public_key_from_pem(Path(p).read_bytes())
            trusted[attest.key_id(pub)] = (Path(p).name, pub)
        except Exception as e:  # noqa: BLE001
            print(f"unsupported trusted key {p}: {type(e).__name__}"); return 2
    if not trusted:
        print("no trusted keys supplied: the signature cannot be checked (keys inside the bundle are never trusted)")
    try:
        env, arts = attest.load_bundle(doc)
    except ValueError as e:
        print(f"unsupported format: {e}"); return 2
    r = attest.verify_envelope(env, trusted, arts)
    report = {"ok": r.ok, "structure_ok": r.structure_ok, "signature_verified": r.signature_verified, "signer_trusted": r.signer_trusted, "signer": r.signer_name,
              "keyid": r.keyid, "artifact_digests": r.digests_checked, "problems": r.problems, "verified": r.verified, "unverified": r.unverified,
              "statement": {"predicateType": (r.statement or {}).get("predicateType"), "subjects": [s["name"] for s in (r.statement or {}).get("subject", [])],
                            "run_id": ((r.statement or {}).get("predicate") or {}).get("run_id"), "project_id": ((r.statement or {}).get("predicate") or {}).get("project_id"),
                            "implementation": ((r.statement or {}).get("predicate") or {}).get("implementation"),
                            "classification": (((r.statement or {}).get("predicate") or {}).get("results") or {}).get("classification")}}
    if a.json:
        print(json.dumps(report, indent=1))
    else:
        print("RESULT:", "ALL CHECKS PASSED" if r.ok else "CHECKS FAILED")
        for v in r.verified:
            print("  verified   :", v)
        for u in r.unverified:
            print("  unverified :", u)
        for p in r.problems:
            print("  PROBLEM    :", p)
        s = report["statement"]
        print(f"  statement  : {s['predicateType']} run_id={s['run_id']} project={s['project_id']} impl={s['implementation']} classification={s['classification']}")
        print("  note       : verification establishes integrity and attribution under YOUR trust policy; it does not establish that the\n"
              "               reported environment or execution was genuine, nor that the implementation is secure.")
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())

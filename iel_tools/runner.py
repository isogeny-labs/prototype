#!/usr/bin/env python3
"""Isogeny Evidence Lab — customer-side runner.

Runs a versioned test definition against YOUR adapter on YOUR machine and writes a signed evidence bundle.
Source code and signing keys never leave the machine; you upload only the bundle.

  python -m iel_tools.runner keygen  --out runner_key.pem                   # once; register the printed PUBLIC key in the project
  python -m iel_tools.runner run --project <id> --impl-name acme-signer --impl-version 1.0.0 \
        --adapter ./adapter.py --test signature-library-core --test-version 1 --key runner_key.pem --out bundle.json
  python -m iel_tools.runner run ... --fixture-dir /path/to/fixtures     # if fixtures are not next to this package

The bundle: in-toto Statement (subjects: raw_output.json, adapter source) in a DSSE envelope, Ed25519-signed, plus
the raw output artifact. Keep the private key outside any uploaded artifact and outside source control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from iel_tools import attest  # noqa: E402

RUNNER_VERSION = "0.2.0"
TESTS = {"signature-library-core": {"fixture": "signature_library", "params": {"repeat_count": 100, "message_bytes": 1024, "seed": 1}},
         "malformed-input-sweep": {"fixture": "malformed_input_sweep", "params": {"max_extra_bytes": 64, "seed": 3}}}


def find_fixtures(explicit: str | None) -> Path:
    for cand in ([Path(explicit)] if explicit else []) + [Path(__file__).resolve().parent / "fixtures", Path(__file__).resolve().parents[1] / "backend" / "fixtures"]:
        if cand and (cand / "signature_library.py").exists():
            return cand
    sys.exit("fixtures not found; pass --fixture-dir")


def cmd_keygen(a):
    key = attest.generate_private_key()
    out = Path(a.out)
    out.write_bytes(attest.private_key_to_pem(key))
    os.chmod(out, 0o600)
    pub = attest.public_key_to_pem(key.public_key())
    Path(str(out) + ".pub").write_text(pub)
    print(f"private key written to {out} (mode 600) — keep it out of uploads and source control")
    print(f"PUBLIC key written to {out}.pub — register it in the project's trusted keys (key id {attest.key_id(key.public_key())[:16]}…):\n{pub}")


def cmd_run(a):
    fixtures = find_fixtures(a.fixture_dir)
    test = TESTS[a.test]
    adapter = Path(a.adapter).resolve()
    src = adapter.read_bytes()
    if b"PRIVATE KEY-----" in src:
        sys.exit("refusing: the adapter file contains private-key material")
    params = {**test["params"], **json.loads(a.params or "{}"), "adapter": {"kind": "module", "path": str(adapter)}}
    argv = [sys.executable, "-I", str(fixtures / f"{test['fixture']}.py")]
    started = datetime.now(timezone.utc)
    proc = subprocess.run(argv, input=json.dumps(params, sort_keys=True).encode(), capture_output=True, cwd=str(fixtures), timeout=a.timeout)
    if proc.returncode not in (0, 2) or not proc.stdout:
        sys.exit(f"fixture failed (exit {proc.returncode}): {proc.stderr.decode()[-800:]}")
    raw = proc.stdout
    result = json.loads(raw)
    run_id = a.run_id or uuid.uuid4().hex
    key = attest.private_key_from_pem(Path(a.key).read_bytes())
    predicate = {
        "project_id": a.project, "run_id": run_id, "execution_mode": "customer_runner",
        "implementation": {"name": a.impl_name, "version": a.impl_version, "source_digest": hashlib.sha256(src).hexdigest(), "source_revision": a.source_revision or ""},
        "test": {"test_id": a.test, "version": a.test_version, "fixture": test["fixture"], "fixture_version": result.get("fixture_version")},
        "runner": {"kind": "customer_runner", "version": RUNNER_VERSION},
        "environment": {**result.get("environment", {}), "hostname": platform.node(), "runner_host_platform": platform.platform(), "measured_by": "customer-side runner"},
        "commands": [{"argv": [os.path.basename(argv[0]), "-I", f"fixtures/{test['fixture']}.py"], "stdin_sha256": hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()}],
        "inputs": {k: v for k, v in params.items() if k != "adapter"},
        "results": {"status": result.get("status"), "metrics": result.get("metrics", {}), "scenarios": result.get("scenarios", []), "failures": result.get("failures", []),
                    "limitations": result.get("limitations", []), "classification": ("failed" if any(s.get("pass") is False for s in result.get("scenarios", [])) else
                                                                                    ("passed_defined_checks" if result.get("status") == "completed" else "inconclusive"))},
        "executed_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    subjects = [{"name": "raw_output.json", "digest": {"sha256": hashlib.sha256(raw).hexdigest()}},
                {"name": f"adapter-source:{adapter.name}", "digest": {"sha256": hashlib.sha256(src).hexdigest()}}]
    stmt = attest.build_statement(subjects, attest.PREDICATE_RUN, predicate)
    env = attest.sign_statement(stmt, key)
    bundle = attest.make_bundle(env, {"raw_output.json": raw})  # adapter source is referenced by digest, not uploaded
    Path(a.out).write_text(json.dumps(bundle, indent=1, sort_keys=True))
    print(f"run {run_id}: classification={predicate['results']['classification']} -> {a.out} (signer {attest.key_id(key.public_key())[:16]}…)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen"); k.add_argument("--out", default="runner_key.pem"); k.set_defaults(fn=cmd_keygen)
    r = sub.add_parser("run")
    for name, kw in (("--project", {"required": True}), ("--impl-name", {"required": True}), ("--impl-version", {"required": True}), ("--adapter", {"required": True}),
                     ("--test", {"default": "signature-library-core", "choices": sorted(TESTS)}), ("--test-version", {"default": "1"}), ("--key", {"required": True}),
                     ("--out", {"default": "bundle.json"}), ("--fixture-dir", {}), ("--params", {}), ("--run-id", {}), ("--source-revision", {}), ("--timeout", {"type": int, "default": 600})):
        r.add_argument(name, **kw)
    r.set_defaults(fn=cmd_run)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()

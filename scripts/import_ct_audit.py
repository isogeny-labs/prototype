#!/usr/bin/env python3
"""Pin a read-only snapshot of the crypto crate's dynamic constant-time audit (isogeny-labs/crypto PR #3296).

Reads `research/ct_dynamic_audit_20261102/results/summary.json` and the run receipt from a checkout of the crypto
repository on the study's branch, and writes `seeds/ct_audit_snapshot.json`: per-target taint sites and verdicts,
per-class instruction-count ranges and verdicts, the source commit, and SHA-256 digests of the files read. Nothing is
recomputed. The seed imports it as *imported* evidence when the `ct_dynamic_audit` binary is not available.

Usage: python3 scripts/import_ct_audit.py /path/to/crypto
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "seeds" / "ct_audit_snapshot.json"
STUDY = "research/ct_dynamic_audit_20261102"


def main(crypto: Path) -> None:
    summary_path = crypto / STUDY / "results" / "summary.json"
    receipt_path = crypto / STUDY / "cards" / "CARD-ct-dynamic-audit-20261102-1.receipt.json"
    summary_raw = summary_path.read_bytes()
    receipt = json.loads(receipt_path.read_text())
    commit = subprocess.run(["git", "-C", str(crypto), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    branch = subprocess.run(["git", "-C", str(crypto), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    snap = {
        "schema": "iel-ct-audit-snapshot/v1",
        "provenance": "imported",
        "source": {
            "repository": "isogeny-labs/crypto",
            "study": STUDY,
            "pull_request": 3296,
            "branch": branch,
            "commit": commit,
            "summary_sha256": hashlib.sha256(summary_raw).hexdigest(),
            "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            "run_commit": receipt.get("commit"),
            "card_id": receipt.get("card_id"),
            "report": f"{STUDY}/REPORT.pdf",
        },
        "method": ("Valgrind 3.22. Taint: Memcheck with the secret marked undefined (ctgrind); every conditional jump/move "
                   "or address that depends on it is reported. Instruction count: Callgrind, one dump per call, classes "
                   "aa (one secret repeated), random, short (< 2^32), lowhw (weight 8)."),
        "limitations": [
            "Taint covers one release build, 4 calls per target and Memcheck's model; it does not see conditional moves, cache-line or port effects.",
            "The instruction-count verdict is 'not applicable' wherever repeating one secret already varies the count (OsRng, allocator state).",
            "No target is claimed constant-time; no wall-clock measurement was made.",
        ],
        "targets": json.loads(summary_raw),
    }
    OUT.write_text(json.dumps(snap, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(snap['targets'])} targets from {branch}@{commit[:12]}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]).resolve())

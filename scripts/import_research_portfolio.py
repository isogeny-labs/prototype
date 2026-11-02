#!/usr/bin/env python3
"""Pin a read-only research-portfolio snapshot from the sibling `crypto` checkout.

Reads `docs/ic/leaderboard.json` (the index-calculus leaderboard that `scripts/build_ic_leaderboard.py` generates in
the crypto repository) and writes `seeds/research_portfolio.json`: a trimmed copy of its rows with the source commit,
the SHA-256 of the exact file read, each row's validation-gate status, and the leaderboard's own scope statements.

Nothing is recomputed or re-ranked here. A row's `ratio_rho` is copied as the leaderboard states it: the distance
remaining to the matched Pollard-rho reference within that row's family (>1 means index calculus is still slower).

Usage: python3 scripts/import_research_portfolio.py /path/to/crypto
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "seeds" / "research_portfolio.json"


def main(crypto: Path) -> None:
    src = crypto / "docs" / "ic" / "leaderboard.json"
    raw = src.read_bytes()
    d = json.loads(raw)
    commit = subprocess.run(["git", "-C", str(crypto), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    commit_date = subprocess.run(["git", "-C", str(crypto), "log", "-1", "--format=%cs", "--", "docs/ic/leaderboard.json"],
                                 capture_output=True, text=True, check=True).stdout.strip()
    rows = []
    for r in d["board"]:
        best = min(r["recipes"], key=lambda x: x["ratio_rho"])
        v = r.get("validation") or {}
        rows.append({
            "regime": r["regime"],
            "family": r.get("family"),
            "slug": r["slug"],
            "log2_r": r["log2_r"],
            "targets": r.get("targets"),
            "reference": r.get("reference"),
            "best_recipe": best.get("label") or best.get("variant"),
            "best_s": best.get("s"),
            "ratio_rho": best["ratio_rho"],
            "ratio_floor": best.get("ratio_floor"),
            "verified": best.get("verified"),
            "repetitions": best.get("repetitions"),
            "recipes_measured": len(r["recipes"]),
            "validation_status": v.get("status", "unknown"),
            "validation_verdict": (v.get("sweep") or {}).get("verdict"),
            "validation_caveats": [k for k, ok in (v.get("sweep") or {}).items() if k.endswith("_ok") and ok is not True],
            "validation_reasons": v.get("reasons", []),
        })
    families = {k: {kk: f.get(kk) for kk in ("title", "regimes", "unit_short", "ref_short", "unit", "reference", "floor", "status")}
                for k, f in d["families"].items()}
    progress = d.get("progress") or {}
    snap = {
        "schema": "iel-research-portfolio/v1",
        "provenance": "imported",
        "source": {
            "repository": "isogeny-labs/crypto",
            "path": "docs/ic/leaderboard.json",
            "commit": commit,
            "file_last_changed": commit_date,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "generated_by": d.get("generated_by"),
        },
        "what_this_is": d.get("what_this_is"),
        "what_this_is_not": d.get("what_this_is_not"),
        "unit": d.get("unit"),
        "success_criterion": ("Every verified, measured improvement over the current index-calculus baseline is a success. "
                              "Beating Pollard rho is the long-term goal; each row's ratio to the matched rho is the distance "
                              "remaining, not a pass/fail gate."),
        "validation_gate": d.get("validation_gate"),
        "families": families,
        "leaders": d.get("leaders"),
        "rows": rows,
        "progress": {"label": progress.get("label"), "updated": progress.get("updated"),
                     "points": [{k: p.get(k) for k in ("date", "label", "value", "class", "reference", "detail")}
                                for p in progress.get("points", [])]},
    }
    OUT.write_text(json.dumps(snap, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} rows from {commit[:12]} (sha256 {snap['source']['sha256'][:16]}…)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]).resolve())

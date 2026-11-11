"""Accuracy check: does the app's answer for each demo claim match demo/expected.json?

Run from the backend folder:  python -m app.accuracy
It does a fresh demo import and a real Verify. It only READS the answer key; it never writes it.
Phase 1 covers the "verify" entries (V1-V3). Any mismatch or missing answer is shown and makes the
command exit with an error code.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from .config import EXPECTED_JSON, Settings, load_settings
from .lab import Lab

# Which claim in demo/acme-pay-cbom.json answers which entry of the answer key: (bom-ref, kind) -> id.
DEMO_CLAIM_IDS = {
    ("proto-tls13", "protocol_versions"): "V1",
    ("cert-server", "certificate"): "V2",
    ("lib-acme-sign", "signature_algorithm"): "V3",
}


def run_accuracy(settings: Settings | None = None) -> dict:
    settings = settings or load_settings()
    expected = json.loads(EXPECTED_JSON.read_text(encoding="utf-8"))["verify"]
    notes = []
    with tempfile.TemporaryDirectory(prefix="evidence-lab-accuracy-") as scratch:
        # Own scratch database (so the app's saved work is untouched); same demo test certificate as the app.
        lab = Lab(settings, db_path=Path(scratch) / "accuracy.sqlite3", allow_external_demo_server=True)
        lab.start()
        try:
            if lab.demo.running:
                notes.append(f"Started the demo server on {settings.demo_address} for this check.")
            elif lab.demo.port_in_use:
                notes.append(f"Port {settings.demo_tls_port} is already in use (normally by the running app). Using it "
                             "only if its certificate is this app's demo test certificate.")
            else:
                notes.append(f"The demo server could not start: {lab.demo.error}")
            imp = lab.import_demo()
            for address in imp["addresses"]:
                lab.confirm_address(imp["id"], address["address"], True)
                notes.append(f"Confirmed {address['address']} automatically for this check (it is the app's own demo "
                             "server on this computer). In the app, you tick this box yourself.")
            run = lab.verify(imp["id"])
        finally:
            lab.stop()
    actual = {}
    for res in run["results"]:
        key = DEMO_CLAIM_IDS.get((res["claim"]["ref"], res["claim"]["kind"]))
        if key:
            actual[key] = res
    lines, matched = [], 0
    for entry in expected:
        res = actual.get(entry["id"])
        got = res["result"] if res else "(no answer: the demo file produced no claim for this entry)"
        ok = res is not None and got == entry["expected"]
        matched += ok
        lines.append({"id": entry["id"], "claim": entry["claim"], "expected": entry["expected"], "actual": got,
                      "match": ok, "found": (res or {}).get("found"), "reason": (res or {}).get("reason"),
                      "app_claim_text": (res or {}).get("claim", {}).get("text")})
    return {"lines": lines, "matched": matched, "total": len(expected), "notes": notes,
            "unmapped_claims": [r["claim"]["text"] for r in run["results"]
                                if (r["claim"]["ref"], r["claim"]["kind"]) not in DEMO_CLAIM_IDS]}


def main() -> int:
    report = run_accuracy()
    print("Demo accuracy check (Verify step) against demo/expected.json")
    for note in report["notes"]:
        print(f"  note: {note}")
    for line in report["lines"]:
        print(f"  {line['id']}  {'MATCH   ' if line['match'] else 'MISMATCH'}  expected {line['expected']!r}, "
              f"app says {line['actual']!r}  -  {line['claim']}")
        if line["found"]:
            print(f"        found: {line['found']}")
        if line["reason"]:
            print(f"        reason: {line['reason']}")
        if line["app_claim_text"] and line["app_claim_text"] != line["claim"]:
            print(f"        (the app words this claim as: {line['app_claim_text']})")
    for text in report["unmapped_claims"]:
        print(f"  EXTRA   the demo file produced a claim the answer key does not list: {text}")
    print(f"Demo accuracy: {report['matched']} of {report['total']} match")
    return 0 if report["matched"] == report["total"] and not report["unmapped_claims"] else 1


if __name__ == "__main__":
    sys.exit(main())

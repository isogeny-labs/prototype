"""Phase 4d: the Dependencies part of the evidence file and section 7 of the readable report, in demo mode.
The file still checks with `python -m evidence verify`; every yes or no carries one label and its source; the report
links only to the knowledge base's official sources (fixed in the app), never to anything from the list."""
import json
from pathlib import Path

from conftest import make_lab
from test_evidence import Shape

from app.evidence.export import REPORT_LINKS
from app.knowledge.base import knowledge_base

REPO = Path(__file__).resolve().parents[3]


def _walk(tmp_path):
    lab = make_lab(tmp_path)
    imp = lab.import_demo()
    for address in imp["addresses"]:
        lab.confirm_address(imp["id"], address["address"], True)
    pid = lab.ensure_plan(imp["id"])["id"]
    view = lab.add_dependency_list(pid, "dependencies-demo.cdx.json", (REPO / "demo/dependencies-demo.cdx.json").read_bytes())
    pay = next(g for g in view["groups"] if g["label"] == "acme-pay-server 1.0.0")
    server = next(o["key"] for o in pay["picker"]["options"] if o["key"].startswith("server:"))
    lab.tie_dependency(pid, pay["key"], server)
    lab.measure_migration(pid)
    lab.wait_until_measured(pid, 120)
    return lab, pid, server


def test_evidence_has_the_dependency_part_and_still_verifies(tmp_path):
    from evidence import verify_bytes
    lab, pid, server = _walk(tmp_path)
    try:
        made = lab.export_evidence(pid)
        raw = lab.evidence_file(made["id"], "json")[1]
        page = lab.evidence_file(made["id"], "html")[1].decode("utf-8")
        outcome = verify_bytes(raw, (lab.settings.data_dir / "evidence-signing-public-key.txt").read_text().strip())
        assert outcome.ok, outcome
    finally:
        lab.stop()
    part = json.loads(raw)["evidence"]["dependencies"]
    assert part["list"]["filename"] == "dependencies-demo.cdx.json" and len(part["rows"]) == 10
    assert part["measurements"] == []                         # demo mode: nothing measured, nothing pretended
    labels = {a["label"] for r in part["rows"] for a in r["answers"].values()} | {
        b["answer_label"] for s in part["systems"] for bs in s["blockers"].values() for b in bs}
    assert labels == {"release_notes", None}               # the third label (your_environment) is never produced
    for row in part["rows"]:
        for a in row["answers"].values():
            if a["answer"] in ("yes", "no"):
                assert a["label"] == "release_notes" and a["lookup"]["source"]["url"].startswith("https://")
            else:
                assert a["label"] is None
    system = next(s for s in part["systems"] if s["key"] == server)
    assert [b["library"] for b in system["blockers"]["kex"]] == ["openssl"] and system["without_answer"] == 1
    assert [f["source"]["kind"] for f in json.loads(raw)["evidence"]["fixes"]].count("dependency") == 1
    # section 7 of the report: the sources are links to the official pages, and only those
    shape = Shape()
    shape.feed(page)
    text = " ".join(shape.text)
    assert "7. Dependencies" in text and "Update OpenSSL to 3.5.0 or later" in text
    assert "Support for PQC algorithms (ML-KEM, ML-DSA and SLH-DSA)" in text
    kb_links = set(knowledge_base().source_urls())
    assert kb_links & set(shape.links) and set(shape.links) <= set(REPORT_LINKS)
    assert text.lower().count("secure") == 1                 # only the disclaimer


def test_knowledge_base_links_are_allowed_and_https():
    urls = knowledge_base().source_urls()
    assert urls and set(urls) <= set(REPORT_LINKS) and all(u.startswith("https://") for u in urls)

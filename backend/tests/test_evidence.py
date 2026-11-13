"""Download evidence: the signed JSON envelope, the allow-list it is built from, the static HTML report, the routes."""
import hashlib
import json
import re
import stat
from html.parser import HTMLParser

from sqlalchemy import select

from app import evidence_export
from app.canonical import canonical_bytes, loads_strict
from app.db import AddressRow, ClaimRow, ImportRow, VerifyRunRow
from app.evidence_export import (
    PUBLIC_KEY_FILE, REPORT_LINKS, SIGNING_KEY_FILE, ensure_signing_key, key_fingerprint, render_report_html,
)
from app.present import DISCLAIMER
from conftest import demo_plan, make_lab, run_kind
from test_plan_api import start, wait

MARKUP = '<script>alert(1)</script>"onmouseover="x\'<img src=x onerror=y>&'


def export(lab, plan_id):
    made = lab.export_evidence(plan_id)
    return made, lab.evidence_file(made["id"], "json")[1], lab.evidence_file(made["id"], "html")[1]


def test_envelope_shape_and_what_is_inside(demo_flow):
    made, raw, report = export(demo_flow.lab, demo_flow.plan.id)
    envelope = loads_strict(raw)
    assert raw == canonical_bytes(envelope) and not raw.endswith(b"\n")
    assert sorted(envelope) == ["evidence", "fingerprint", "public_key", "signature"]
    e = envelope["evidence"]
    assert envelope["fingerprint"] == hashlib.sha256(canonical_bytes(e)).hexdigest() == made["fingerprint"]
    assert re.fullmatch(r"[0-9a-f]{64}", envelope["public_key"]) and re.fullmatch(r"[0-9a-f]{128}", envelope["signature"])
    assert envelope["public_key"] == (demo_flow.lab.settings.data_dir / PUBLIC_KEY_FILE).read_text().strip()
    assert sorted(e) == ["app", "code", "component", "disclaimer", "fixes", "generated_at", "import", "mode_line", "retest", "schema",
                         "signer_key_fingerprint", "tests", "verify"]
    # no code was connected for this file, so the two fixes are listed as they stood: nothing prepared, nothing proved
    assert e["code"] is None and [(f["id"], f["kind"], f["status"]) for f in e["fixes"]] == [
        ("fix-ecdsa-range-check", "code", "Code not connected"), ("fix-tls-versions", "text", "Text only")]
    assert all(f["change"] is None and f["proofs"] == [] and f["pull_request"] is None and f["merge"] is None for f in e["fixes"])
    assert e["schema"] == "isogeny.evidence/1" and e["disclaimer"] == DISCLAIMER and e["mode_line"] == demo_flow.lab.mode.line
    assert e["signer_key_fingerprint"] == key_fingerprint(envelope["public_key"])
    assert e["component"] == {"name": "acme-sign", "version": "1.4.2"}
    assert e["retest"]["baseline_version"] == "1.4.2" and e["retest"]["version"] == "1.4.3"
    assert e["import"]["is_demo"] is True and len(e["import"]["claims"]) == 3
    assert [r["result"] for r in e["verify"]["results"]] == ["False", "True", "True"]
    assert [t["kind"] for t in e["tests"]] == [r["kind"] for r in demo_flow.after["rows"]]
    for test in e["tests"]:
        assert test["spec_hash_ok"] is True
        assert hashlib.sha256(canonical_bytes(test["spec"])).hexdigest() == test["spec_hash"]  # the locked test, exactly
        assert [run["phase"] for run in test["runs"]] == ["first", "retest"]
        for run in test["runs"]:
            # the run record as fingerprinted, the separate review of it, and the worded result
            assert hashlib.sha256(canonical_bytes(run["record"])).hexdigest() == run["run_sha256"] == run["review"]["run_sha256"]
            assert run["record"]["spec_hash"] == test["spec_hash"] == run["review"]["spec_hash"]
            assert run["record"]["mode"] == "demo" and run["review"]["reviewer"] == "isogeny.rule-reviewer/1"
            assert run["review"]["reviewer"] != run["review"]["proposed_by"]
            assert run["result"]["code"] == run["review"]["verdict"]["code"]
            assert run["result"]["locked_test"]["fingerprint"] == test["spec_hash"]
            # which code it ran on: our bundled demo component for a software test, nothing for a server test
            software = run["record"]["component"]["name"] is not None
            assert (run["code"]["source"] if software else run["code"]) == ("bundled" if software else None)
    vectors = next(t for t in e["tests"] if t["kind"] == "official_vectors")
    assert [r["result"]["label"] for r in vectors["runs"]] == ["Failed", "Passed"]
    assert vectors["runs"][0]["record"]["component"] == {"name": "acme-sign", "version": "1.4.2"}
    assert vectors["runs"][1]["record"]["component"] == {"name": "acme-sign", "version": "1.4.3"}
    assert made["json"]["filename"].startswith("evidence-lab-evidence-") and made["html"]["filename"].startswith("evidence-lab-report-")
    assert made["verify_hint"] == "To check the file: cd backend && .venv/bin/python -m evidence verify <the downloaded .json file>"
    assert report.startswith(b"<!DOCTYPE html>")


def test_mark_reviewed_and_dig_deeper_are_in_the_evidence(lab):
    plan = demo_plan(lab)
    result = run_kind(lab, plan, "certificate")
    lab.mark_reviewed(result["run_id"])
    lab.dig_deeper(result["run_id"])
    _, raw, report = export(lab, plan.id)
    tests = json.loads(raw)["evidence"]["tests"]
    run = next(t for t in tests if t["kind"] == "certificate")["runs"][0]
    assert run["reviewed_at"] and run["research_request"]["status"] == "waiting for research engine"
    assert run["result"]["research"]["badge"] == "Queued"
    assert all(t["runs"] == [] for t in tests if t["kind"] != "certificate")   # tests not run: listed, with no result
    assert json.loads(raw)["evidence"]["retest"] is None and json.loads(raw)["evidence"]["verify"] is None
    assert b"waiting for research engine" in report and b"Not run yet. No result." in report


def test_built_from_an_allow_list_not_from_row_dumps(lab):
    """Things planted in columns and JSON fields the evidence does not list never reach the files."""
    plan = demo_plan(lab)
    lab.verify(plan.imp["id"])
    run_kind(lab, plan, "certificate")
    with lab.db() as db:
        claim = db.scalars(select(ClaimRow).where(ClaimRow.import_id == plan.imp["id"])).first()
        claim.detail = {**claim.detail, "planted": "PLANTED-IN-DETAIL"}
        address = db.scalars(select(AddressRow).where(AddressRow.import_id == plan.imp["id"])).first()
        address.error = "PLANTED-IN-ADDRESS"
        run = db.scalars(select(VerifyRunRow)).first()
        results = json.loads(json.dumps(run.results))
        results[0]["planted"] = "PLANTED-IN-RESULT"
        results[0]["claim"]["planted"] = "PLANTED-IN-CLAIM"
        results[0]["evidence"][0]["planted"] = "PLANTED-IN-EVIDENCE-ITEM"
        results[0]["evidence"][0]["private_key"] = "PLANTED-PRIVATE"
        run.results = results
        db.commit()
    _, raw, report = export(lab, plan.id)
    assert b"PLANTED" not in raw and b"PLANTED" not in report
    e = json.loads(raw)["evidence"]
    assert sorted(e["verify"]["results"][0]) == ["claim", "claim_ref", "evidence", "found", "reason", "result"]
    assert sorted(e["verify"]["results"][0]["evidence"][0]) == ["command", "duration_ms", "output", "started_at", "title", "tool", "tool_version"]
    assert sorted(e["import"]["claims"][0]) == ["claimed_value", "kind", "location", "location_kind", "ref", "source", "text"]
    # nothing about the login is in it
    for word in (b"password", b"salt", b"token_hash"):
        assert word not in raw.lower()


def test_private_key_fields_and_pem_blocks_are_masked_on_the_way_out(lab):
    plan = demo_plan(lab)
    lab.verify(plan.imp["id"])
    run_kind(lab, plan, "certificate")
    pem = "-----BEGIN PRIVATE KEY-----\nTUlHSEFnRUFNQk1HQnlxR1NNNDlBZ0VHQ0NxR1NNNDlBd0VIQkcwd2F3SUJBUVFn\n-----END PRIVATE KEY-----"
    with lab.db() as db:
        run = db.scalars(select(VerifyRunRow)).first()
        results = json.loads(json.dumps(run.results))
        results[0]["evidence"][0]["output"] = f"before {pem} after"
        results[0]["found"] = pem
        run.results = results
        db.commit()
    _, raw, report = export(lab, plan.id)
    for data in (raw, report):
        assert b"PRIVATE KEY" not in data and b"TUlHSEFnRUFNQk1HQnlxR1NNNDlBZ0VH" not in data


class Shape(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.attrs, self.links, self.text = set(), set(), [], []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        self.attrs.update((tag, name) for name, _ in attrs)
        self.links += [value for name, value in attrs if name in ("href", "src", "action")]

    def handle_data(self, data):
        self.text.append(data)


def poisoned(value):
    if isinstance(value, dict):
        return {k: poisoned(v) for k, v in value.items()}
    if isinstance(value, list):
        return [poisoned(v) for v in value]
    return f"{value}{MARKUP}" if isinstance(value, str) else value


def test_report_escapes_markup_from_claims_and_component_output(demo_flow):
    """Every text in the evidence (claim text, file name, component output, raw TLS output...) gets markup added.
    None of it may come out as markup."""
    _, raw, _ = export(demo_flow.lab, demo_flow.plan.id)
    envelope = json.loads(raw)
    evidence = poisoned(envelope["evidence"])
    evidence["import"]["is_demo"], evidence["retest"]["columns"] = True, envelope["evidence"]["retest"]["columns"]
    page = render_report_html({"evidence": evidence, "fingerprint": envelope["fingerprint"]}).decode("utf-8")
    assert page.count("&lt;script&gt;alert(1)&lt;/script&gt;&quot;onmouseover=&quot;x&#x27;&lt;img src=x onerror=y&gt;&amp;") > 200
    assert "<script" not in page.lower() and "<img" not in page.lower() and '"onmouseover' not in page
    shape = Shape()
    shape.feed(page)
    assert shape.tags <= {"html", "head", "meta", "title", "style", "body", "main", "h1", "h2", "h3", "h4", "p", "div", "span", "table",
                          "thead", "tbody", "tr", "th", "td", "pre", "code", "ul", "li", "details", "summary", "strong", "a"}
    assert {name for _, name in shape.attrs} <= {"class", "href", "rel", "charset", "http-equiv", "content", "name", "lang"}
    assert shape.links == []   # a link whose address was touched is not one of ours any more, so it is printed as text
    assert MARKUP in "".join(shape.text)  # shown to the reader as plain text


def test_report_is_static_and_says_what_it_is(demo_flow):
    made, raw, report = export(demo_flow.lab, demo_flow.plan.id)
    page = report.decode("utf-8")
    assert '<meta http-equiv="Content-Security-Policy" content="default-src &#x27;none&#x27;; style-src &#x27;unsafe-inline&#x27;">' in page
    shape = Shape()
    shape.feed(page)
    assert "script" not in shape.tags and not {"link", "img", "iframe", "form", "object", "embed"} & shape.tags
    assert not any(name.startswith("on") or name in ("src", "style", "action") for _, name in shape.attrs)
    assert shape.links and set(shape.links) <= set(REPORT_LINKS)   # only links from our own config
    assert "http://" not in page and all(url.startswith("https://") for url in shape.links)
    text = " ".join(shape.text)
    assert made["fingerprint"] in text
    assert "The JSON file is the record. This page is a readable copy and is not signed." in text
    assert "cd backend && .venv/bin/python -m evidence verify" in text
    assert "Demo data" in text and demo_flow.lab.mode.line in text
    # the one allowed use of the word, and no scores or time-to-hack
    assert DISCLAIMER in text and text.lower().count("secure") == text.count(DISCLAIMER) == 1
    for word in ("security score", "time to hack", "time-to-hack", "unbreakable"):
        assert word not in text.lower()
    # the results a reader needs are there, with where each number came from
    for words in ("3 of 484 official cases wrong", "484 of 484 official cases right", "No slowdown beyond measured noise",
                  "for scale only", "Before: acme-sign 1.4.2", "After: acme-sign 1.4.3", "reference, not production",
                  "Fingerprint of these details (SHA-256)", "from the file", "measured"):
        assert words in text, words
    assert json.loads(raw)["evidence"]["tests"][0]["spec_hash"] in text


def test_signing_key_is_made_once_and_kept_private(tmp_path):
    lab = make_lab(tmp_path)
    lab.stop()
    key_path, public_path = tmp_path / "data" / SIGNING_KEY_FILE, tmp_path / "data" / PUBLIC_KEY_FILE
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    before, public = key_path.read_bytes(), public_path.read_text().strip()
    assert re.fullmatch(r"[0-9a-f]{64}", public)
    assert ensure_signing_key(tmp_path / "data") == public and key_path.read_bytes() == before   # not made again
    public_path.unlink()
    assert ensure_signing_key(tmp_path / "data") == public and public_path.read_text().strip() == public
    # nothing in the module hands the private key out
    assert not [n for n in evidence_export.__all__ if "private" in n.lower()]


def test_an_unreadable_signing_key_stops_the_download_with_a_plain_message(lab):
    plan = demo_plan(lab)
    run_kind(lab, plan, "certificate")
    (lab.settings.data_dir / SIGNING_KEY_FILE).write_bytes(b"not a key")
    try:
        lab.export_evidence(plan.id)
    except Exception as exc:
        assert exc.__class__.__name__ == "Conflict" and "signing key" in str(exc) and "not a key" not in str(exc)
    else:
        raise AssertionError("the download should have been refused")


def test_routes_download_both_files_and_need_a_login(client, anon_client):
    imp = start(client)
    plan = client.post(f"/api/import/{imp['id']}/plan").json()
    pid = plan["id"]
    nothing = client.post(f"/api/plans/{pid}/evidence")
    assert nothing.status_code == 409 and nothing.json()["error"]["message"] == "Run a test first, so there is something to download."
    assert client.post("/api/plans/999/evidence").status_code == 404
    client.post(f"/api/plans/{pid}/tests/{plan['tests'][1]['id']}/run")
    wait(client, pid)
    made = client.post(f"/api/plans/{pid}/evidence").json()
    assert sorted(made) == ["created_at", "fingerprint", "fingerprint_label", "html", "id", "json", "message", "verify_hint"]
    assert made["fingerprint_label"] == "Fingerprint (SHA-256)" and re.fullmatch(r"[0-9a-f]{64}", made["fingerprint"])
    assert made["message"] == "Two files were downloaded: the evidence (JSON) and a readable report (HTML). The JSON file is the record."
    assert made["json"]["url"] == f"/api/evidence/{made['id']}/json" and made["html"]["url"] == f"/api/evidence/{made['id']}/html"
    assert re.fullmatch(r"evidence-lab-evidence-\d{8}-\d{6}\.json", made["json"]["filename"])
    assert re.fullmatch(r"evidence-lab-report-\d{8}-\d{6}\.html", made["html"]["filename"])
    got = client.get(made["json"]["url"])
    assert got.status_code == 200 and got.headers["content-type"] == "application/json"
    assert got.headers["content-disposition"] == f'attachment; filename="{made["json"]["filename"]}"'
    assert json.loads(got.content)["fingerprint"] == made["fingerprint"]
    page = client.get(made["html"]["url"])
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert page.headers["content-disposition"] == f'attachment; filename="{made["html"]["filename"]}"'
    assert page.headers["x-content-type-options"] == "nosniff" and "default-src 'none'" in page.headers["content-security-policy"]
    assert made["fingerprint"].encode() in page.content
    assert client.get(made["json"]["url"]).content == got.content   # the stored bytes, not a new file each time
    for missing in ("/api/evidence/999/json", f"/api/evidence/{made['id']}/zip", f"/api/evidence/{made['id']}/key"):
        assert client.get(missing).status_code == 404
    assert client.get("/api/evidence/x/json").status_code == 422
    anon_client.cookies.clear()
    for method, path in (("POST", f"/api/plans/{pid}/evidence"), ("GET", made["json"]["url"]), ("GET", made["html"]["url"])):
        assert anon_client.request(method, path).status_code == 401


def test_no_route_returns_the_signing_key(client):
    paths = [getattr(r, "path", "") for r in client.app.routes]
    assert not [p for p in paths if "key" in p.lower()]
    source = (evidence_export.__file__ and open(evidence_export.__file__, encoding="utf-8").read())
    assert "print(" not in source.replace("fingerprint(", "") and "logging" not in source

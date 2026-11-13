"""Download evidence with the Fixes step in it: the connected code, every fix, and for a code change the change
itself, every proof (its record, fingerprint, review and runs in full), the pull request, the approvals and the
merge; the code each run ran on; that the checker accepts a file from every stage and refuses any changed field;
and the Fixes part of the readable report. One small plan is driven once, with a download at each stage."""
import hashlib
import json
import re
from types import SimpleNamespace

import pytest

from app import components, demo_repo
from app.canonical import canonical_bytes, loads_strict
from app.demo_server import KEY_FILE
from app.evidence_export import PUBLIC_KEY_FILE, REPORT_LINKS, SIGNING_KEY_FILE, ensure_signing_key, render_report_html, sign_envelope
from app.gitrepo import GitRepo
from app.present import DISCLAIMER
from app.reviewer import RuleReviewer
from conftest import make_lab
from evidence import FAILED, verify_bytes
from fixes_shapes import fix as fix_of, plain, section
from test_changes import proved, small_plan, tamper
from test_evidence import MARKUP, Shape, export, poisoned
from test_evidence_cli import run_cli
from test_secrets_scan import MARKERS, key_forms

FIX, TLS = "fix-ecdsa-range-check", "fix-tls-versions"
OLD_SHA256 = hashlib.sha256(components.lookup("acme-sign", "1.4.2").read_bytes()).hexdigest()
NEW_SHA256 = hashlib.sha256(components.lookup("acme-sign", "1.4.3").read_bytes()).hexdigest()
PROOF_CHANGED = "The stored proof no longer matches its fingerprint."
STAGES = ("not_connected", "failed", "ready", "opened", "merged", "retested")


def stage(lab, plan_id) -> SimpleNamespace:
    made, raw, report = export(lab, plan_id)
    return SimpleNamespace(made=made, raw=raw, report=report.decode("utf-8"), evidence=loads_strict(raw)["evidence"],
                           fixes=lab.fixes_view(plan_id), lab=lab.lab_view(plan_id), states=lab.fix_states(plan_id))


def sha256_of(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def report_text(page: str, part: str = "4. Fixes") -> str:
    """The words of a report from one heading on, as a reader sees them."""
    shape = Shape()
    shape.feed(page[page.index(f"<h2>{part}</h2>"):])
    return re.sub(r"\s+", " ", " ".join(shape.text))


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    """Old TLS versions, certificate strength and bad signatures. The first proof fails (the server's address is
    unconfirmed while it runs), the second passes; then a pull request with two reviewers, the merge and Retest now."""
    lab = make_lab(tmp_path_factory.mktemp("fixes-evidence"))
    try:
        plan = small_plan(lab)
        lab.verify(plan.imp["id"])
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 120)
        seen = {"not_connected": stage(lab, plan.id)}
        address = plan.imp["addresses"][0]["address"]
        lab.confirm_address(plan.imp["id"], address, False)
        lab.connect_code(plan.id)
        lab.wait_until_idle(plan.id, 120)
        seen["failed"] = stage(lab, plan.id)
        lab.confirm_address(plan.imp["id"], address, True)
        lab.run_proof_again(plan.id, FIX)
        lab.wait_until_idle(plan.id, 120)
        seen["ready"] = stage(lab, plan.id)
        lab.open_pull_request(plan.id, FIX, ["you", "a"])
        lab.approve(plan.id, FIX, "you")
        seen["opened"] = stage(lab, plan.id)
        lab.approve(plan.id, FIX, "a")
        lab.merge(plan.id, FIX)
        seen["merged"] = stage(lab, plan.id)
        lab.retest_now(plan.id, FIX)
        lab.wait_until_idle(plan.id, 120)
        seen["retested"] = stage(lab, plan.id)
        public = (lab.settings.data_dir / PUBLIC_KEY_FILE).read_text().strip()
        yield SimpleNamespace(lab=lab, plan=plan, public=public, patch=lab.patch_file(plan.id, FIX), **seen)
    finally:
        lab.stop()


def code_entry(seen) -> dict:
    return next(f for f in seen.evidence["fixes"] if f["id"] == FIX)


# ---------------------------------------------------------------- what the file holds

def test_the_file_lists_every_fix_as_the_fixes_step_showed_it(flow):
    words = {"not_connected": "Code not connected", "failed": "Proof failed", "ready": "Ready for review", "opened": "Waiting for approval",
             "merged": "Merged", "retested": "Merged"}
    for name in STAGES:
        seen = getattr(flow, name)
        e = seen.evidence
        assert sorted(e) == ["app", "code", "component", "disclaimer", "fixes", "generated_at", "import", "mode_line", "retest", "schema",
                             "signer_key_fingerprint", "tests", "verify"]
        assert [(f["id"], f["kind"], f["status"]) for f in e["fixes"]] == [(FIX, "code", words[name]), (TLS, "text", "Text only")]
        for entry in e["fixes"]:
            shown = fix_of(seen.fixes, entry["id"])
            assert sorted(entry) == ["approvals", "change", "id", "kind", "merge", "proofs", "pull_request", "source", "status", "suggestion", "title"]
            assert (entry["title"], entry["status"], entry["source"]["text"]) == (shown["title"], shown["status"]["word"], shown["list_source"])
            assert entry["source"]["kind"] == "failed_tests"
        code, server = e["fixes"]
        # where each fix came from: the failed results it answers, by run
        failed = {t["kind"]: t["runs"][0]["run_id"] for t in e["tests"] if t["runs"] and t["runs"][0]["result"]["tone"] == "fail"}
        assert code["source"]["results"] == [{"item_id": flow.plan.item["bad_signatures"], "kind": "bad_signatures", "run_id": failed["bad_signatures"], "phase": "first"}]
        assert server["source"]["results"][0] == {"item_id": flow.plan.item["tls_versions"], "kind": "tls_versions", "run_id": failed["tls_versions"], "phase": "first"}
        assert code["suggestion"] is None
        # the text-only fix carries its whole suggestion, word for word as shown, and nothing else
        assert server["suggestion"] == section(fix_of(seen.fixes, TLS), "suggestion")["suggestion"]
        assert server["change"] is None and server["proofs"] == [] and server["pull_request"] is None and server["approvals"] == [] and server["merge"] is None
    # the retest's failed server result is one more result the suggestion answers
    assert [r["phase"] for r in flow.retested.evidence["fixes"][1]["source"]["results"]] == ["first", "retest"]


def test_the_connected_code_and_the_change(flow):
    before = flow.not_connected.evidence
    assert before["code"] is None
    assert code_entry(flow.not_connected)["change"] is None and code_entry(flow.not_connected)["proofs"] == []
    bundled_head = GitRepo(demo_repo.bundled("acme-sign")).branch("main")
    for name in STAGES[1:]:
        seen = getattr(flow, name)
        state = next(f for f in seen.states if f["id"] == FIX)
        code = seen.evidence["code"]
        assert sorted(code) == ["base_commit", "branch", "component", "connected_at", "is_demo", "repository"]
        assert (code["repository"], code["branch"], code["is_demo"]) == ("acme-sign", "main", True)
        assert code["component"] == {"name": "acme-sign", "version": "1.4.2"} and re.fullmatch(r"[0-9a-f]{40}", code["base_commit"])
        assert code["base_commit"] == bundled_head  # the copy starts from the bundled repository's commit
        change = code_entry(seen)["change"]
        assert sorted(change) == ["base_commit", "branch", "built", "created_at", "files", "fix_key", "head_commit", "label", "patch",
                                  "proposed_by", "size", "source_kind", "template_id", "title", "written_by"]
        assert (change["template_id"], change["fix_key"], change["written_by"], change["label"]) == (
            "ecdsa-range-check", "ecdsa-range-check", "fix_template", "From a fix template")
        assert change["proposed_by"] == "isogeny.rule-engine/1" and change["source_kind"] == "failed_tests"
        assert (change["title"], change["branch"], change["size"]) == ("Reject signatures whose r or s is out of range", "fix/ecdsa-range-check",
                                                                       "3 lines added and 1 removed")
        # the commits in full (the screens shorten them)
        assert change["base_commit"] == code["base_commit"] == state["change"]["base_commit"] and change["head_commit"] == state["change"]["head_commit"]
        assert len(change["head_commit"]) == 40 and change["head_commit"] != change["base_commit"]
        (file,) = change["files"]
        assert file == {"name": "acme_sign.py", "added": 3, "removed": 1, "old_sha256": OLD_SHA256, "new_sha256": NEW_SHA256,
                        "old_blob": state["change"]["files"][0]["old_blob"], "new_blob": state["change"]["files"][0]["new_blob"]}
        # the code check: byte for byte our registered 1.4.3
        assert change["built"] == {"file": "acme_sign.py", "sha256": NEW_SHA256, "matches": {"name": "acme-sign", "version": "1.4.3"}}
        # the patch text is the downloadable patch, whole
        assert change["patch"] == flow.patch[1].decode("utf-8")
        assert '+VERSION = "1.4.3"' in change["patch"] and "+    if not (1 <= r < N and 1 <= s < N):" in change["patch"]


def test_every_proof_is_in_the_file_with_its_record_fingerprint_review_and_runs(flow):
    assert [len(code_entry(getattr(flow, name))["proofs"]) for name in STAGES] == [0, 1, 2, 2, 2, 2]
    failed_only = code_entry(flow.failed)["proofs"][0]
    for name in STAGES[2:]:
        seen = getattr(flow, name)
        first, second = code_entry(seen)["proofs"]
        assert first == failed_only  # an earlier proof is exported the same way every time
        for proof in (first, second):
            assert sorted(proof) == ["baseline_version", "id", "outcome", "record", "record_sha256", "review", "started_at", "tests", "version"]
            assert (proof["baseline_version"], proof["version"]) == ("1.4.2", "1.4.3")
            record, review = proof["record"], proof["review"]
            # the evidence fingerprint of the proof is the SHA-256 of the record in the file: anyone can work it out again
            assert sha256_of(record) == proof["record_sha256"] == review["record_sha256"]
            assert record["schema"] == "isogeny.proof/1" and record["proposed_by"] == "isogeny.rule-engine/1"
            assert record["built"] == code_entry(seen)["change"]["built"] and record["change"]["head_commit"] == code_entry(seen)["change"]["head_commit"]
            assert review["reviewer"] == "isogeny.rule-reviewer/1" != record["proposed_by"] and review["believed"] is True and review["problem"] is None
            # ... and the review can be made again from the record in the file, by the same rule
            again = RuleReviewer().review_proof(record)
            assert (again["record_sha256"], again["offered"], again["checks"], again["counts"]) == (
                review["record_sha256"], review["offered"], review["checks"], review["counts"])
            assert [t["kind"] for t in proof["tests"]] == [t["kind"] for t in record["tests"]] == ["tls_versions", "certificate", "bad_signatures"]
            exported = {t["item_id"]: t["runs"][0] for t in seen.evidence["tests"]}
            for test, recorded, checked in zip(proof["tests"], record["tests"], again["tests"]):
                assert sorted(test) == ["check", "first", "item_id", "kind", "run", "shown", "target", "title"]
                # the first result it was compared with is the one Evidence Lab shows, by fingerprint
                assert test["first"]["run_sha256"] == recorded["first"]["run_sha256"] == exported[test["item_id"]]["run_sha256"]
                assert test["first"]["run_id"] == exported[test["item_id"]]["run_id"]
                # the proof run in full: its run record as fingerprinted, the separate review of it, the worded result
                run = test["run"]
                assert run["phase"] == run["record"]["phase"] == "proof"
                assert sha256_of(run["record"]) == run["run_sha256"] == run["review"]["run_sha256"] == recorded["proof"]["run_sha256"]
                assert run["review"]["reviewer"] == "isogeny.rule-reviewer/1" and run["review"]["verdict"]["code"] == run["result"]["code"] == recorded["proof"]["code"]
                assert run["review"]["control"]["outcome"] == recorded["proof"]["control_outcome"]
                assert (test["check"]["group"], test["check"]["ok"], test["check"]["reason"]) == (checked["group"], checked["ok"], checked["reason"])
                assert test["shown"]["label"] == run["result"]["label"]
        assert first["outcome"] == "The proof did not pass." and first["review"]["offered"] is False
        assert first["review"]["checks"] == {"code_is_ours": True, "changed_code_passed": True, "controls_behaved": True, "server_unchanged": False}
        assert [t["check"]["text"] for t in first["tests"]] == ["Not the same as before", "Not the same as before", "Passed"]
        assert [t["run"]["result"]["label"] for t in first["tests"]] == ["Couldn't run (address not confirmed)"] * 2 + ["Passed"]
        assert second["outcome"] == "The proof passed." and second["review"]["offered"] is True and second["id"] != first["id"]
        assert second["review"]["counts"] == {"tests": 3, "code": 1, "code_ok": 1, "server": 2, "server_ok": 2}
        assert [t["check"]["text"] for t in second["tests"]] == ["Same as before", "Same as before", "Passed"]
        # the fingerprint on the screen (Technical details) is the one in the file
        shown = {f["label"]: plain(f["value"]) for f in section(fix_of(seen.fixes, FIX), "details")["facts"]}
        assert shown["Evidence fingerprint of the proof (SHA-256)"] == second["record_sha256"]
        # the cells are worded as the Fixes step words them
        rows = {r["kind"]: r for table in section(fix_of(seen.fixes, FIX), "proof")["tables"] for r in table["rows"]}
        for test in second["tests"]:
            assert test["shown"] == rows[test["kind"]]["proof"] and test["first"]["short"] == rows[test["kind"]]["before"]["short"]
            assert test["run"]["result"]["control"]["line"] == rows[test["kind"]]["control"] and test["check"]["text"] == rows[test["kind"]]["check"]["text"]
        # a proof run of the signing test ran on the change's branch; a server test ran no code of ours
        bad = next(t for t in second["tests"] if t["kind"] == "bad_signatures")["run"]
        assert bad["code"] == {"source": "repository", "component_name": "acme-sign", "component_version": "1.4.3", "file_sha256": NEW_SHA256,
                               "repository": "acme-sign", "branch": "fix/ecdsa-range-check", "commit": code_entry(seen)["change"]["head_commit"],
                               "change_id": bad["code"]["change_id"], "pull_request_number": None}
        assert all(t["run"]["code"] is None for t in second["tests"] if t["kind"] != "bad_signatures")


def test_the_pull_request_the_approvals_and_the_merge(flow):
    for name in ("not_connected", "failed", "ready"):
        entry = code_entry(getattr(flow, name))
        assert entry["pull_request"] is None and entry["approvals"] == [] and entry["merge"] is None
    opened, merged = code_entry(flow.opened), code_entry(flow.merged)
    passed = opened["proofs"][1]
    assert opened["pull_request"] == {"number": 1, "title": "Reject signatures whose r or s is out of range", "proof_id": passed["id"],
                                      "reviewers": ["you", "a"], "opened_at": opened["pull_request"]["opened_at"]}
    stamp = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z"
    assert re.fullmatch(stamp, opened["pull_request"]["opened_at"])
    # each approval with its name and time; a reviewer who has not approved is listed as such
    assert [(a["reviewer"], a["name"], bool(a["approved_at"])) for a in opened["approvals"]] == [("you", "You", True), ("a", "Demo reviewer A", False)]
    assert opened["merge"] is None
    assert [(a["reviewer"], a["name"]) for a in merged["approvals"]] == [("you", "You"), ("a", "Demo reviewer A")]
    assert all(re.fullmatch(stamp, a["approved_at"]) for a in merged["approvals"])
    assert merged["pull_request"] == opened["pull_request"] and sorted(merged["merge"]) == ["merge_commit", "merged_at"]
    assert re.fullmatch(r"[0-9a-f]{40}", merged["merge"]["merge_commit"]) and re.fullmatch(stamp, merged["merge"]["merged_at"])
    assert opened["pull_request"]["opened_at"] <= merged["approvals"][0]["approved_at"] <= merged["approvals"][1]["approved_at"] <= merged["merge"]["merged_at"]
    assert code_entry(flow.retested)["merge"] == merged["merge"]


def test_every_exported_run_says_which_code_it_ran_on(flow):
    keys = ["branch", "change_id", "commit", "component_name", "component_version", "file_sha256", "pull_request_number", "repository", "source"]
    for name in STAGES:
        for test in getattr(flow, name).evidence["tests"]:
            for run in test["runs"]:
                if test["kind"] == "bad_signatures":
                    assert sorted(run["code"]) == keys and run["code"]["component_name"] == "acme-sign"
                else:
                    assert run["code"] is None  # a server test runs no code of ours
                assert "code" not in run["record"]  # kept beside the run record, not inside what was fingerprinted
    first, after = next(t for t in flow.retested.evidence["tests"] if t["kind"] == "bad_signatures")["runs"]
    assert first["code"] == {"source": "bundled", "component_name": "acme-sign", "component_version": "1.4.2", "file_sha256": OLD_SHA256,
                             "repository": None, "branch": None, "commit": None, "change_id": None, "pull_request_number": None}
    merge = code_entry(flow.retested)["merge"]
    assert after["code"] == {"source": "repository", "component_name": "acme-sign", "component_version": "1.4.3", "file_sha256": NEW_SHA256,
                             "repository": "acme-sign", "branch": "main", "commit": merge["merge_commit"], "change_id": after["code"]["change_id"],
                             "pull_request_number": 1}
    # the worded result carries the same in its run record, and the one line that stands in place of the suggested fix
    meta = {m["label"]: m["value"] for m in after["result"]["run_record"]["meta"]}
    assert meta["Code"] == (f"the merged fix: branch main, commit {merge['merge_commit'][:7]} (pull request #1), the same byte for byte as our "
                            "bundled acme-sign 1.4.3")
    assert first["result"]["suggested_fix"] is None
    assert first["result"]["fix_line"] == {"fix_id": FIX, "lead": "Fix merged:", "rest": "3 lines added and 1 removed, proof passed"}
    assert after["result"]["fix_line"] is None and after["result"]["suggested_fix"] == "None needed. Every bad signature was rejected."
    retest = flow.retested.evidence["retest"]
    assert retest["columns"]["after_heading"] == f"After: acme-sign 1.4.3, the merged fix (commit {merge['merge_commit'][:7]})"
    assert retest["code_line"] == ("Code they ran on: before, the bundled demo version of acme-sign 1.4.2; after, " + meta["Code"] + ".")


# ---------------------------------------------------------------- the checker

def leaves(value, path=()):
    """Every single value inside a part of the evidence, with the path to it."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, (*path, key))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from leaves(item, (*path, i))
    else:
        yield path, value


def changed(value):
    """The same kind of value, a little different: what an edit by hand would look like."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return (("0" if value[0] != "0" else "1") + value[1:]) if value else "x"
    return 0  # was null


def with_change(envelope: dict, path: tuple) -> bytes:
    """The file with one value changed, written exactly the way the app writes files (so only the content differs)."""
    target = envelope["evidence"]
    for key in path[:-1]:
        target = target[key]
    kept = target[path[-1]]
    target[path[-1]] = changed(kept)
    try:
        return canonical_bytes(envelope)
    finally:
        target[path[-1]] = kept


def test_the_checker_accepts_a_file_from_every_stage(flow, tmp_path):
    for name in STAGES:
        seen = getattr(flow, name)
        outcome = verify_bytes(seen.raw, flow.public)
        assert outcome.ok and outcome.message == "Evidence verified" and outcome.fingerprint == seen.made["fingerprint"], name
        assert seen.raw == canonical_bytes(loads_strict(seen.raw))
    # the command a person runs, on the last file
    path = tmp_path / flow.retested.made["json"]["filename"]
    path.write_bytes(flow.retested.raw)
    done = run_cli("verify", str(path), "--data-dir", str(flow.lab.settings.data_dir))
    assert done.returncode == 0 and done.stdout.splitlines()[0] == "Evidence verified"
    assert f"Fingerprint (SHA-256): {flow.retested.made['fingerprint']}" in done.stdout


def test_the_checker_refuses_a_file_in_which_any_fixes_or_proof_field_was_changed(flow, tmp_path):
    envelope = loads_strict(flow.retested.raw)
    evidence = envelope["evidence"]
    entry = next(f for f in evidence["fixes"] if f["id"] == FIX)
    passed = entry["proofs"][1]
    # every single value of: the connected code, the change, both proofs' records and reviews, each proof test's summary,
    # the pull request, the approvals, the merge, the text-only fix; and of each run, the code it ran on
    paths = [("code", *p) for p, _ in leaves(evidence["code"])]
    fix_at = evidence["fixes"].index(entry)
    for key in ("id", "kind", "title", "status", "source", "change", "pull_request", "approvals", "merge"):
        paths += [("fixes", fix_at, key, *p) for p, _ in leaves(entry[key])]
    for n, proof in enumerate(entry["proofs"]):
        for key in ("id", "started_at", "baseline_version", "version", "record", "record_sha256", "outcome", "review"):
            paths += [("fixes", fix_at, "proofs", n, key, *p) for p, _ in leaves(proof[key])]
        for t, test in enumerate(proof["tests"]):
            for key in ("item_id", "kind", "title", "target", "first", "shown", "check"):
                paths += [("fixes", fix_at, "proofs", n, "tests", t, key, *p) for p, _ in leaves(test[key])]
            for key in ("phase", "run_id", "run_sha256", "review", "code"):
                paths += [("fixes", fix_at, "proofs", n, "tests", t, "run", key, *p) for p, _ in leaves(test["run"][key])]
    paths += [("fixes", 1 - fix_at, *p) for p, _ in leaves(evidence["fixes"][1 - fix_at])]
    for t, test in enumerate(evidence["tests"]):
        for r, run in enumerate(test["runs"]):
            paths += [("tests", t, "runs", r, "code", *p) for p, _ in leaves(run["code"])]
            paths += [("tests", t, "runs", r, "result", "fix_line", *p) for p, _ in leaves(run["result"]["fix_line"])]
    assert len(paths) > 500 and len(set(paths)) == len(paths)
    # ... and a sample of the long parts (the proof runs' own records and worded results)
    deep = [("fixes", fix_at, "proofs", 1, "tests", t, "run", key, *p) for t, test in enumerate(passed["tests"]) for key in ("record", "result")
            for p, _ in leaves(test["run"][key])]
    paths += deep[::7]
    for path in paths:
        outcome = verify_bytes(with_change(envelope, path), flow.public)
        assert outcome.code == FAILED, f"a change at {'/'.join(map(str, path))} was not noticed"
        assert outcome.message == "Evidence NOT verified: the fingerprint does not match the evidence. The evidence was changed after it was signed."
    # the checks that matter most to a reader, by name: none of them can be flipped
    for path in (("fixes", fix_at, "status"), ("fixes", fix_at, "proofs", 0, "review", "offered"), ("fixes", fix_at, "proofs", 0, "outcome"),
                 ("fixes", fix_at, "proofs", 1, "record_sha256"), ("fixes", fix_at, "change", "built", "matches", "version"),
                 ("fixes", fix_at, "approvals", 1, "approved_at"), ("fixes", fix_at, "merge", "merge_commit"), ("fixes", fix_at, "change", "patch")):
        assert path in paths
    # a changed field with the fingerprint worked out again: the signature no longer fits
    edited = json.loads(with_change(envelope, ("fixes", fix_at, "proofs", 0, "review", "offered")))
    edited["fingerprint"] = sha256_of(edited["evidence"])
    outcome = verify_bytes(canonical_bytes(edited), flow.public)
    assert outcome.code == FAILED and "signature is not valid" in outcome.message
    # ... and signed again with another key: not the signer you trust
    ensure_signing_key(tmp_path / "theirs")
    forged = verify_bytes(sign_envelope(edited["evidence"], tmp_path / "theirs"), flow.public)
    assert forged.code == FAILED
    # the command says the same
    path = tmp_path / "edited.json"
    path.write_bytes(with_change(envelope, ("fixes", fix_at, "merge", "merge_commit")))
    done = run_cli("verify", str(path), "--data-dir", str(flow.lab.settings.data_dir))
    assert done.returncode == 1 and done.stdout.startswith("Evidence NOT verified: the fingerprint does not match the evidence.")


def test_no_private_key_in_the_files_with_the_fixes_in_them(flow):
    data_dir = flow.lab.settings.data_dir
    secrets = key_forms(data_dir / SIGNING_KEY_FILE) + key_forms(data_dir / KEY_FILE)
    for name in STAGES:
        seen = getattr(flow, name)
        for place, text in (("evidence JSON", seen.raw.decode("utf-8")), ("HTML report", seen.report)):
            for i, form in enumerate(secrets):
                leaked = form in text  # (kept out of the assert, so a failure never prints the key)
                assert not leaked, f"a private key (form {i}) appears in the {place} at stage {name}"
            for marker in MARKERS:
                marked = marker in text
                assert not marked, f"a private-key marker ({marker}) appears in the {place} at stage {name}"
    assert flow.public in flow.retested.raw.decode("utf-8")  # only the public half of the signing key is in the download


# ---------------------------------------------------------------- the readable report

def test_the_report_has_a_readable_fixes_part(flow):
    before = report_text(flow.not_connected.report)
    assert before.startswith("4. Fixes acme-sign accepts out-of-range signatures Code not connected Came from 1 failed test: Bad signatures")
    assert ("A fix template exists for this failure. The code was not connected when this file was made, so no change had been prepared "
            "or proved.") in before
    assert "Code connected" not in before and "Pull request" not in before and "Merged" not in before
    text = report_text(flow.retested.report)
    change, merge = code_entry(flow.retested)["change"], code_entry(flow.retested)["merge"]
    passed = code_entry(flow.retested)["proofs"][1]
    for words in (
            f"Code connected: the app's own copy of the repository acme-sign, branch main, commit {change['base_commit']} (acme-sign 1.4.2). demo",
            "acme-sign accepts out-of-range signatures Merged Came from 1 failed test: Bad signatures",
            "The change From a fix template", "Reject signatures whose r or s is out of range. 3 lines added and 1 removed.",
            f"Change branch fix/ecdsa-range-check, commit {change['head_commit']}", f"Starting point: commit {change['base_commit']}",
            f"File acme_sign.py: SHA-256 before {OLD_SHA256}, after {NEW_SHA256}",
            f"Code check: the built file (SHA-256 {NEW_SHA256}) is byte for byte the same as our bundled demo component acme-sign 1.4.3, and "
            "that component is what the proof ran.",
            "The change as a patch", "Proof 1 of 2", "The proof did not pass. Started", "Proof 2 of 2", "The proof passed. Started",
            f"Evidence fingerprint of the proof (SHA-256): {passed['record_sha256']}", "Test Before On the changed code Rule check",
            "Bad signatures Failed Accepts the signature r=0, s=0. One cause: no range check. Passed Rejects r=0, s=0 and every other bad "
            "signature tried. Control: a deliberately broken signer failed this test, as expected. Passed",
            "Old TLS versions Failed Server accepted TLS 1.2. Failed Server still accepts TLS 1.2. This change doesn't touch the server.",
            "Same as before", "Not the same as before",
            "The JSON file holds every run of this proof in full (its run record, fingerprint and review), and the proof record this "
            "fingerprint is made from.",
            "Pull request #1 Reject signatures whose r or s is out of range. Opened", "It stays inside the app.", "You: approved",
            "Demo reviewer A: approved", f"by the person logged in, after confirming (merge commit {merge['merge_commit']}). Nothing was deployed.",
            "Server accepts TLS 1.2 Text only Came from 1 failed test: Old TLS versions",
            "The suggestion (text only: the app has not applied it or tested it)", "Where the setting lives", "Two ways to fix it",
            "Option 2: the exact settings", "End of report. The JSON file is the record. This page is a readable copy and is not signed."):
        assert words in text, words
    # the lock-out warning comes before any setting that could be copied
    assert text.index("Before you switch TLS 1.2 off:") < text.index("ssl_protocols TLSv1.3;")
    # the patch is in the report, and the two changed lines with it
    assert "+    if not (1 &lt;= r &lt; N and 1 &lt;= s &lt; N):" in flow.retested.report and "+VERSION = &quot;1.4.3&quot;" in flow.retested.report
    # the results part says which code each result ran on, and points from a failure to its fix
    whole = report_text(flow.retested.report, "3. Tests and results")
    assert "Code they ran on: before, the bundled demo version of acme-sign 1.4.2; after, the merged fix: branch main, commit" in whole
    assert "Code: the bundled demo version of acme-sign 1.4.2 demo" in whole and "After: acme-sign 1.4.3, the merged fix (commit " in whole
    assert "Fix merged: 3 lines added and 1 removed, proof passed. It is in part 4, Fixes." in whole
    assert "Text-only suggestion: a server setting. It is in part 4, Fixes." in whole
    # one approval missing: said plainly
    assert "Demo reviewer A: has not approved" in report_text(flow.opened.report) and "Merged" not in report_text(flow.opened.report)


def test_the_report_calls_nothing_passed_or_merged_that_the_records_do_not(flow):
    failed = report_text(flow.failed.report)
    assert "acme-sign accepts out-of-range signatures Proof failed" in failed and "The proof did not pass. Started" in failed
    assert "The proof passed" not in failed and "Pull request" not in failed and "Merged" not in failed and "Proof 1 of" not in failed
    for name in STAGES:
        page = getattr(flow, name).report
        text = report_text(page)
        # the one allowed use of the word, and no scores or time-to-hack
        shape = Shape()
        shape.feed(page)
        words = " ".join(shape.text)
        assert words.lower().count("secure") == words.count(DISCLAIMER) == 1
        for banned in ("security score", "time to hack", "time-to-hack", "unbreakable"):
            assert banned not in words.lower()
        assert ("The proof passed." in text) == (name not in ("not_connected", "failed"))
        assert ("Nothing was deployed." in text) == (name in ("merged", "retested"))
        # static, as before: no scripts, no outside resources, only our own links
        assert "script" not in shape.tags and not {"link", "img", "iframe", "form", "object", "embed"} & shape.tags
        assert set(shape.links) <= set(REPORT_LINKS)


def test_the_fixes_part_escapes_everything(flow):
    """Every text in the evidence gets markup added (the patch, the commit ids, the names, the sentences). None of
    it may come out as markup."""
    envelope = json.loads(flow.retested.raw)
    evidence = poisoned(envelope["evidence"])
    evidence["import"]["is_demo"], evidence["retest"]["columns"] = True, envelope["evidence"]["retest"]["columns"]
    page = render_report_html({"evidence": evidence, "fingerprint": envelope["fingerprint"]}).decode("utf-8")
    part = page[page.index("<h2>4. Fixes</h2>"):]
    assert part.count("&lt;script&gt;alert(1)&lt;/script&gt;") > 100
    assert "<script" not in page.lower() and "<img" not in page.lower() and '"onmouseover' not in page
    shape = Shape()
    shape.feed(page)
    assert shape.tags <= {"html", "head", "meta", "title", "style", "body", "main", "h1", "h2", "h3", "h4", "p", "div", "span", "table",
                          "thead", "tbody", "tr", "th", "td", "pre", "code", "ul", "li", "details", "summary", "strong", "a"}
    assert {name for _, name in shape.attrs} <= {"class", "href", "rel", "charset", "http-equiv", "content", "name", "lang"}
    assert shape.links == [] and MARKUP in "".join(shape.text)


# ---------------------------------------------------------------- what the file says when the records do not hold up

def test_a_proof_that_is_no_longer_believed_an_interrupted_one_and_code_that_is_not_ours(flow):
    lab = flow.lab
    # a stored proof run changed by hand after the proof had passed
    plan = small_plan(lab)
    ready = proved(lab, plan)
    run_id = next(r["proof"]["run_id"] for r in ready["proof"]["tests"] if r["kind"] == "bad_signatures")
    tamper(lab, f"""UPDATE test_runs SET raw = json_set(raw, '$.subject.answers."r0-s0"', 'accept') WHERE id = {run_id}""")
    seen = stage(lab, plan.id)
    entry = code_entry(seen)
    (proof,) = entry["proofs"]
    assert entry["status"] == "Proof failed" and proof["outcome"] == PROOF_CHANGED
    assert proof["review"] == {"reviewed_at": proof["review"]["reviewed_at"], "believed": False, "offered": False, "problem": PROOF_CHANGED,
                               "record_sha256": None, "checks": None, "counts": None, "reviewer": None}
    assert all(test["check"] is None for test in proof["tests"])  # nothing of the stored answer is passed on
    assert next(t for t in proof["tests"] if t["kind"] == "bad_signatures")["shown"]["label"] == "Couldn't trust this run"
    assert sha256_of(proof["record"]) == proof["record_sha256"]  # the record as it now stands; no review vouches for it
    text = report_text(seen.report)
    assert f"{PROOF_CHANGED} Started" in text and "The proof passed" not in text and "Evidence fingerprint of the proof" not in text
    assert verify_bytes(seen.raw, flow.public).ok  # the file itself is what the app made, and says what the app found
    # an interrupted proof: no review
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(lab, "_submit", lambda *a, **k: None)
        lab.connect_code(plan.id)
    seen = stage(lab, plan.id)
    (proof,) = code_entry(seen)["proofs"]
    assert proof["review"] is None and proof["outcome"] == "This proof has no review: it was interrupted before every test had run."
    assert all(test["run"] is None and test["shown"] is None and test["check"] is None and test["first"]["label"] for test in proof["tests"])
    assert "This proof has no review: it was interrupted before every test had run. Started" in report_text(seen.report)
    # a change whose code is not one of our components: recorded, never run
    plan = small_plan(lab)
    lab.run_all(plan.id)
    lab.wait_until_idle(plan.id, 120)
    propose = lab.engine.propose_change

    def not_ours(request):
        reply = propose(request)
        reply["files"]["acme_sign.py"] += "NOT_OURS = 1\n"
        return reply

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(lab.engine, "propose_change", not_ours)
        lab.connect_code(plan.id)
    seen = stage(lab, plan.id)
    entry = code_entry(seen)
    assert entry["status"] == "Proof failed" and entry["proofs"] == [] and entry["change"]["built"]["matches"] is None
    assert entry["change"]["built"]["sha256"] != NEW_SHA256 and "+NOT_OURS = 1" in entry["change"]["patch"]
    text = report_text(seen.report)
    assert f"Code check: the built file (SHA-256 {entry['change']['built']['sha256']}) is not one of our demo components, so nothing was run." in text
    assert "The proof passed" not in text and "Proof" not in text.replace("Proof failed", "")

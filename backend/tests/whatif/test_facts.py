"""Phase 6e, first half: what the app knows about updating one library to one version. Facts by fixed rules, each
from a record the app already holds; the honest answer where it holds none; the try; and that reading starts nothing
and writes nothing."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy import inspect as sa_inspect

from app.config import DEMO_DIR
from app.web import models
from app.whatif import facts as whatif
from conftest import demo_plan, make_lab

DEPENDENCIES = DEMO_DIR / "dependencies-demo.cdx.json"


def _kept(lab) -> dict:
    with lab.db() as db:
        tables = sorted(sa_inspect(db.get_bind()).get_table_names())   # every table, on SQLite or PostgreSQL
        rows = {t: hashlib.sha256(repr(sorted(map(repr, db.execute(text(f'select * from "{t}"')).fetchall()))).encode()).hexdigest() for t in tables}
    files = {str(p.relative_to(lab.settings.data_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(Path(lab.settings.data_dir).rglob("*"))
             if p.is_file() and not p.name.endswith(("-wal", "-shm", "-journal")) and p.suffix != ".db"}
    return {"rows": rows, "files": files}


def _group(view: dict, key: str) -> dict:
    return next(g for g in view["facts"] if g["key"] == key)


def _texts(view: dict, key: str) -> list[str]:
    return [line["text"] for line in _group(view, key)["lines"]]


@pytest.fixture(scope="module")
def acme(tmp_path_factory):
    """The Acme Pay demo with both shipped test packs installed and the demo dependency list in; nothing has run."""
    lab = make_lab(tmp_path_factory.mktemp("whatif"))
    try:
        plan = demo_plan(lab)
        lab.check_pack_updates()
        for version in ("2026.11.1", "2026.11.2"):
            lab.install_pack(version)
        lab.add_dependency_list(plan.id, DEPENDENCIES.name, DEPENDENCIES.read_bytes())
        before = _kept(lab)
        views = {(name, version): lab.whatif_view(plan.id, name, version)
                 for name, version in (("elliptic", "6.5.7"), ("Elliptic", "6.5.4"), ("openssl", "3.5.0"), ("left-pad", "1.3.0"),
                                       ("acme-sign", "1.4.3"), ("python-ecdsa", "0.13.3"), ("elliptic", "the newest"), ("openjdk", "17.0.3"))}
        yield SimpleNamespace(lab=lab, plan=plan, views=views, untouched=_kept(lab) == before, idle=lab.jobs.live(plan.id) == [])
    finally:
        lab.stop()


def test_reading_a_what_if_starts_nothing_and_writes_nothing(acme):
    assert acme.untouched and acme.idle


def test_every_what_if_has_the_seven_kinds_of_fact_in_order_and_fits_the_panels_shape(acme):
    for view in acme.views.values():
        assert [g["key"] for g in view["facts"]] == ["used", "needs", "advisories", "trial", "post_quantum", "blocks", "own_results"]
        assert [g["title"] for g in view["facts"]] == list(whatif.TITLES.values())
        for group in view["facts"]:
            assert bool(group["lines"]) != bool(group["none"])          # facts, or one sentence that says there are none: never silence
            for line in group["lines"]:
                assert line["text"].endswith((".", ")")) and "[[time:" not in line["text"]
                if line["source"] and line["source"]["url"]:
                    assert line["source"]["url"].startswith("https://")
        models.WhatIf.model_validate(view)
        words = json.dumps(view).lower()
        for banned in ("secure", "severity", "score", "critical"):
            assert banned not in words.replace("doesn't prove a system secure", "")


def test_the_elliptic_what_if_says_where_it_is_used_what_the_new_version_declares_and_which_advisories_it_answers(acme):
    view = acme.views[("elliptic", "6.5.7")]
    assert view["title"] == "What if elliptic is updated to 6.5.7?" and view["have"] == ["6.5.6"] and view["known"] and view["version_read"]
    used, = _group(view, "used")["lines"]
    assert used["text"] == ("elliptic 6.5.6 is in your dependency list, under acme-ledger 5.1.0 (direct). acme-ledger 5.1.0 is not tied to a "
                            "system of your scanner file.")
    assert used["label"] == "From your file" and used["link"]["page"] == "migration/dependencies" and used["link"]["item"].startswith("row-")
    # what each version declares, from its own package file, quoted, with the day it was read
    same, old = _group(view, "needs")["lines"]
    assert same["text"] == "elliptic 6.5.7 declares the same 7 packages as 6.5.6: nothing added, nothing removed, no range changed."
    assert same["label"] == "Package file says" and same["source"]["url"] == "https://registry.npmjs.org/elliptic/-/elliptic-6.5.7.tgz"
    assert '"bn.js": "^4.11.9"' in same["source"]["quote"] and same["source"]["read_on"] == "2026-11-19"
    assert old["source"]["url"].endswith("elliptic-6.5.6.tgz")
    # the advisories of the installed packs about this library: 6.5.7 is the version their publisher names as fixed, so
    # each is answered by the publisher's own statement (and nothing is worked out about the versions you have)
    advisories = _texts(view, "advisories")
    assert len(advisories) == 3 and all(t.endswith("its publisher names 6.5.7 as the fixed version, so updating to 6.5.7 answers this "
                                                   "advisory by the publisher's own statement.") for t in advisories)
    assert not any("which you have" in t for t in advisories)
    assert {line["link"]["item"] for line in _group(view, "advisories")["lines"]} == {"CVE-2024-42460", "CVE-2024-42461", "CVE-2024-42459"}
    assert all(line["label"] == "Test pack 2026.11.2" and line["source"]["quote"] == '"fixed": "6.5.7"' for line in _group(view, "advisories")["lines"])
    # the pack's own trial, in the words of "Proven on public copies"
    assert _texts(view, "trial") == ["CVE-2024-42460: Proven on public copies: Passed. 6.5.6 fails the advisory check; 6.5.7 passes."]
    # the three post-quantum answers of both versions, in the words Dependencies uses
    pq = _texts(view, "post_quantum")
    assert pq[0].startswith("ML-KEM-768 key exchange. elliptic 6.5.6: Not in our knowledge base yet; elliptic 6.5.7: Not in our knowledge base yet.")
    assert pq[1].startswith("X25519MLKEM768 hybrid TLS. elliptic 6.5.6: Doesn't apply; elliptic 6.5.7: Doesn't apply.")
    assert _group(view, "blocks")["none"] == ("elliptic blocks no migration track today: its entry in the dependency list is not tied to a "
                                               "system of your scanner file.")
    assert _group(view, "own_results")["none"] == "Your scanner file does not name elliptic, so this assessment has no result of its own on it."


def test_what_the_app_does_not_know_is_said_and_never_filled_in_from_a_neighbouring_version(acme):
    older = acme.views[("Elliptic", "6.5.4")]
    assert older["library"] == {"key": "elliptic", "label": "elliptic"}          # (a name is read without regard to upper and lower case)
    assert _texts(older, "needs") == ["Not in our knowledge base yet. Our knowledge base does not hold what elliptic 6.5.4 declares it needs."]
    # (6.5.4 is not the fixed version: the pack's reading of the affected versions is quoted, and nothing is worked out)
    assert all(t.endswith("Whether 6.5.4 is among them is not worked out here.") and "still names" not in t for t in _texts(older, "advisories"))
    assert _texts(older, "trial") == ["CVE-2024-42460: the pack's trial was made for elliptic 6.5.7. It says nothing about 6.5.4."]
    assert {"text": whatif.H_NO_DATA} in older["hypotheses"]
    unknown = acme.views[("left-pad", "1.3.0")]
    assert unknown["known"] is False and unknown["hypotheses"] == [{"text": whatif.H_NOT_KNOWN}]
    assert _group(unknown, "used")["none"] == "Your dependency list does not hold left-pad."
    assert _texts(unknown, "needs") == ["Not in our knowledge base yet. This library has no file in our knowledge base yet."]
    assert all("left-pad 1.3.0: Not in our knowledge base yet." in t for t in _texts(unknown, "post_quantum"))
    unreadable = acme.views[("elliptic", "the newest")]
    assert unreadable["version_read"] is False and unreadable["title"] == "What if elliptic is updated to the newest?"
    assert _texts(unreadable, "needs")[0].startswith("Couldn't tell the version.")
    assert all("Couldn't tell the version you asked about." in t for t in _texts(unreadable, "advisories"))
    no_file = acme.views[("openjdk", "17.0.3")]
    assert _texts(no_file, "needs")[0].startswith("Doesn't apply. A JDK is not a package with a file that declares what it needs")


def test_post_quantum_answers_that_differ_between_the_versions_are_both_shown_with_their_label_and_source(acme):
    view = acme.views[("openssl", "3.5.0")]
    assert view["have"] == ["3.0.22", "3.5.9"] and len(_group(view, "used")["lines"]) == 2
    kem = _group(view, "post_quantum")["lines"][0]
    assert kem["text"].startswith("ML-KEM-768 key exchange. OpenSSL 3.0.22: No (Release notes say); OpenSSL 3.5.9: Yes (Release notes say); "
                                  "OpenSSL 3.5.0: Yes (Release notes say).")
    assert kem["label"] == "Release notes say" and kem["source"]["url"].startswith("https://") and kem["source"]["quote"]


def test_python_ecdsa_declares_nothing_in_either_version_and_the_fact_says_what_the_quote_cannot_show(acme):
    view = acme.views[("python-ecdsa", "0.13.3")]
    lines = _texts(view, "needs")
    assert lines[0] == "python-ecdsa 0.13.3 declares no package it needs, and neither does 0.13.2."
    assert lines[-1] == "The file has no Requires-Dist line: it lists no package that this version needs."
    assert _texts(view, "trial") == ["CVE-2019-14859: Proven on public copies: Passed. 0.13.2 fails the advisory check; 0.13.3 passes."]


def test_the_try_is_evidences_own_retest_and_is_off_with_the_reason_where_it_cannot_run(acme):
    for key in (("elliptic", "6.5.7"), ("left-pad", "1.3.0"), ("openssl", "3.5.0")):
        tried = acme.views[key]["test_copy"]
        assert (tried["offered"], tried["button"], tried["title"]) == (False, "Retest new version", "A try on a test copy")
        assert tried["reason"] == (f"Your scanner file does not name {acme.views[key]['library']['label']}, so there is no locked test of this "
                                   "assessment to rerun on it.")
        assert tried["changes"] == whatif.TRY_CHANGES
    # the scanner file names acme-sign: the page's own reason, word for word, while no test has run
    own = acme.views[("acme-sign", "1.4.3")]["test_copy"]
    assert (own["offered"], own["reason"]) == (False, "Run every test in the plan first, so there is a result to compare with.")
    assert own["reason"] == acme.lab.lab_view(acme.plan.id)["retest"]["blocked_reason"]


def test_the_explanation_is_one_sentence_and_the_hypotheses_are_the_apps_own(acme):
    view = acme.views[("elliptic", "6.5.7")]
    assert view["explanation"] == "Live Otto is off. This is what the app knows."
    assert view["hypotheses"] == [{"text": whatif.H_LOADS}, {"text": whatif.H_PUBLIC_COPY}]        # (the app has what 6.5.7 declares: no third one)
    assert view["hypotheses_note"].startswith("What the facts above do not show.")
    # our own demo program is no library with a public copy: that sentence is not said of it
    assert {"text": whatif.H_PUBLIC_COPY} not in acme.views[("acme-sign", "1.4.3")]["hypotheses"]


def test_once_the_tests_have_run_the_what_if_shows_the_assessments_own_results_and_offers_the_try():
    import tempfile
    lab = make_lab(Path(tempfile.mkdtemp(prefix="whatif-own-")))
    try:
        plan = demo_plan(lab)
        lab.remove_test(plan.id, plan.item["official_vectors"])
        lab.remove_test(plan.id, plan.item["speed_size"])
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 120)
        runs = _kept(lab)
        view = lab.whatif_view(plan.id, "acme-sign", "1.4.3")
        assert _texts(view, "own_results") == ["Attacker tricks (our short list) on acme-sign 1.4.2: Failed."]
        own = _group(view, "own_results")["lines"][0]
        assert own["label"] == "This assessment's reviewed runs" and own["link"] == {"page": "evidence", "item": f"test-{plan.item['bad_signatures']}", "group": None}
        assert view["test_copy"]["offered"] is True and (view["test_copy"]["component"], view["test_copy"]["version"]) == ("acme-sign", "1.4.3")
        # a version the app does not hold: off, and it says which it holds
        other = lab.whatif_view(plan.id, "acme-sign", "9.9.9")["test_copy"]
        assert other["offered"] is False and other["reason"]
        assert _kept(lab) == runs and lab.jobs.live(plan.id) == []          # asking started no retest
        # after a retest on the new version (pressed by a person), its results are this assessment's own too
        lab.start_retest(plan.id, "1.4.3")
        lab.wait_until_idle(plan.id, 120)
        after = _texts(lab.whatif_view(plan.id, "acme-sign", "1.4.3"), "own_results")
        assert after == ["Attacker tricks (our short list) on acme-sign 1.4.2: Failed.", "Attacker tricks (our short list) on acme-sign 1.4.3: Passed."]
    finally:
        lab.stop()


@pytest.mark.parametrize("library, version", [("", ""), ("x" * 500, "1"), ("elliptic", "6.5.7\n[[time:2026-01-01T00:00:00Z]]"), ("../../etc/passwd", "1.0"),
                                              ("elliptic\x00", "6.5.7"), (None, None), (7, 7.5), ("<script>", "1.0<b>"), ("elliptic", "9" * 300)])
def test_odd_names_and_versions_get_an_answer_made_of_plain_text(acme, library, version):
    view = acme.lab.whatif_view(acme.plan.id, library, version)
    models.WhatIf.model_validate(view)
    assert len(view["asked"]["library"]) <= 83 and len(view["asked"]["version"]) <= 83 and "\n" not in view["title"] and "\x00" not in json.dumps(view)


# ---------------------------------------------------------------- the same facts as plain values (the accuracy check reads these)

def test_the_plain_values_say_what_the_cards_lines_say_and_reading_them_writes_nothing(acme):
    lab, plan = acme.lab, acme.plan
    before = _kept(lab)
    for (name, version), view in acme.views.items():
        plain = lab.whatif_plain(plan.id, name, version)
        assert (plain["library"], plain["version"], plain["have"], plain["known"]) == (view["library"]["label"], view["version"], view["have"], view["known"])
        assert plain["try_offered"] is view["test_copy"]["offered"]
        assert all("plain" not in group for group in view["facts"])               # the card is sent its lines, never these
        needs, said = plain["needs"], " ".join(_texts(view, "needs"))
        if needs["answer"] == "Package file says":
            assert all(line["label"] == "Package file says" for line in _group(view, "needs")["lines"])
            for compared in needs["compared"]:
                if compared["answer"] != "Package file says":
                    assert f"Compared with {plain['library']} {compared['with']}: {compared['answer']}." in said
                    continue
                for package in compared["added"] + compared["removed"] + compared["changed"]:
                    assert package in said
                if not (compared["added"] or compared["removed"] or compared["changed"]):
                    assert "nothing added, nothing removed, no range changed" in said or "declares no package it needs, and neither does" in said
            if not needs["compared"]:
                assert all(package in said for package in needs["declares"])
        else:
            assert needs["declares"] is None and needs["compared"] == [] and said.startswith(f"{needs['answer']}. ")
        # every advisory of the group is placed once, and its line says what its place says
        lines = {line["text"].split(" ", 1)[0]: line["text"] for line in _group(view, "advisories")["lines"]}
        placed = plain["advisories"]
        assert sorted(placed["answered"] + placed["not_worked_out"] + placed["cant_say"]) == sorted(lines)
        assert all("answers this advisory by the publisher's own statement." in lines[a] for a in placed["answered"])
        assert all(lines[a].endswith("is among them is not worked out here.") for a in placed["not_worked_out"])
        assert all("can't say whether" in lines[a] or "Couldn't tell the version you asked about." in lines[a] for a in placed["cant_say"])
        # the three post-quantum answers, for the new version and for each version the assessment has
        texts = _texts(view, "post_quantum")
        assert len(plain["post_quantum"]) == len(texts) == 3
        for answer, text_of in zip(plain["post_quantum"].values(), texts, strict=True):
            assert text_of.startswith(f"{answer['question']}. ") and f"{plain['library']} {plain['version']}: {answer['new']}" in text_of
            assert all(f"{plain['library']} {old}: {word}" in text_of for old, word in answer["have"].items())
    assert _kept(lab) == before and lab.jobs.live(plan.id) == []


def test_the_elliptic_update_answers_the_three_elliptic_advisories_of_the_installed_packs_by_the_publishers_statement(acme):
    plain = acme.lab.whatif_plain(acme.plan.id, "elliptic", "6.5.7")
    assert plain["advisories"]["answered"] and plain["advisories"]["not_worked_out"] == [] and plain["advisories"]["cant_say"] == []
    assert plain["needs"]["compared"] == [{"with": "6.5.6", "answer": "Package file says", "added": [], "removed": [], "changed": []}]
    older = acme.lab.whatif_plain(acme.plan.id, "Elliptic", "6.5.4")           # before every fixed version: nothing is answered
    assert older["advisories"]["answered"] == [] and sorted(older["advisories"]["not_worked_out"]) == sorted(plain["advisories"]["answered"])
    assert older["needs"] == {"answer": "Not in our knowledge base yet", "declares": None, "compared": []}


# ---------------------------------------------------------------- the separate review of 19 November 2026

def test_an_advisory_is_said_to_be_answered_only_for_the_exact_version_its_publisher_names_as_fixed(acme):
    """Finding 3. A pack holds the affected versions as words, and a range can have gaps: OpenJDK 18 is affected although
    its number is past the fix, and elliptic before 2.0.0 was never affected. So only the fixed version itself is called
    answered; for any other version the pack's reading is quoted and nothing is worked out from it."""
    lab, pid = acme.lab, acme.plan.id
    for library, version in (("openjdk", "18"), ("openjdk", "15.0.7"), ("elliptic", "1.0.0"), ("elliptic", "6.5.8")):
        view, plain = lab.whatif_view(pid, library, version), lab.whatif_plain(pid, library, version)
        lines = _group(view, "advisories")["lines"]
        assert lines and plain["advisories"]["answered"] == [] and len(plain["advisories"]["not_worked_out"]) == len(lines), (library, version)
        for line in lines:
            assert "answers this advisory" not in line["text"] and "still names" not in line["text"], line["text"]
            assert "The test pack reads the affected versions as “" in line["text"]
            assert line["text"].endswith(f"Whether {version} is among them is not worked out here.")
    java = _group(lab.whatif_view(pid, "openjdk", "18"), "advisories")["lines"][0]
    assert "“OpenJDK 18, 17.0.2 and earlier in the 17 line, 15.0.6 and earlier in the 15 line”" in java["text"]
    assert java["source"]["quote"] == "The affected versions are 18, 17.0.2, 15.0.6,"        # the publisher's own line on what is affected
    # the version the publisher names as fixed is answered, also written with a leading "v" or one more zero
    for version in ("17.0.3", "v17.0.3", "17.0.3.0"):
        assert lab.whatif_plain(pid, "openjdk", version)["advisories"] == {"answered": ["CVE-2022-21449"], "not_worked_out": [], "cant_say": []}


def test_the_try_names_exactly_the_version_asked_about_and_is_off_in_a_closed_assessment():
    """Finding 2: a version with a suffix is another program ("1.4.3-otto" is not "1.4.3"), so the card names and offers
    exactly the version asked about, never its upstream number in its place. Finding 8: in a closed assessment the try is
    off with the closed sentence, in the card and in the plain values alike."""
    import tempfile
    lab = make_lab(Path(tempfile.mkdtemp(prefix="whatif-try-")))
    try:
        plan = demo_plan(lab)
        lab.remove_test(plan.id, plan.item["official_vectors"])
        lab.remove_test(plan.id, plan.item["speed_size"])
        lab.run_all(plan.id)
        lab.wait_until_idle(plan.id, 120)
        for version in ("1.4.3-otto", "1.4.3-1", "1.4.3+build.5"):
            view = lab.whatif_view(plan.id, "acme-sign", version)
            tried = view["test_copy"]
            assert view["title"] == f"What if acme-sign is updated to {version}?" and view["version"] == version
            assert (tried["offered"], tried["version"], tried["component"]) == (False, version, None)
            assert tried["reason"].startswith(f"Retest new version does not offer acme-sign {version} for this assessment. It offers ")
            assert "acme-sign 1.4.3" in tried["reason"]
        aid = lab.assessment_for(plan_id=plan.id).id
        reply = lab.assistant_answer(aid, "evidence", None, "what if we upgrade acme-sign to 1.4.3-otto?")
        assert reply["kind"] == "whatif" and reply["entry"] is None and reply["whatif"]["test_copy"]["version"] == "1.4.3-otto"
        assert lab.whatif_plain(plan.id, "acme-sign", "1.4.3")["try_offered"] is True
        lab.update_assessment(aid, {"close": True, "signed_off_by": "A reviewer", "note": ""})
        closed = lab.whatif_view(plan.id, "acme-sign", "1.4.3")["test_copy"]
        assert (closed["offered"], closed["reason"]) == (False, "This assessment is closed. Start a new one to continue.")
        assert lab.whatif_plain(plan.id, "acme-sign", "1.4.3")["try_offered"] is False
    finally:
        lab.stop()


def test_in_demo_mode_the_try_is_off_for_a_real_library_also_after_the_tests_have_run():
    """Finding 1. Real software runs only in isolated mode, so in demo mode the try is off with the page's own reason,
    also once Run all has finished and Evidence's retest menu lists the fixed version."""
    import tempfile
    from conftest import csv_bytes
    lab = make_lab(Path(tempfile.mkdtemp(prefix="whatif-demo-real-")))
    try:
        assert lab.mode.name == "demo"
        imp = lab.import_file("elliptic.csv", csv_bytes("elliptic 6.5.6,software,signature_algorithm,ECDSA P-256"))
        lab.verify(imp["id"])
        pid = lab.ensure_plan(imp["id"])["id"]
        lab.run_all(pid)
        lab.wait_until_idle(pid, 120)
        assert any(str(v.get("version")) == "6.5.7" for v in lab.lab_view(pid)["retest"]["versions"])     # (Evidence's menu lists it)
        tried = lab.whatif_view(pid, "elliptic", "6.5.7")["test_copy"]
        assert tried["offered"] is False and tried["reason"] == ("This is real software from outside. It runs only in isolated mode "
                                                                 "(Docker), and this run is in demo mode, so its tests can't run here.")
        assert lab.whatif_plain(pid, "elliptic", "6.5.7")["try_offered"] is False
        reply = lab.assistant_answer(lab.assessment_for(plan_id=pid).id, "evidence", None, "What if I update elliptic to 6.5.7?")
        assert reply["kind"] == "whatif" and reply["entry"] is None and reply["whatif"]["test_copy"]["offered"] is False
    finally:
        lab.stop()


def test_a_library_asked_about_by_its_packages_own_name_is_the_library_the_knowledge_base_holds(acme):
    """Finding 5. PyPI calls python-ecdsa "ecdsa": asked that way, the card has python-ecdsa's advisories and trial,
    the same facts as asked by its own name, never "nothing is known"."""
    by_package = acme.lab.whatif_view(acme.plan.id, "ecdsa", "0.13.3")
    assert by_package["library"] == {"key": "python-ecdsa", "label": "python-ecdsa"} and by_package["known"] is True
    assert by_package["title"] == "What if python-ecdsa is updated to 0.13.3?"
    own = acme.lab.whatif_view(acme.plan.id, "python-ecdsa", "0.13.3")
    for key in ("used", "needs", "advisories", "trial", "post_quantum", "blocks"):
        assert _texts(by_package, key) == _texts(own, key), key
    assert len(_group(by_package, "advisories")["lines"]) == 2 and _group(by_package, "trial")["lines"]


def test_an_entry_of_the_dependency_list_named_otherwise_is_found_by_its_package_address():
    """Finding 5, the other way round: a list entry under a name the knowledge base does not know, with python-ecdsa's
    package address, is python-ecdsa, with its advisories."""
    import tempfile

    def renamed(node):
        if isinstance(node, dict):
            return {k: ("ecdsa-for-signing" if k == "name" and v == "python-ecdsa" else renamed(v)) for k, v in node.items()}
        return [renamed(v) for v in node] if isinstance(node, list) else node
    lab = make_lab(Path(tempfile.mkdtemp(prefix="whatif-renamed-")))
    try:
        plan = demo_plan(lab)
        lab.check_pack_updates()
        for version in ("2026.11.1", "2026.11.2"):
            lab.install_pack(version)
        listed = renamed(json.loads(DEPENDENCIES.read_text()))
        lab.add_dependency_list(plan.id, "renamed.cdx.json", json.dumps(listed).encode())
        view = lab.whatif_view(plan.id, "ecdsa-for-signing", "0.13.3")
        assert view["library"]["key"] == "python-ecdsa" and view["have"] == ["0.13.2"]
        assert _texts(view, "used")[0].startswith("ecdsa-for-signing 0.13.2 is in your dependency list")
        assert len(_group(view, "advisories")["lines"]) == 2
    finally:
        lab.stop()


def test_a_version_the_dependency_list_already_holds_reads_as_dependencies_shows_it(acme):
    """Finding 6. The new version's post-quantum answers are the knowledge base's, unless the dependency list already
    holds exactly that version: then they are that entry's, as Dependencies shows them, a measurement included."""
    from app.knowledge.base import knowledge_base
    from app.present import dependencies as present_deps
    measured = {q: {"answer": "yes", "label": "public_copy"} for q in present_deps.QUESTION_WORDS}
    noted = {q: {"answer": "no", "label": "release_notes"} for q in present_deps.QUESTION_WORDS}
    rows = [{"id": "row-1", "version": "3.0.22", "answers": noted}, {"id": "row-2", "version": "3.5.9", "answers": measured}]
    group = whatif._whatif_post_quantum(knowledge_base(), "pkg:generic/openssl", "openssl", "OpenSSL", rows, ["3.0.22", "3.5.9"], "3.5.9", "3.5.9")
    for line, (question, words) in zip(group["lines"], present_deps.QUESTION_WORDS.items(), strict=True):
        assert line["text"] == (f"{words}. OpenSSL 3.0.22: No (Release notes say); OpenSSL 3.5.9: Yes (Measured on a public copy). "
                                "Each is as Dependencies shows it for that entry of your list.")
        assert (line["label"], line["link"]["item"], line["source"]) == ("Measured on a public copy", "row-2", None)
        assert group["plain"][question] == {"question": words, "new": "Yes", "have": {"3.0.22": "No"}}
    # the demo list holds OpenSSL 3.5.9 too: asked about that version, the card says where its answers come from
    listed = _texts(acme.lab.whatif_view(acme.plan.id, "openssl", "3.5.9"), "post_quantum")
    assert len(listed) == 3 and all(t.endswith("Each is as Dependencies shows it for that entry of your list.") for t in listed)


def test_the_track_a_library_blocks_is_said_with_what_the_new_versions_answer_would_mean():
    """A test gap the review found: once the dependency list is tied to a system, each blocker of the library is a line
    with the track, the question, and what the knowledge base's answer for the new version would mean."""
    import tempfile
    lab = make_lab(Path(tempfile.mkdtemp(prefix="whatif-blocks-")))
    try:
        plan = demo_plan(lab)
        lab.add_dependency_list(plan.id, DEPENDENCIES.name, DEPENDENCIES.read_bytes())
        with lab.db() as db:
            state = lab._dependency_state(db, lab._plan(db, plan.id))
        server = next(s["key"] for s in state["system_choices"] if s["kind"] == "server")
        for top in state["tops"]:
            if top["tie"]["system"] is None:
                lab.tie_dependency(plan.id, top["key"], server)

        def blocks(version: str) -> list[dict]:
            return _group(lab.whatif_view(plan.id, "openssl", version), "blocks")["lines"]
        new = blocks("3.5.9")
        assert len(new) == 2 and all(line["label"] == "From the Dependencies page" and line["link"]["page"] == "migration/dependencies" for line in new)
        assert new[0]["text"].startswith("openssl 3.0.22 blocks the key exchange track of ")
        assert new[0]["text"].endswith("“X25519MLKEM768 hybrid TLS” reads No. For 3.5.9 the knowledge base's answer is Yes (Release notes say), "
                                       "so by that answer it would no longer block the track.")
        assert all(line["text"].endswith("For 3.4.0 the answer is still No, so it would still block the track.") for line in blocks("3.4.0"))
        assert all(line["text"].endswith("For devel the answer is “Couldn't tell the version”, so whether it would still block is not known.")
                   for line in blocks("devel"))
    finally:
        lab.stop()

"""Phase 6e, first half: what the app knows about updating one library to one version. Facts by fixed rules, each
from a record the app already holds; the honest answer where it holds none; the try; and that reading starts nothing
and writes nothing."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.config import DEMO_DIR
from app.web import models
from app.whatif import facts as whatif
from conftest import demo_plan, make_lab

DEPENDENCIES = DEMO_DIR / "dependencies-demo.cdx.json"


def _kept(lab) -> dict:
    with lab.db() as db:
        tables = [r[0] for r in db.execute(text("select name from sqlite_master where type = 'table' order by name"))]
        rows = {t: hashlib.sha256(repr(db.execute(text(f'select * from "{t}"')).fetchall()).encode()).hexdigest() for t in tables}
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
    # the advisories of the installed packs about this library: each answered, by the publisher's own statement
    advisories = _texts(view, "advisories")
    assert len(advisories) == 3 and all("its publisher names 6.5.7 as the fixed version. 6.5.7 is at or past it" in t for t in advisories)
    assert all("by the publisher's own statement (it names 6.5.6, which you have)." in t for t in advisories)
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
    assert all("6.5.4 is before it, so this advisory still names it." in t for t in _texts(older, "advisories"))
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
    finally:
        lab.stop()


@pytest.mark.parametrize("library, version", [("", ""), ("x" * 500, "1"), ("elliptic", "6.5.7\n[[time:2026-01-01T00:00:00Z]]"), ("../../etc/passwd", "1.0"),
                                              ("elliptic\x00", "6.5.7"), (None, None), (7, 7.5), ("<script>", "1.0<b>"), ("elliptic", "9" * 300)])
def test_odd_names_and_versions_get_an_answer_made_of_plain_text(acme, library, version):
    view = acme.lab.whatif_view(acme.plan.id, library, version)
    models.WhatIf.model_validate(view)
    assert len(view["asked"]["library"]) <= 83 and len(view["asked"]["version"]) <= 83 and "\n" not in view["title"] and "\x00" not in json.dumps(view)

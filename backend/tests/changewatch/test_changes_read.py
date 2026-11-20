"""Change watch, first part: a developer's change is read from the connected repository; the tests picked for it and
why; the byte-for-byte check; the flags; and "Bring in a demo change", which runs nothing."""
import hashlib
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app import demo_repo
from app.changewatch import demo_changes, flags
from app.changewatch.state import DEMO_DEVELOPER, ChangeWatchMixin, _file, change_id
from app.db import CodeConnectionRow
from app.errors import Conflict, NotFound
from app.fixes.gitrepo import GitRepo, Person
from app.run import components
from conftest import make_lab
from test_changes import FIX, proved, small_plan

V142 = components.lookup("acme-sign", "1.4.2").read_bytes()
V143 = components.lookup("acme-sign", "1.4.3").read_bytes()
NOT_CONNECTED = "Connect the demo code first. Connect demo code is on Fixes."
SOMEONE = Person("A developer", "dev@example.invalid")


def kept(lab) -> dict:
    """Every row of every table, and every file of the data folder (the connected repositories are in it)."""
    with lab.db() as db:
        tables = [r[0] for r in db.execute(text("select name from sqlite_master where type = 'table' order by name"))]
        rows = {t: hashlib.sha256(repr(db.execute(text(f'select * from "{t}"')).fetchall()).encode()).hexdigest() for t in tables}
    files = {str(p.relative_to(lab.settings.data_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(Path(lab.settings.data_dir).rglob("*"))
             if p.is_file() and not p.name.endswith(("-wal", "-shm", "-journal")) and p.suffix != ".db"}
    return {"rows": rows, "files": files}


def repo_of(lab, plan_id: int) -> GitRepo:
    with lab.db() as db:
        folder = db.query(CodeConnectionRow).filter(CodeConnectionRow.plan_id == plan_id).one().folder
    return GitRepo(lab.settings.data_dir / folder)


def refusal(call, kind=Conflict) -> str:
    with pytest.raises(kind) as caught:
        call()
    return str(caught.value)


def one(state: dict, branch: str) -> dict:
    return next(c for c in state["changes"] if c["branch"] == branch)


@pytest.fixture(scope="module")
def watch(tmp_path_factory):
    """One assessment taken from "nothing connected" to "a fix merged", with what Change watch reads at each stage:
    before connecting; connected with the proof passed; after the first demo change came in; after the merge; after
    the second demo change came in. Tests that only read share it."""
    lab = make_lab(tmp_path_factory.mktemp("change-watch"))
    try:
        plan = small_plan(lab)                      # TLS versions, certificate, bad signatures, speed and size (timings played back)
        before = lab.change_watch_state(plan.id)
        early = refusal(lambda: lab.bring_in_demo_change(plan.id, "allow-tls-1-0"))
        proved(lab, plan)                           # Run all, Connect demo code, the proof that starts by itself
        connected = lab.change_watch_state(plan.id)
        needs_merge = refusal(lambda: lab.bring_in_demo_change(plan.id, "revert-range-check"))
        kept_before = kept(lab)
        with_tls = lab.bring_in_demo_change(plan.id, "allow-tls-1-0")
        kept_after = kept(lab)
        twice = refusal(lambda: lab.bring_in_demo_change(plan.id, "allow-tls-1-0"))
        lab.open_pull_request(plan.id, FIX, ["you"])
        lab.approve(plan.id, FIX, "you")
        lab.merge(plan.id, FIX)
        merged = lab.change_watch_state(plan.id)
        with_revert = lab.bring_in_demo_change(plan.id, "revert-range-check")
        yield SimpleNamespace(lab=lab, plan=plan, before=before, early=early, connected=connected, needs_merge=needs_merge,
                              kept_before=kept_before, with_tls=with_tls, kept_after=kept_after, twice=twice, merged=merged,
                              with_revert=with_revert)
    finally:
        lab.stop()


# ---------------------------------------------------------------- before the code is connected

def test_until_the_demo_code_is_connected_nothing_is_listed_and_nothing_can_come_in(watch):
    state = watch.before
    assert state["code"]["state"] == "not_connected" and state["changes"] == []
    assert state["code"]["program"] == {"name": "acme-sign", "version": "1.4.2", "file": "acme_sign.py"}
    assert [(m["key"], m["blocked"]) for m in state["menu"]] == [("revert-range-check", "not_connected"), ("allow-tls-1-0", "not_connected")]
    assert watch.early == NOT_CONNECTED


def test_a_file_that_names_no_program_of_ours_has_no_code_to_connect(tmp_path):
    lab = make_lab(tmp_path)
    try:
        imp = lab.import_file("real-libraries.csv", (demo_repo.DEMO_DIR / "real-libraries.csv").read_bytes())    # real libraries: none is a demo program of ours
        plan = lab.ensure_plan(imp["id"])
        state = lab.change_watch_state(plan["id"])
        assert state["code"] == {"state": "no_code", "program": None, "merged": False, "repository": None, "branch": None}
        assert state["changes"] == [] and all(m["blocked"] == "no_code" for m in state["menu"])
        assert "no code that can be connected" in refusal(lambda: lab.bring_in_demo_change(plan["id"], "allow-tls-1-0"))
    finally:
        lab.stop()


def test_a_file_that_names_another_version_than_the_demo_repository_holds_has_no_code_to_connect(tmp_path):
    """The bundled demo repository holds acme-sign 1.4.2. For a file that names 1.4.3 (a registered program too) Fixes
    refuses to connect it, so Change watch must not send the person there with "Connect the demo code first"."""
    from app.lab.hub import DEMO_CBOM
    lab = make_lab(tmp_path)
    try:
        imp = lab.import_file("acme-pay-1.4.3.json", DEMO_CBOM.read_bytes().replace(b"1.4.2", b"1.4.3"))
        plan = lab.ensure_plan(imp["id"])
        with lab.db() as db:        # (the file names a program of ours, in a version the registry has)
            row = lab._plan(db, plan["id"])
            assert (row.component_name, row.component_version) == ("acme-sign", "1.4.3") and components.lookup("acme-sign", "1.4.3") is not None
        state = lab.change_watch_state(plan["id"])
        assert state["code"] == {"state": "no_code", "program": None, "merged": False, "repository": None, "branch": None}
        assert all(m["blocked"] == "no_code" for m in state["menu"])
        page = lab.change_watch_view(plan["id"])
        assert page["code"]["line"] == "This assessment has no code that can be connected, so no developer's change can come in here."
        assert page["code"]["link"] is None and page["changes"] == [] and page["busy"] is False
        assert "no code that can be connected" in refusal(lambda: lab.bring_in_demo_change(plan["id"], "allow-tls-1-0"))
    finally:
        lab.stop()


# ---------------------------------------------------------------- connected: the app's own change is not a developer's

def test_the_fix_templates_own_branch_is_not_listed_as_a_developers_change(watch):
    state = watch.connected
    assert state["code"]["state"] == "connected" and state["code"]["repository"] == "acme-sign" and state["code"]["branch"] == "main"
    assert state["code"]["merged"] is False
    assert len(repo_of(watch.lab, watch.plan.id).branches()) >= 2          # main and the fix's branch are both there
    assert state["changes"] == []
    # the settings change is offered as soon as the code is connected; the one that undoes a fix only once a fix is merged
    assert [(m["key"], m["blocked"]) for m in state["menu"]] == [("revert-range-check", "needs_merge"), ("allow-tls-1-0", None)]
    assert "offered once a fix is merged" in watch.needs_merge


# ---------------------------------------------------------------- the settings change: nothing to run, one flag

def test_bringing_in_a_demo_change_writes_one_branch_with_one_commit_and_runs_nothing(watch):
    before, after = watch.kept_before, watch.kept_after
    assert after["rows"] == before["rows"]                                # no row of any table was written: no run, no record
    new = sorted(set(after["files"]) - set(before["files"]))
    assert all("/refs/heads/dev/" in name or "/objects/" in name for name in new) and len(new) == 4, new   # a branch, a commit, a tree, a file
    assert all(after["files"][name] == before["files"][name] for name in before["files"])     # nothing that was there changed
    assert watch.lab.jobs.live(watch.plan.id) == []
    repo = repo_of(watch.lab, watch.plan.id)
    head = repo.branch("dev/allow-tls-1-0-for-partner")
    commit = repo.read_commit(head)
    # (it was pushed before the merge: its one parent is where the connected branch stood then)
    assert commit.author == DEMO_DEVELOPER and len(commit.parents) == 1 and repo.is_ancestor(commit.parents[0], repo.branch("main"))
    assert commit.title == "Allow TLS 1.0 for an old partner" and set(repo.files(head)) == {"acme_sign.py", "partner-gateway.conf"}
    assert abs(commit.author_time - time.time()) < 3600
    assert watch.twice == "This demo change is already in the repository."


def test_a_change_that_touches_no_program_file_picks_nothing_and_says_which_rule_left_each_test_out(watch):
    change = one(watch.with_tls, "dev/allow-tls-1-0-for-partner")
    assert change["id"] == change_id(change["head"]) and change["id"].startswith("change-") and len(change["id"]) == 19
    assert change["title"] == "Allow TLS 1.0 for an old partner" and change["author"] == "Demo developer" and change["is_demo"] is True
    assert change["commits"] == 1 and change["problem"] is None and change["when"].endswith("Z")
    assert [(f["name"], f["state"], f["added"], f["removed"], f["is_program"]) for f in change["files"]] == [("partner-gateway.conf", "added", 5, 0, False)]
    assert change["touches_program"] is False and change["picked"] == [] and change["status"] == "nothing_to_run"
    # every test of the plan is listed as not picked, with the rule that left it out
    rules = {t["kind"]: t["rule"] for t in change["not_picked"]}
    assert rules == {"tls_versions": "server_test", "certificate": "server_test", "bad_signatures": "program_not_touched",
                     "speed_size": "program_not_touched"}
    assert all(t["server"] for t in change["not_picked"] if t["rule"] == "server_test")
    # the whole file is shown as added lines
    block = change["files"][0]["blocks"][0]
    assert block["before"] == [] and [line["mark"] for line in block["after"]] == ["+"] * 5
    assert block["after"][3] == {"n": 4, "mark": "+", "text": "minimum_protocol = TLS 1.0"}


def test_the_line_that_names_tls_1_0_is_flagged_with_its_source_and_the_flag_is_no_result(watch):
    change = one(watch.with_tls, "dev/allow-tls-1-0-for-partner")
    assert change["flags"] == [{"kind": "old_cryptography", "word": "TLS 1.0", "as_written": "TLS 1.0", "file": "partner-gateway.conf", "line": 4,
                                "text": "minimum_protocol = TLS 1.0",
                                "source": {"title": "RFC 8996, Deprecating TLS 1.0 and TLS 1.1", "url": "https://www.rfc-editor.org/rfc/rfc8996"}}]
    assert change["more_flags"] == 0
    assert "code" not in change["flags"][0] and "label" not in change["flags"][0]       # nothing that reads like a result


# ---------------------------------------------------------------- after the merge: the change that undoes the fix

def test_once_a_fix_is_merged_the_change_that_undoes_it_is_offered(watch):
    assert watch.merged["code"]["merged"] is True
    assert [(m["key"], m["blocked"]) for m in watch.merged["menu"]] == [("revert-range-check", None), ("allow-tls-1-0", "already_in")]
    # the settings change was made before the merge: it still starts from the connected branch, one commit back
    earlier = one(watch.merged, "dev/allow-tls-1-0-for-partner")
    assert earlier["problem"] is None and earlier["status"] == "nothing_to_run"


def test_a_change_to_the_programs_file_picks_every_test_that_runs_that_program_and_no_other(watch):
    change = one(watch.with_revert, "dev/revert-range-check")
    repo = repo_of(watch.lab, watch.plan.id)
    assert change["base"] == repo.branch("main") and repo.files(change["base"]) == {"acme_sign.py": V143}      # it starts from the merged fix
    assert repo.files(change["head"]) == {"acme_sign.py": V142}                                             # and gives 1.4.2, byte for byte
    assert change["gives"] == {"name": "acme-sign", "version": "1.4.2"} and change["status"] == "not_run"
    file = change["files"][0]
    assert (file["name"], file["state"], file["is_program"], file["text"]) == ("acme_sign.py", "changed", True, True)
    assert file["added"] > 0 and file["removed"] > 0 and file["blocks"]
    assert change["touches_program"] is True
    assert [(t["kind"], t["rule"]) for t in change["picked"]] == [("bad_signatures", "runs_the_program"), ("speed_size", "runs_the_program")]
    assert [(t["kind"], t["rule"]) for t in change["not_picked"]] == [("tls_versions", "server_test"), ("certificate", "server_test")]
    picked, not_picked = {t["item_id"] for t in change["picked"]}, {t["item_id"] for t in change["not_picked"]}
    assert not picked & not_picked and len(picked | not_picked) == 4          # every test of the plan is in exactly one list
    # the newest change comes first
    assert [c["branch"] for c in watch.with_revert["changes"]] == ["dev/revert-range-check", "dev/allow-tls-1-0-for-partner"]
    assert all(m["blocked"] == "already_in" for m in watch.with_revert["menu"])


def test_reading_change_watch_writes_nothing_and_starts_nothing(watch):
    before = kept(watch.lab)
    for _ in range(3):
        watch.lab.change_watch_state(watch.plan.id)
    assert kept(watch.lab) == before and watch.lab.jobs.live(watch.plan.id) == []


# ---------------------------------------------------------------- changes nobody bundled: whatever is in the repository is listed

def _connected(folder):
    lab = make_lab(folder)
    try:
        plan = small_plan(lab)
        proved(lab, plan)
        yield SimpleNamespace(lab=lab, plan=plan, repo=repo_of(lab, plan.id))
    finally:
        lab.stop()


@pytest.fixture(scope="module")
def connected(tmp_path_factory):
    """One assessment with its demo code connected, shared by the tests that add a branch of their own to its
    repository (each looks only at its own branch)."""
    yield from _connected(tmp_path_factory.mktemp("change-watch-branches"))


@pytest.fixture()
def connected_alone(tmp_path):
    """The same, for a test that damages the repository."""
    yield from _connected(tmp_path)


def test_a_change_whose_code_is_not_one_of_our_registered_programs_cannot_run(connected):
    lab, plan, repo = connected.lab, connected.plan, connected.repo
    main = repo.branch("main")
    edited = V142 + b"\n# one more line: no longer byte for byte one of our programs\n"
    repo.branch_from("dev/tweak", main, {"acme_sign.py": edited}, "Tweak the signer", SOMEONE, int(time.time()))
    change = one(lab.change_watch_state(plan.id), "dev/tweak")
    assert change["touches_program"] is True and [t["kind"] for t in change["picked"]] == ["bad_signatures", "speed_size"]
    assert change["gives"] is None and change["status"] == "cant_run"
    assert change["author"] == "A developer" and change["is_demo"] is False
    # a registered program under another file name is not that program either, and a second file beside it is not it
    repo.branch_from("dev/renamed", main, {"signer.py": V142}, "Rename the signer", SOMEONE, int(time.time()))
    renamed = one(lab.change_watch_state(plan.id), "dev/renamed")
    assert renamed["gives"] is None and renamed["status"] == "cant_run" and renamed["touches_program"] is True     # (the program's file was removed)
    assert {f["name"]: f["state"] for f in renamed["files"]} == {"acme_sign.py": "removed", "signer.py": "added"}


def test_a_branch_with_several_commits_is_one_change_from_where_it_left_the_connected_branch(connected):
    lab, plan, repo = connected.lab, connected.plan, connected.repo
    main = repo.branch("main")
    first = repo.branch_from("dev/two-steps", main, {"acme_sign.py": V142, "notes.txt": b"use MD5 for the cache key\n"}, "Add notes", SOMEONE, 1794400000)
    repo.commit("dev/two-steps", {"acme_sign.py": V142, "notes.txt": b"use SHA-256 for the cache key\n"}, "Fix the notes", SOMEONE, 1794400100, first)
    change = one(lab.change_watch_state(plan.id), "dev/two-steps")
    assert change["commits"] == 2 and change["base"] == main and change["title"] == "Fix the notes"
    assert [(f["name"], f["state"], f["added"]) for f in change["files"]] == [("notes.txt", "added", 1)]
    assert change["flags"] == []                         # the line that named MD5 is not in what the change leaves
    assert change["status"] == "nothing_to_run" and change["touches_program"] is False


def test_a_branch_that_does_not_start_from_the_connected_branch_is_listed_with_why_and_cannot_run(connected):
    lab, plan, repo = connected.lab, connected.plan, connected.repo
    repo.commit("dev/elsewhere", {"acme_sign.py": V142}, "A history of its own", SOMEONE, 1794400000, None)
    change = one(lab.change_watch_state(plan.id), "dev/elsewhere")
    assert change["problem"] == "no_start" and change["status"] == "cant_run" and change["picked"] == [] and change["files"] == []
    # a branch that points at the connected branch itself, or behind it, holds nothing new and is not a change
    repo.set_branch("dev/nothing-new", repo.branch("main"), None)
    listed = [c["branch"] for c in lab.change_watch_state(plan.id)["changes"]]
    assert "dev/elsewhere" in listed and "dev/nothing-new" not in listed


def test_a_damaged_repository_is_said_plainly_and_never_stops_the_page(connected_alone):
    lab, plan, repo = connected_alone.lab, connected_alone.plan, connected_alone.repo
    main = repo.branch("main")
    head = repo.branch_from("dev/broken", main, {"acme_sign.py": V142, "x.txt": b"x\n"}, "Will be damaged", SOMEONE, 1794400000)
    (repo.path / "objects" / head[:2] / head[2:]).write_bytes(b"not a git object")
    state = lab.change_watch_state(plan.id)
    assert one(state, "dev/broken")["problem"] == "unreadable" and one(state, "dev/broken")["status"] == "cant_run"
    # the connected branch itself gone: nothing is listed, and the view says the repository could not be read
    (repo.path / "refs" / "heads" / "main").unlink()
    gone = lab.change_watch_state(plan.id)
    assert gone["code"]["state"] == "unreadable" and gone["changes"] == []
    assert "could not be written" in refusal(lambda: lab.bring_in_demo_change(plan.id, "allow-tls-1-0"))


def test_an_unknown_demo_change_does_not_exist(watch):
    for key in ("nope", "../revert-range-check", "", None, 7, "revert-range-check.json"):
        assert refusal(lambda key=key: watch.lab.bring_in_demo_change(watch.plan.id, key), NotFound) == "That demo change does not exist."


# ---------------------------------------------------------------- the rules by themselves

def _test(item_id, kind, program=None, server=None):
    return {"item_id": item_id, "kind": kind, "title": kind, "program": program, "server": server}


def test_the_picking_rules():
    own = {"component": "acme-sign", "version": "1.4.2", "ref": "c1", "label": "acme-sign 1.4.2", "own": True}
    other = {"component": "other-sign", "version": "2.0", "ref": "c2", "label": "other-sign 2.0", "own": False}
    tests = [_test(1, "tls_versions", server="localhost:8443"), _test(2, "bad_signatures", own), _test(3, "bad_signatures", other),
             _test(4, "mldsa_compare"), _test(5, "advisory_check", own)]
    program = {"name": "acme-sign", "version": "1.4.2", "file": "acme_sign.py"}
    picked, not_picked = ChangeWatchMixin._pick(tests, program, True)
    assert [(t["item_id"], t["rule"]) for t in picked] == [(2, "runs_the_program"), (5, "runs_the_program")]
    assert [(t["item_id"], t["rule"]) for t in not_picked] == [(1, "server_test"), (3, "other_program"), (4, "no_program")]
    assert not_picked[1]["other"] == "other-sign 2.0" and not_picked[0]["server"] == "localhost:8443"
    picked, not_picked = ChangeWatchMixin._pick(tests, program, False)
    assert picked == [] and [(t["item_id"], t["rule"]) for t in not_picked] == [
        (1, "server_test"), (2, "program_not_touched"), (3, "other_program"), (4, "no_program"), (5, "program_not_touched")]


def test_a_flag_comes_only_from_a_line_the_change_adds():
    old = b"digest = MD5\nprotocol = TLS 1.2\nkeep = yes\n"
    new = b"digest = SHA-256\nprotocol = TLS 1.2\nkeep = yes\ncipher = RC4-SHA\n"
    file = _file("app.conf", old, new, "acme_sign.py")
    assert (file["state"], file["added"], file["removed"]) == ("changed", 2, 1)
    assert [n for n, _ in file["added_lines"]] == [1, 4]
    found = flags.named_in("app.conf", file["added_lines"])
    assert [(f["word"], f["line"]) for f in found] == [("RC4", 4)]                # the removed MD5 line gives none; SHA-256 and TLS 1.2 are not on the list
    # removing a line that names old cryptography gives no flag at all
    gone = _file("app.conf", b"a\ncipher = 3DES\n", b"a\n", "acme_sign.py")
    assert gone["added_lines"] == [] and flags.named_in("app.conf", gone["added_lines"]) == []
    # a file that is not text, or very large, is listed without lines and gives no flag
    binary = _file("blob.bin", None, b"\xff\xfe\x00TLS 1.0", "acme_sign.py")
    assert (binary["state"], binary["text"], binary["added"], binary["blocks"], binary["added_lines"]) == ("added", False, None, [], [])


@pytest.mark.parametrize("line,words", [
    ("minimum_protocol = TLS 1.0", ["TLS 1.0"]), ("ssl_protocols TLSv1 TLSv1.1 TLSv1.2;", ["TLS 1.0", "TLS 1.1"]), ("TLSv1.2 only", []), ("TLS 1.3", []),
    ("openssl s_client -tls1", ["TLS 1.0"]), ("tls1_2", []), ("TLS 1.0.2", []), ("TLS 1.10", []), ("TLS 1.0, then TLS 1.2", ["TLS 1.0"]),
    ("digest = sha1", ["SHA-1"]), ("SHA-256", []), ("sha1WithRSAEncryption", ["SHA-1"]), ("sha128", []), ("SHA-1.", ["SHA-1"]),
    ("hashlib.md5(x)", ["MD5"]), ("cmd5", []), ("RC4-SHA", ["RC4"]), ("src4", []), ("arcfour128", ["RC4"]),
    ("DES-EDE3-CBC", ["3DES"]), ("ciphers = 3DES", ["3DES"]), ("Triple DES", ["3DES"]), ("description", []), ("nodes", []),
    ("SSLv3", ["SSL 3.0"]), ("ssl3", ["SSL 3.0"]), ("SSL 3.0 is off", ["SSL 3.0"]), ("ssl30x", []),
    # a newer version written with dashes or underscores, or a date after the name, is not the old one (the review of 6d)
    ('ssl_policy = "ELBSecurityPolicy-TLS-1-2-2017-01"', []), ("min-tls-1-3-only = true", []), ("TLS_1_2", []), ("tls-1-2", []), ("TLSv1.1.1", []),
    ('ssl_policy = "ELBSecurityPolicy-TLS-1-0-2015-04"', ["TLS 1.0"]), ("tls-1-0", ["TLS 1.0"]), ("TLS-1-1", ["TLS 1.1"]), ("tls1_1", ["TLS 1.1"]),
    ("openssl 3.0", []), ("openssl-3.0.2", []), ("libssl3", []), ("ssl_3_0", ["SSL 3.0"]),
    # words that only look like a name on the list
    ("retry on up to 3 destinations", []), ("keep 3 desks free", []), ("tdeadline = 30", []), ("triple description", []),
    ("git sha 1a2b3c", []), ("arc4random()", []), ("the triple-des cipher", ["3DES"]), ("sha 1", ["SHA-1"]), ("hmac-md5", ["MD5"]), ("rc 4", ["RC4"]),
])
def test_how_the_names_on_the_list_are_found(line, words):
    assert [f["word"] for f in flags.named_in("f", [(1, line)])] == words


def test_every_name_on_the_list_has_a_source_the_app_may_link_to():
    from app.engine.guidance import OLD_CRYPTOGRAPHY, OWN_LINKS
    assert [w["word"] for w in OLD_CRYPTOGRAPHY] == ["SSL 3.0", "TLS 1.0", "TLS 1.1", "SHA-1", "MD5", "RC4", "3DES"]
    for word in OLD_CRYPTOGRAPHY:
        assert word["source"]["title"] and word["source"]["url"].startswith("https://") and word["source"]["url"] in OWN_LINKS
    flags.read_words(OLD_CRYPTOGRAPHY)      # the built-in list has the form its reader holds a list to


# ---------------------------------------------------------------- the bundled demo changes are data

def test_the_two_bundled_demo_changes_read_and_neither_adds_a_program():
    changes = demo_changes.bundled()
    assert [c.key for c in changes] == list(demo_changes.ORDER) == ["revert-range-check", "allow-tls-1-0"]
    revert, tls = changes
    assert demo_changes.content(revert) == {"acme_sign.py": V142}                    # byte for byte our registered 1.4.2
    assert revert.files[0].text is None and revert.files[0].registered == ("acme-sign", "1.4.2") and revert.offered == "after_merge"
    assert list(demo_changes.content(tls)) == ["partner-gateway.conf"] and tls.offered == "connected"
    # no change file holds program text: a program comes only by the name of a registered one
    for path in sorted(demo_changes.CHANGES_DIR.iterdir()):
        assert path.suffix == ".json" and path.stem in demo_changes.ORDER, path
        assert b"def " not in path.read_bytes() and b"import " not in path.read_bytes()
    for change in changes:
        for file in change.files:
            assert file.registered is not None or not file.name.endswith(".py")
    assert demo_changes.find("revert-range-check") == revert and demo_changes.find("no-such") is None and demo_changes.find(None) is None

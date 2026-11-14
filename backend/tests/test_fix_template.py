"""The one fix template (the missing range check in acme-sign): it applies only to the exact lines it expects."""
import pytest

from app import components, gitrepo, present, vectors
from app.research import CHANGE_LABEL, RANGE_CHECK, RuleEngine, out_of_range_cause

OLD = components.lookup("acme-sign", "1.4.2").read_text()
NEW = components.lookup("acme-sign", "1.4.3").read_bytes()


def wrong(case_id, comment="", expected="invalid"):
    return {"id": case_id, "comment": comment, "flags": [], "expected": expected, "got": "accept"}


BAD = {"kind": "bad_signatures", "reason_code": None, "detail": {"wrong": [wrong("r0-s0", "r = 0, s = 0"), wrong("s-plus-n", "s + n")]}}
OFFICIAL = {"kind": "official_vectors", "reason_code": None,
            "detail": {"wrong": [wrong("168", "r=0 and s=0"), wrong("171", "r=0 and s=n"), wrong("364", "s larger than n")]}}


def propose(text=OLD, failed=(OFFICIAL, BAD), name="acme-sign", file_name="acme_sign.py"):
    return RuleEngine().propose_change({"component": {"name": name, "version": "1.4.2"}, "failed": list(failed), "files": {file_name: text}})


def test_the_template_turns_the_bundled_1_4_2_into_exactly_the_registered_1_4_3():
    change = propose()
    assert change["files"]["acme_sign.py"].encode() == NEW  # byte for byte, so the proof can run our registered 1.4.3
    assert (change["template_id"], change["branch"]) == ("ecdsa-range-check", "fix/ecdsa-range-check")
    assert change["title"] == "Reject signatures whose r or s is out of range"
    assert change["label"] == CHANGE_LABEL == "From a fix template"
    assert change["answers"] == [0, 1]
    assert gitrepo.count_changes(OLD, change["files"]["acme_sign.py"]) == (3, 1)  # only what the fix needs


def test_each_edit_says_what_the_screen_shows_and_where_it_landed():
    check, version = propose()["edits"]  # in the order the screen shows them: the check first
    assert check["title"] == "The check: reject a signature whose numbers are out of range"
    assert check["why"].startswith("acme_sign.py, in the verify command.")
    assert (check["context_before"], check["context_after"]) == (4, 1)
    assert version["title"] == "The version number" and (version["context_before"], version["context_after"]) == (1, 1)
    assert check["file"] == version["file"] == "acme_sign.py"
    # where each edit landed is exactly where a diff of the two texts finds a change
    spots = gitrepo.changed_spots(OLD, NEW.decode())
    landed = sorted((e["old_start"], e["old_end"], e["new_start"], e["new_end"]) for e in (check, version))
    assert landed == [(s.old_start, s.old_end, s.new_start, s.new_end) for s in spots]
    new_lines = NEW.decode().split("\n")
    assert new_lines[check["new_start"]:check["new_end"]] == ["    if not (1 <= r < N and 1 <= s < N):", '        return {"valid": False}']
    assert new_lines[version["new_start"]:version["new_end"]] == ['VERSION = "1.4.3"']
    assert OLD.split("\n")[version["old_start"]:version["old_end"]] == ['VERSION = "1.4.2"']


def test_it_answers_only_the_failures_that_are_about_the_range():
    other = {"kind": "bad_signatures", "reason_code": None, "detail": {"wrong": [wrong("r0-s0"), wrong("changed-message")]}}
    server = {"kind": "tls_versions", "reason_code": None, "detail": {"accepted_outside_claim": ["TLS 1.2"]}}
    assert propose(failed=[server, other, BAD])["answers"] == [2]
    for failed in ([], [server], [other], [{"kind": "bad_signatures", "reason_code": None, "detail": {"wrong": []}}],
                   [{"kind": "official_vectors", "reason_code": None, "detail": {"wrong": [wrong("1", "signature malleability")]}}],
                   [{"kind": "official_vectors", "reason_code": None, "detail": {"wrong": [wrong("168", "r=0 and s=0", expected="valid")]}}],
                   [{"kind": "bad_signatures", "reason_code": "component_no_answer", "detail": {}}], ["not a result"]):
        assert propose(failed=failed) is None, failed


@pytest.mark.parametrize("text", [
    OLD.replace('VERSION = "1.4.2"', 'VERSION = "1.4.1"'),                                  # the version line is not there
    OLD.replace('VERSION = "1.4.2"\n', 'VERSION = "1.4.2"\nVERSION = "1.4.2"\n'),           # ... or is there twice
    OLD.replace("    except ValueError:\n        return {\"valid\": False}\n", "    except ValueError:\n        return {\"valid\": 0}\n"),
    OLD.replace("        r, s = der_decode(", "        r,s = der_decode("),                 # one anchor line differs by a space
    OLD + OLD[OLD.index("def cmd_verify(req):"):OLD.index("def cmd_bench(req):")],          # the four lines appear twice
    OLD.replace("\n", "\r\n"),                                                              # other line ends: not the exact lines
    NEW.decode(),                                                                           # already changed
    "",
], ids=["no-version", "version-twice", "changed-anchor", "space", "check-twice", "crlf", "already-fixed", "empty"])
def test_a_missing_or_repeated_anchor_gives_no_change(text):
    assert text != OLD and propose(text=text) is None


def test_no_change_for_another_component_or_another_file():
    assert propose(name="other-sign") is None and propose(name=None) is None
    assert propose(file_name="other.py") is None
    assert RuleEngine().propose_change({}) is None
    assert RuleEngine().propose_change({"component": {"name": "acme-sign"}, "failed": [BAD], "files": {"acme_sign.py": OLD.encode()}}) is None


def test_other_files_are_passed_through_untouched_and_nothing_is_run():
    reply = RuleEngine().propose_change({"component": {"name": "acme-sign", "version": "1.4.2"}, "failed": [BAD],
                                         "files": {"acme_sign.py": OLD, "notes.txt": "raise SystemExit\n"}})
    assert reply["files"]["notes.txt"] == "raise SystemExit\n" and set(reply["files"]) == {"acme_sign.py", "notes.txt"}
    assert all(e["file"] == "acme_sign.py" for e in reply["edits"])


def test_the_template_and_the_wording_agree_on_what_one_cause_means():
    """present.py says "One cause: ..." by the same test the template uses to decide what it answers."""
    cases = {c.id: c for c in vectors.load_wycheproof("ecdsa_p256").cases}
    demo = [wrong(i, cases[i].comment) for i in ("168", "171", "364")]  # what acme-sign 1.4.2 really gets wrong
    lists = [demo, demo[:1], [wrong("1", cases["1"].comment)], demo + [wrong("1", cases["1"].comment)], []]
    lists += [[wrong(c.id, c.comment)] for c in list(cases.values())[:60] if c.expected == "invalid"]
    for wrong_cases in lists:
        assert out_of_range_cause("official_vectors", {"wrong": wrong_cases}) == present._range_cause_official(wrong_cases)
    assert out_of_range_cause("official_vectors", {"wrong": demo}) is True
    bad_ids = [c.id for c in vectors.load_bad_signatures().cases]
    for ids in ([i] for i in bad_ids + ["r0-s0"]):
        said = bool(set(ids)) and set(ids) <= present.RANGE_IDS
        assert out_of_range_cause("bad_signatures", {"wrong": [wrong(i) for i in ids]}) == said
    assert out_of_range_cause("bad_signatures", {"wrong": [wrong("r0-s0"), wrong("s-plus-n")]}) is True
    assert out_of_range_cause("speed_size", {"wrong": [wrong("r0-s0")]}) is False


def test_only_this_template_knows_the_versions_and_the_range_check():
    assert RANGE_CHECK["id"] == "ecdsa-range-check" and RANGE_CHECK["component"] == "acme-sign"
    assert [len(e["find"]) for e in RANGE_CHECK["edits"]] == [4, 1]
    for edit in RANGE_CHECK["edits"]:
        assert OLD.count("\n".join(edit["find"]) + "\n") == 1  # each anchor stands in the bundled code exactly once

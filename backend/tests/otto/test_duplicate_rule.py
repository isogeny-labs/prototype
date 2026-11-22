"""Phase 5c: the same check is never shipped under two names, and no advisory loses a check it should have.

A design that selects exactly the published cases of another advisory's check, for the SAME library, is refused
before it is tried: a trial on public copies could not tell the two weaknesses apart. Only a check that exists
counts (a test of an earlier pack, or a design of this build whose own trial held), and the same cases for another
library are another check. The pack builder looks once more before it signs.

The rule is exercised here on stand-ins for a lab's state, so it needs neither the Otto harness nor Docker. The
shipped packs show it at work on real data (tests/otto/test_shipped.py)."""

import json
from types import SimpleNamespace

import pytest

from ottolab import build, research

FILE, SHA = "ecdsa_secp256r1_sha256_test.json", "1" * 64
NINE = ["8", "9", "48", "67", "68", "84", "114", "115", "128"]


def _advisory(aid: str, name: str = "python-ecdsa", ecosystem: str = "PyPI") -> dict:
    return {"id": aid, "package": {"name": name, "ecosystem": ecosystem}}


def _design(aid: str, ids=NINE) -> dict:
    return {"advisory": aid, "cases": {"file": FILE, "sha256": SHA, "ids": list(ids)}}


def _design_claim(aid: str, ids=NINE, outcome: str = "used", decision: str = "test") -> dict:
    parsed = (
        {"decision": decision, "design": _design(aid, ids)}
        if decision == "test"
        else {"decision": decision, "reason": "nothing fits"}
    )
    return {"artifact": {"advisory": aid, "step": {"step": "design_test"}, "outcome": outcome, "parsed": parsed}}


class _State:
    """What the rule reads of a lab's state: its claims."""

    def __init__(self, claims: list[dict]):
        self._claims = claims

    def of(self, kind: str):
        return [(f"sha256:{n:064x}", c) for n, c in enumerate(self._claims)] if kind == "claim" else []


@pytest.fixture
def lab_of(monkeypatch):
    """Returns a function: given which advisories' test trials held, the rule's view of a lab."""

    def make(claims: list[dict], held: set[str]):
        monkeypatch.setattr(research, "trials_of", lambda st, aid, kind, lab: [(f"trial-of-{aid}", {})])
        monkeypatch.setattr(research, "held", lambda st, lab, hid: hid.removeprefix("trial-of-") in held)
        return _State(claims), SimpleNamespace()

    return make


SNAP = {
    "advisories": [_advisory("CVE-A"), _advisory("CVE-B"), _advisory("CVE-C", "elliptic", "npm"), _advisory("CVE-D")]
}


def _same(st, lab, aid: str, ids=NINE, snap=SNAP):
    return research.same_check_as(st, lab, snap, research.snapshot.advisory_of(snap, aid), _design(aid, ids))


def test_a_design_that_repeats_a_check_of_the_same_library_is_refused(lab_of, monkeypatch):
    monkeypatch.delenv(research.ENV_EARLIER, raising=False)
    st, lab = lab_of([_design_claim("CVE-A")], held={"CVE-A"})
    assert _same(st, lab, "CVE-B") == ("CVE-A", "this build")
    assert _same(st, lab, "CVE-B", list(reversed(NINE))) == ("CVE-A", "this build")  # the same cases in another order
    assert _same(st, lab, "CVE-A") is None  # never against itself


def test_only_a_check_that_exists_counts(lab_of, monkeypatch):
    """A design that was refused, that said "no test fits", or whose own trial did not hold is no check. It must not
    cost another advisory the test it could have."""
    monkeypatch.delenv(research.ENV_EARLIER, raising=False)
    st, lab = lab_of([_design_claim("CVE-A")], held=set())  # tried, and it did not hold
    assert _same(st, lab, "CVE-B") is None
    st, lab = lab_of([_design_claim("CVE-A", outcome="refused")], held={"CVE-A"})
    assert _same(st, lab, "CVE-B") is None
    st, lab = lab_of([_design_claim("CVE-A", decision="no_test")], held={"CVE-A"})
    assert _same(st, lab, "CVE-B") is None


def test_the_same_cases_for_another_library_are_another_check(lab_of, monkeypatch):
    """The same weakness in two libraries is two advisories, each tried on its own library's versions and each with
    its own publisher's fix. Neither is refused."""
    monkeypatch.delenv(research.ENV_EARLIER, raising=False)
    st, lab = lab_of([_design_claim("CVE-A")], held={"CVE-A"})
    assert _same(st, lab, "CVE-C") is None
    st, lab = lab_of([_design_claim("CVE-C")], held={"CVE-C"})
    assert _same(st, lab, "CVE-B") is None


def test_more_or_fewer_cases_are_not_the_same_check(lab_of, monkeypatch):
    monkeypatch.delenv(research.ENV_EARLIER, raising=False)
    st, lab = lab_of([_design_claim("CVE-A")], held={"CVE-A"})
    assert _same(st, lab, "CVE-B", NINE + ["6"]) is None and _same(st, lab, "CVE-B", NINE[:-1]) is None


def test_a_check_of_an_earlier_pack_counts_also_when_it_came_out_of_another_lab(lab_of, monkeypatch, tmp_path):
    """The research command for the next pack works in a lab of its own, which knows nothing of the shipped packs.
    The build command tells it their checks."""
    earlier = tmp_path / "earlier.json"
    earlier.write_text(
        json.dumps(
            [
                {
                    "advisory": "CVE-OLD",
                    "package": "PyPI/python-ecdsa",
                    "pack": "2026.11.1",
                    "file": FILE,
                    "sha256": SHA,
                    "ids": sorted(NINE),
                },
                {
                    "advisory": "CVE-OTHER",
                    "package": "npm/elliptic",
                    "pack": "2026.11.2",
                    "file": FILE,
                    "sha256": SHA,
                    "ids": ["6"],
                },
            ]
        )
    )
    monkeypatch.setenv(research.ENV_EARLIER, str(earlier))
    st, lab = lab_of([], held=set())
    assert _same(st, lab, "CVE-B") == ("CVE-OLD", "test pack 2026.11.1")
    assert _same(st, lab, "CVE-C") is None  # another library
    assert _same(st, lab, "CVE-C", ["6"]) == ("CVE-OTHER", "test pack 2026.11.2")
    assert _same(st, lab, "CVE-B", ["6"]) is None
    # an advisory of an earlier build in the same lab is not in today's snapshot: its check counts only if it shipped
    st, lab = lab_of([_design_claim("CVE-GONE")], held={"CVE-GONE"})
    monkeypatch.delenv(research.ENV_EARLIER)
    assert _same(st, lab, "CVE-B") is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{not json",
        "{}",
        "[1, 2]",
        '[{"advisory": "x"}]',
        json.dumps([{"advisory": 1, "package": "p", "pack": "v", "file": "f", "sha256": "s", "ids": []}]),
        json.dumps([{"advisory": "a", "package": "p", "pack": "v", "file": "f", "sha256": "s", "ids": [1]}]),
    ],
)
def test_a_list_of_earlier_checks_that_is_not_what_it_must_be_holds_none(monkeypatch, tmp_path, text):
    path = tmp_path / "earlier.json"
    path.write_text(text)
    monkeypatch.setenv(research.ENV_EARLIER, str(path))
    assert research.earlier_checks() == []
    monkeypatch.setenv(research.ENV_EARLIER, str(tmp_path / "missing.json"))
    assert research.earlier_checks() == []


def test_the_builder_looks_once_more_before_it_signs():
    def check(aid, package="PyPI/python-ecdsa", pack="2026.11.1", ids=NINE):
        return {"advisory": aid, "package": package, "pack": pack, "file": FILE, "sha256": SHA, "ids": sorted(ids)}

    assert build.same_check_twice([check("CVE-A"), check("CVE-C", "npm/elliptic"), check("CVE-B", ids=["6"])]) is None
    said = build.same_check_twice([check("CVE-A"), check("CVE-B", pack="2026.11.2")])
    assert (
        said and "CVE-B" in said and "CVE-A" in said and "test pack 2026.11.1" in said and "no pack was signed" in said
    )
    assert build.same_check_twice([]) is None


def test_the_checks_of_a_pack_are_read_off_its_ready_tests():
    pack = {
        "version": "2026.11.1",
        "advisories": [
            {"id": "CVE-A", "package": {"name": "python-ecdsa", "ecosystem": "PyPI"}},
            {"id": "CVE-B", "package": {"name": "python-ecdsa", "ecosystem": "PyPI"}},
        ],  # CVE-B has no test
        "tests": [{"design": _design("CVE-A", list(reversed(NINE)))}],
    }
    assert build.checks_of(pack) == [
        {
            "advisory": "CVE-A",
            "package": "PyPI/python-ecdsa",
            "pack": "2026.11.1",
            "file": FILE,
            "sha256": SHA,
            "ids": sorted(NINE),
        }
    ]


def test_the_spending_of_a_research_run_is_carried_whole_from_step_to_step(monkeypatch, tmp_path):
    """Each step of the research command is its own process. What counts against the run's limit, the cost of
    requests that got no answer included, is handed on through a small file."""
    from app.otto import model

    spent = tmp_path / "spent.json"
    for name, value in (
        (research.ENV_SPENT, str(spent)),
        (research.ENV_LIMIT, str(2 * model.NANO)),
        (research.ENV_RECORDED, str(tmp_path)),
        (research.ENV_LIVE, "0"),
    ):
        monkeypatch.setenv(name, value)
    first = research.env_model()
    assert (first.budget.spent_nano, first.budget.calls, first.budget.unanswered_nano) == (0, 0, 0)
    first.budget.add(300_000_000)
    first.budget.add_unanswered(1_400_000_000)
    research.save_spent(first)
    second = research.env_model()
    assert (second.budget.spent_nano, second.budget.calls, second.budget.unanswered_nano) == (
        300_000_000,
        1,
        1_400_000_000,
    )
    with pytest.raises(
        model.SpendingLimitReached
    ):  # $0.30 spent and $1.40 perhaps billed: the next one (up to $0.41) could pass $2
        second.budget.check(model.DEFAULT_MODEL, "x" * 1000)
    assert "may have been billed for requests that got no answer" in build._spent_line(spent, 2 * model.NANO)
    spent.write_text("[1]")  # a file that is not what it must be counts as nothing spent
    assert research._spent(str(spent)) == (0, 0, 0)


def test_the_research_audit_refuses_a_ledger_that_names_something_else_to_run(monkeypatch):
    """`ottolab.build audit` asks Otto's harness to run the pinned checker again, so it first makes sure the ledger
    names nothing else, in an objective or in an entry that only poses as one."""
    ours = research.file_sha256(research.PINNED / research.CHECKER)
    monkeypatch.setattr(
        build.harness,
        "module",
        lambda name: SimpleNamespace(
            digest=lambda record: "sha256:" + str(abs(hash(json.dumps(record, sort_keys=True))))
        ),
    )

    def entry(record):
        return {"kind": record["type"], "payload": record}

    verifier = {
        "kind": "certificate",
        "checker": research.CHECKER,
        "checker_sha256": ours,
        "params": {"step": "read_advisory"},
        "timeout_seconds": 60,
    }
    objective = {"type": "objective", "statement": "x", "verifier": verifier}
    oid = build.harness.module("canonical").digest(objective)
    claim = {"type": "claim", "objective_id": oid, "artifact": {}}
    cid = build.harness.module("canonical").digest(claim)
    verdict = {"type": "verdict", "claim_id": cid, "objective_id": oid, "status": "accept"}
    good = [entry({"type": "question", "title": "x"}), entry(objective), entry(claim), entry(verdict)]
    assert build.names_only_our_checker(good) is None
    replay = {"kind": "replay", "command": ["sh", "-c", "true"], "code": {}}
    assert "not the research side's own pinned checker" in build.names_only_our_checker(
        [entry({**objective, "verifier": replay})]
    )
    assert "not the research side's own pinned checker" in build.names_only_our_checker(
        [entry({**objective, "verifier": {**verifier, "checker_sha256": "0" * 64}})]
    )
    carrier = {**claim, "verifier": replay}
    assert "carries something to run" in build.names_only_our_checker([entry(objective), entry(carrier)])
    posing = {"type": "verdict", "claim_id": cid, "objective_id": cid, "status": "accept"}
    assert "does not point at" in build.names_only_our_checker([entry(objective), entry(claim), entry(posing)])
    assert "does not point at an earlier objective" in build.names_only_our_checker([entry(claim), entry(objective)])
    assert "of its own kind" in build.names_only_our_checker([{"kind": "claim", "payload": objective}])

"""Certificate checker of the decision entries in an assessment's Otto ledger (phase 5c, second part).

Otto's harness runs it, pinned by SHA-256, with the standard library only:
stdin: {"params": {...}, "artifact": {...}}; stdout: {"status": "accept" | "reject", "detail": ...}.

It stands beside recheck.py, which is left exactly as it was: a ledger written before this file existed names only
recheck.py, and still reads and checks as before.

One kind of objective uses it.

  kind "decision": Otto made a proposal in this assessment (a check, a fix, a change to the migration plan, or a
  status of a dependency). `params` names the proposal and its kind. A claim under it is one decision a person
  recorded on that proposal: accept, reject, undo or reconsider. It is accepted only when it names the same
  proposal, carries the SHA-256 of what was proposed, says who decided and when, counts its place among the
  decisions on that proposal, and is a step that the state before it allows.

"accept" from this checker means the entry is whole and in order. It is NOT a result of a test and is never shown
as one, and it is not the person's decision either: that is the entry's own `decision` field. This checker never
sees whether anything passed or failed.
"""
import json
import re
import sys

HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
STAMP = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|\+00:00)\Z")
KEY = re.compile(r"\A[a-z][a-z0-9_]{0,23}\Z")
KINDS = ("check", "fix", "plan", "dependency")
# (the state before, the decision) -> the state after. Nothing else is a step this app has.
STEPS = {("proposed", "accept"): "accepted", ("proposed", "reject"): "rejected",
         ("accepted", "undo"): "proposed", ("rejected", "reconsider"): "proposed"}
# A decision entry holds exactly these. With no other field there is no place for a result, whatever it might be called.
FIELDS = {"proposal", "proposal_kind", "proposal_sha256", "title", "decision", "before", "after", "by", "at", "reason", "number", "about"}
MAX_ABOUT = 12


def is_text(value, limit):
    """One short line of plain text."""
    return isinstance(value, str) and 0 < len(value) <= limit and value.isprintable()


def check_decision(params, artifact):
    if not is_text(params.get("proposal"), 200) or params.get("proposal_kind") not in KINDS:
        return "the entry does not name a proposal and its kind"
    if set(artifact) != FIELDS:
        return "a decision entry holds what was decided, by whom and when, and nothing else"
    if artifact["proposal"] != params["proposal"] or artifact["proposal_kind"] != params["proposal_kind"]:
        return "the decision names another proposal than the one this entry is about"
    if not isinstance(artifact["proposal_sha256"], str) or not HEX64.match(artifact["proposal_sha256"]):
        return "the decision does not carry the SHA-256 of what was proposed"
    if not is_text(artifact["title"], 300):
        return "the decision does not say, in one plain line, what was proposed"
    before, decision = artifact["before"], artifact["decision"]
    if not isinstance(before, str) or not isinstance(decision, str) or STEPS.get((before, decision)) is None:
        return "the decision is not a step the state before it allows"
    if artifact["after"] != STEPS[(before, decision)]:
        return "the state after the decision is not the one that step leads to"
    if not is_text(artifact["by"], 100):
        return "the decision does not say who made it"
    if not isinstance(artifact["at"], str) or not STAMP.match(artifact["at"]):
        return "the decision does not say when it was made"
    reason = artifact["reason"]
    if reason is not None and (decision != "reject" or not is_text(reason, 300)):
        return "a reason is one short plain line, and only a reject carries one"
    number = artifact["number"]
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        return "the decision does not count its place among the decisions on this proposal"
    if number == 1 and before != "proposed":
        return "the first decision on a proposal starts from a proposal nobody has decided yet"
    about = artifact["about"]
    if not isinstance(about, dict) or len(about) > MAX_ABOUT:
        return "what the proposal is about is not a short list of names"
    for name, value in about.items():
        if not isinstance(name, str) or not KEY.match(name):
            return "what the proposal is about is not a short list of names"
        if not (value is None or is_text(value, 300) or (isinstance(value, int) and not isinstance(value, bool))):
            return "what the proposal is about is not a short list of names"
    return None


def main():
    try:
        data = json.load(sys.stdin)
        params, artifact = data.get("params"), data.get("artifact")
        if not isinstance(params, dict) or not isinstance(artifact, dict):
            problem = "the claim is not in the shape this checker knows"
        elif params.get("kind") == "decision":
            problem = check_decision(params, artifact)
        else:
            problem = "the entry is of a kind this checker does not know"
    except Exception as exc:  # a checker never crashes on a claim: an unreadable claim is rejected
        problem = "the claim could not be read (" + exc.__class__.__name__ + ")"
    if problem:
        print(json.dumps({"status": "reject", "detail": problem}))
    else:
        print(json.dumps({"status": "accept", "detail": "whole and in order (this is not a result of a test, and not the decision itself)"}))


main()

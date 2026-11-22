"""Certificate checker of an assessment's Otto ledger (phase 5c).

Otto's harness runs it, pinned by SHA-256, with the standard library only:
stdin: {"params": {...}, "artifact": {...}}; stdout: {"status": "accept" | "reject", "detail": ...}.

Two kinds of objective use it.

  kind "run": an advisory check was locked. `params` holds what was locked: the test's fingerprint, the design's
  SHA-256, the pack's fingerprint, the advisory. A claim under it is one reviewed run of that check. It is accepted
  only when the run names the same locked test, carries the SHA-256 of its run record and of its review, was
  proposed by the pack and reviewed by someone else, and ran in a phase this app has.

  kind "step": a Claude step was taken in the app (writing a change for the customer's own code). A claim under it
  is accepted only when the prompt and the answer are there and match their SHA-256, and the record says where the
  answer came from.

"accept" means bound and consistent. It is NOT a result of a test and is never shown as one: results come only from
the reviewer, and this checker never sees whether a run passed or failed.
"""
import hashlib
import json
import re
import sys

HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")       # the whole value: 64 hex characters and nothing after them
PHASES = ("first", "retest", "proof")
PACK_ID = "isogeny.otto-pack/1"
# A run entry holds exactly these, and what it ran on exactly those: fingerprints and names. With no other field
# there is no place for a result, whatever it might be called.
RUN_FIELDS = {"test", "run_id", "run_sha256", "review_sha256", "proposed_by", "reviewer", "phase", "ran_on"}
RAN_ON_FIELDS = {"name", "version", "mode", "commit"}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_hex(value):
    return isinstance(value, str) and bool(HEX64.match(value))


def is_name(value):
    """A short plain line of text (a component's name, a version, a mode), or nothing."""
    return value is None or (isinstance(value, str) and 0 < len(value) <= 200 and value.isprintable())


def check_run(params, artifact):
    for name in ("test", "design", "pack"):
        if not is_hex(params.get(name)):
            return "the lock entry lacks the " + name + " fingerprint"
    if artifact.get("test") != params["test"]:
        return "the run names another locked test than the one this entry locked"
    if not is_hex(artifact.get("run_sha256")) or not is_hex(artifact.get("review_sha256")):
        return "the run or its review has no SHA-256"
    if artifact.get("proposed_by") != PACK_ID:
        return "the test was not proposed by a test pack"
    reviewer = artifact.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer or reviewer == artifact.get("proposed_by"):
        return "the reviewer is missing, or is the one that proposed the test"
    if artifact.get("phase") not in PHASES:
        return "the run is in a phase this app does not have"
    if not isinstance(artifact.get("run_id"), int) or isinstance(artifact.get("run_id"), bool) or artifact["run_id"] < 1:
        return "the run has no number"
    if set(artifact) != RUN_FIELDS:
        return "a ledger entry holds fingerprints and names only, never a result or anything else"
    ran_on = artifact["ran_on"]
    if not isinstance(ran_on, dict) or set(ran_on) != RAN_ON_FIELDS or not all(is_name(value) for value in ran_on.values()):
        return "what the run ran on is not a name, a version, a mode and a commit"
    if not is_name(reviewer) or len(reviewer) > 80:
        return "the reviewer is not a plain name"
    return None


def check_step(params, artifact):
    step = artifact.get("step")
    if not isinstance(step, dict):
        return "the claim holds no step record"
    for name in ("step", "source", "prompt", "answer", "prompt_sha256", "answer_sha256", "at", "how"):
        if not isinstance(step.get(name), str) or not step[name]:
            return "the step record lacks its " + name
    if step["step"] != params.get("step") or artifact.get("advisory") != params.get("advisory"):
        return "the step or the advisory is not the one this entry names"
    if sha(step["prompt"]) != step["prompt_sha256"] or sha(step["answer"]) != step["answer_sha256"]:
        return "the prompt or the answer does not match its SHA-256"
    if step["source"] == "live":
        if not isinstance(step.get("model"), str) or not step["model"]:
            return "a live answer must name the model that gave it"
    elif step["source"] != "recorded" or step.get("model") is not None:
        return "the step record does not say where the answer came from"
    if artifact.get("outcome") not in ("used", "refused"):
        return "the claim does not say whether the answer was used"
    if artifact["outcome"] == "refused" and not (isinstance(artifact.get("refusal"), str) and artifact["refusal"].strip()):
        return "a refused answer must carry the reason"
    return None


def main():
    try:
        data = json.load(sys.stdin)
        params, artifact = data.get("params"), data.get("artifact")
        if not isinstance(params, dict) or not isinstance(artifact, dict):
            problem = "the claim is not in the shape this checker knows"
        elif params.get("kind") == "run":
            problem = check_run(params, artifact)
        elif params.get("kind") == "step":
            problem = check_step(params, artifact)
        else:
            problem = "the entry is of a kind this checker does not know"
    except Exception as exc:  # a checker never crashes on a claim: an unreadable claim is rejected
        problem = "the claim could not be read (" + exc.__class__.__name__ + ")"
    if problem:
        print(json.dumps({"status": "reject", "detail": problem}))
    else:
        print(json.dumps({"status": "accept", "detail": "bound and consistent (this is not a result of a test)"}))


main()

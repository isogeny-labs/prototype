"""Certificate checker for one Claude step in Otto's research ledger.

Otto's harness runs it, pinned by SHA-256, with the standard library only:
stdin: {"params": {"step": ..., "advisory": ...}, "artifact": {...}}; stdout: {"status": "accept" | "reject", "detail": ...}.

It accepts a claim only when the record of the step is whole and consistent:
  - the prompt and the answer are both there, and their SHA-256 are the ones the record states;
  - the step and the advisory are the ones the objective names;
  - the record says where the answer came from (recorded or live) and, for a live answer, which model gave it;
  - an answer that was used parses as the one JSON object the record holds as "parsed", and every line it quotes
    from the publisher stands, character for character, in the prompt that was sent;
  - an answer that was refused carries the plain reason.

"accept" means the record is whole. It says nothing about whether the answer is right: a design is tried on public
copies by Otto's harness, and so is a fix, before either may ship.
"""
import hashlib
import json
import sys


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def answer_object(answer):
    text = answer.strip()
    if text.startswith("```"):
        first, _, rest = text.partition("\n")
        if first.strip() not in ("```", "```json") or not rest.rstrip().endswith("```"):
            return None
        text = rest.rstrip()[:-3].strip()
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def quotes(value):
    """Every {"source", "text"} object anywhere inside a parsed answer."""
    if isinstance(value, dict):
        if set(value) == {"source", "text"} and isinstance(value.get("text"), str):
            yield value["text"]
        else:
            for item in value.values():
                yield from quotes(item)
    elif isinstance(value, list):
        for item in value:
            yield from quotes(item)


def check(params, artifact):
    if not isinstance(params, dict) or not isinstance(artifact, dict):
        return "the claim is not in the shape of a Claude step"
    step = artifact.get("step")
    if not isinstance(step, dict):
        return "the claim holds no step record"
    for name in ("step", "source", "prompt", "answer", "prompt_sha256", "answer_sha256", "at", "how"):
        if not isinstance(step.get(name), str) or not step[name]:
            return "the step record lacks its " + name
    for name in ("input_tokens", "output_tokens", "cost_nano_usd"):
        if not isinstance(step.get(name), int) or isinstance(step.get(name), bool) or step[name] < 0:
            return "the step record lacks its " + name
    if step["step"] != params.get("step") or artifact.get("advisory") != params.get("advisory"):
        return "the step or the advisory is not the one the objective names"
    if sha(step["prompt"]) != step["prompt_sha256"]:
        return "the prompt does not match its SHA-256"
    if sha(step["answer"]) != step["answer_sha256"]:
        return "the answer does not match its SHA-256"
    if step["source"] == "live":
        if not isinstance(step.get("model"), str) or not step["model"]:
            return "a live answer must name the model that gave it"
    elif step["source"] == "recorded":
        if step.get("model") is not None or step["cost_nano_usd"] != 0:
            return "a recorded answer names no model and has no cost"
    else:
        return "the step record does not say where the answer came from"
    outcome = artifact.get("outcome")
    if outcome == "refused":
        if not isinstance(artifact.get("refusal"), str) or not artifact["refusal"].strip():
            return "a refused answer must carry the reason"
        return None
    if outcome != "used":
        return "the claim does not say whether the answer was used"
    parsed = artifact.get("parsed")
    if not isinstance(parsed, dict) or answer_object(step["answer"]) is None:
        return "the answer is not the one JSON object that was asked for"
    for text in quotes(parsed):
        if text not in step["prompt"]:
            return "a quoted line is not in the text that was sent"
    return None


def main():
    try:
        data = json.load(sys.stdin)
        problem = check(data.get("params"), data.get("artifact"))
    except Exception as exc:  # a checker never crashes on a claim: an unreadable claim is rejected
        problem = "the claim could not be read (" + exc.__class__.__name__ + ")"
    if problem:
        print(json.dumps({"status": "reject", "detail": problem}))
    else:
        print(json.dumps({"status": "accept", "detail": "the step record is whole: hashes match, the answer has its shape, quoted lines stand in the prompt"}))


main()

"""The engine in the socket since phase 5c: the rule engine as before, with Otto asked first for a code change when
an advisory check has failed on the assessment's own program.

Everything else is passed straight to the rule engine, under the rule engine's own id: its tests keep their stamp,
so nothing that was graded before moves. A change Otto wrote is stamped as Otto's and labelled "Written by Otto";
it takes exactly the path of a fix-template change (a copy on a branch, the byte-for-byte check, the proof that
reruns every locked test, the separate reviewer, a person's approval and merge).

Looking at a page never asks Claude and never writes anything: a view uses the answer already stored for this
assessment, or the recorded answer for exactly this prompt. A live call is made only by a person's click (Connect
demo code), only with Live Otto on and a key present, and within the spending limit of that one request.
"""
from __future__ import annotations

from app.engine import research
from app.otto import fixes, model
from app.run import components

# Only our registered demo programs may run, so a change can be proven only if the program it gives is one of them.
NOT_REGISTERED = ("the program it gives is not the same as any of our bundled demo components, byte for byte, and only those "
                  "can run in this version, so it can't be proven here.")


class OttoCouldNot(Exception):
    """A person asked for Otto's change and Otto has none to give. str(exc) is one plain sentence."""


class OttoEngine:
    def __init__(self, rules: research.RuleEngine, lab) -> None:
        self.rules, self._lab = rules, lab

    @property
    def engine_id(self) -> str:
        return self.rules.engine_id

    def __getattr__(self, name: str):
        return getattr(self.rules, name)      # propose_tests, design_test, design_capability, design_measurement, dig_deeper, review

    def __setattr__(self, name: str, value) -> None:
        # What this class has itself stays here. Every other part is the rule engine's own, so swapping one of them
        # reaches the engine that uses it (the rule engine calls its parts on itself, not on this wrapper).
        if name in ("rules", "_lab") or hasattr(type(self), name):
            object.__setattr__(self, name, value)
        else:
            setattr(self.rules, name, value)

    def __delattr__(self, name: str) -> None:
        if name in self.__dict__:
            object.__delattr__(self, name)
        else:
            delattr(self.rules, name)

    def propose_change(self, request: dict) -> dict | None:
        """As the rule engine's, plus, beside the question, who is asking: `asking` holds `plan_id`, `mode` ("view"
        when a page is only shown, "connect" for a person's click) and `template_only`. Each failed advisory check
        carries its `advisory` and `title`. The rule engine is given the question only. Raises OttoCouldNot only in
        connect mode."""
        asking = request.get("asking")
        if not isinstance(asking, dict):
            asking = {}
        question = {k: v for k, v in request.items() if k != "asking"}
        # Only the failed tests of the program itself are Otto's business (a failed server test is not in its code).
        # Each keeps its place in the request, because the answer names the failures by that place.
        failed = [(place, r) for place, r in enumerate(request.get("failed") or [])
                  if isinstance(r, dict) and r.get("kind") in research.SOFTWARE_TEST_KINDS]
        first = next((r for _, r in failed if r.get("kind") == research.ADVISORY_KIND and isinstance(r.get("advisory"), dict)), None)
        if first is None or asking.get("template_only") or asking.get("plan_id") is None:
            return self.rules.propose_change(question)
        connect = asking.get("mode") == "connect"
        try:
            proposal, note = self._otto_change(question, int(asking["plan_id"]), failed, first["advisory"], connect)
        except model.ModelError as exc:
            if connect:
                raise OttoCouldNot(f"Otto could not write the change: {exc}") from None
            proposal, note = None, str(exc)
        if proposal is not None:
            return proposal
        fallback = self.rules.propose_change(question)
        if fallback is not None and note:
            fallback = {**fallback, "otto_note": note}
        return fallback

    def _otto_change(self, request: dict, plan_id: int, failed: list[tuple[int, dict]], advisory: dict,
                     connect: bool) -> tuple[dict | None, str | None]:
        lab = self._lab
        component, files = request.get("component") or {}, request.get("files") or {}
        asked = [{"title": r.get("title") or research.title_of(r.get("kind")), "wrong": list((r.get("detail") or {}).get("wrong") or [])}
                 for _, r in failed]
        prompt = fixes.write_fix_prompt(component, advisory, asked, files)
        digest = model.sha256_text(prompt)
        key = fixes.key_of(advisory["id"])
        about = {"advisory": advisory["id"], "plain_name": advisory.get("plain_name"), "pack": advisory.get("pack"),
                 "prompt_sha256": digest}
        stored = lab.otto_stored_step(plan_id, "write_fix", digest)
        asked_now = False       # whether this very click asked Claude (the page then showed no answer to judge before it)
        if stored is not None:
            answer, source, how, step_id = stored["answer"], stored["source"], stored["how"], stored["id"]
            about.update(model=stored["model"], at=stored["at"], ledger_entry=stored["claim_id"])
        else:
            client = lab.otto_model(live=connect)
            step = client.recorded("write_fix", prompt)
            if step is None:
                if not connect:
                    if lab.otto_live_ready():   # a person's click will ask Claude; looking at the page does not
                        return self._pending(request, failed, advisory, key), None
                    return None, "No recorded answer: this needs Live Otto."
                if not client.live_ready:
                    return None, "No recorded answer: this needs Live Otto."
                step = client.ask("write_fix", prompt)          # the live call; ModelError says why there is no answer
                asked_now = True
            answer, source, how, step_id = step.answer, step.source, step.how, None
            about.update(model=step.model, at=step.at, ledger_entry=None)
            if connect:
                try:
                    self._usable(answer, component, files, len(failed))
                    outcome, refusal = "used", None
                except fixes.Refused as exc:
                    outcome, refusal = "refused", str(exc)
                step_id = lab.otto_record_step(plan_id, advisory["id"], step, outcome, refusal)
                kept = lab.otto_stored_step(plan_id, "write_fix", digest) or {}
                about["ledger_entry"] = kept.get("claim_id")
        try:
            change = self._usable(answer, component, files, len(failed))
        except fixes.Refused as exc:
            if asked_now:   # the person asked for Otto's change and there is none to connect: say so, connect nothing
                raise OttoCouldNot(f"Otto's change could not be used: {exc}") from None
            # The page already said this and offered the fix template in its place, so that is what is connected.
            return None, f"Otto wrote one, but it could not be used: {exc}"
        about.update(source=source, how=how, step_id=step_id, answer_sha256=model.sha256_text(answer), title=change["title"],
                     summary=change["summary"], pending=False)
        return {"template_id": key, "title": change["title"], "branch": "fix/" + key, "label": fixes.LABEL,
                "answers": [failed[n][0] for n in change["answers"]],     # the places in the request of the failures it answers
                "files": change["files"], "edits": change["edits"], "written_by": "otto", "proposed_by": fixes.OTTO_ID, "otto": about}, None

    @staticmethod
    def _usable(answer: str, component: dict, files: dict, failures: int) -> dict:
        """The change in Claude's answer, if it is one Otto may offer: a clean change to the code as it is, that gives
        one of our own registered demo programs byte for byte. Nothing is run to find out. Raises fixes.Refused."""
        change = fixes.check_change(answer, files, failures)
        built = {name: text.encode("utf-8") for name, text in change["files"].items()}
        if components.registered_version(component.get("name"), built) is None:
            raise fixes.Refused(NOT_REGISTERED)
        return change

    @staticmethod
    def _pending(request: dict, failed: list[tuple[int, dict]], advisory: dict, key: str) -> dict:
        """Live Otto is on and no answer exists yet: the fix is listed so a person can connect the code, which is the
        click that asks Claude. It holds no change yet."""
        answers = [place for place, r in failed if r.get("kind") == research.ADVISORY_KIND]
        return {"template_id": key, "title": f"A change for {advisory['id']}, written by Otto when the code is connected",
                "branch": "fix/" + key, "label": fixes.LABEL, "answers": answers, "files": dict(request.get("files") or {}), "edits": [],
                "written_by": "otto", "proposed_by": fixes.OTTO_ID,
                "otto": {"advisory": advisory["id"], "plain_name": advisory.get("plain_name"), "pack": advisory.get("pack"), "pending": True,
                         "summary": None, "source": "live", "how": "Live: Claude, through your key"}}

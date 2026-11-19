"""Otto proposes; a person decides (phase 5c, second part).

Everything Otto produces in an assessment arrives as a proposal labelled "From Otto", with Accept and Reject:

    check        an advisory check of an installed test pack, for one signing program of the file (its home: Advisories)
    fix          Otto's fix for a failed advisory check: a change to your own program, or a library update (Fixes)
    plan         something to fix first on a track of the migration plan, when a result calls for it (Migration)
    dependency   a status for a library of the dependency list that a published advisory names (Dependencies)

Rules kept here:
  - A proposal is worked out again on every read, from records already kept: the installed packs, the file, what the
    reviewer decided, the dependency list. Reading a page writes nothing and asks Claude nothing.
  - Plan and dependency proposals come from fixed rules over those records. No model is asked for them.
  - Only a person's decision is stored: accept, reject (with an optional short reason), undo of an accept, or
    reconsider of a reject. Rows are only ever added (otto_decisions), and each decision is also written to the
    assessment's Otto ledger, with who and when. A rejected proposal is never removed; it can be taken up again.
  - An accept can be undone until what it led to has run or been applied.
  - Accepting runs nothing. A check that was accepted joins the test plan and is run there, by a person's click.
  - A proposal and its decisions decide no result. Results come only from the runner and the reviewer.
  - Without the pinned Otto harness a decision could not be recorded in its ledger, so nothing can be decided.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import func, select

from app.canonical import sha256_hex
from app.db import ImportRow, OttoCheckRow, OttoDecisionRow, PlanItemRow, PlanRow, ReviewRow, TestRunRow, TestSpecRow, iso
from app.engine import research
from app.errors import BadRequest, Conflict, NotFound
from app.knowledge.versions import at_least, read_version
from app.lab.testlab import read_spec
from app.otto import assurance, checks, designs, harness

LABEL = "From Otto"
BY = "You"                 # the name the app records for the person at the keyboard, as it does for approvals
KINDS = ("check", "fix", "plan", "dependency")
DECISIONS = ("accept", "reject", "undo", "reconsider")
# (the state before, the decision) -> the state after
STEPS = {("proposed", "accept"): "accepted", ("proposed", "reject"): "rejected",
         ("accepted", "undo"): "proposed", ("rejected", "reconsider"): "proposed"}
HOME = {"check": "advisories", "fix": "fixes", "plan": "migration/systems", "dependency": "migration/dependencies"}
MAX_REASON = 300
NO_OTTO_TAIL = " A decision on a proposal is recorded in Otto's ledger, so nothing can be decided here."
CLOSED = "This assessment is closed. Start a new one to continue."
NOT_CURRENT = "This is no longer proposed here: what it was about has changed since. It stays on the record."
LEGACY = "This check was added before decisions were recorded, so there is no accept to undo."
DONE = "The check has passed since, so this can't be undone."
DONE_REJECTED = "The check has passed since, so this can't be taken up again."


def now_stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def short(*parts: object) -> str:
    return hashlib.sha256("\0".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def check_id(advisory_id: str, design_sha256: str, program_ref: str) -> str:
    return f"check-{str(advisory_id).lower()}-{short(design_sha256, program_ref)}"


def code_fix_id(fix_key: str) -> str:
    return f"fix-code-{fix_key}"


def update_fix_id(item_id: int) -> str:
    return f"fix-update-{int(item_id)}"


def plan_id_for(system_key: str, item_id: int) -> str:
    return f"plan-{short(system_key, item_id)}"


def dependency_id(library: str, version: object, advisory_id: str) -> str:
    """One proposal for one library in one version and one advisory, wherever (and however often) the list names it. So
    a decision stays with that library and version when a newer list is added, and never moves to another row."""
    return f"dep-{short(str(library).casefold(), version, advisory_id)}"


def content(proposal: dict) -> dict:
    """What Otto proposed, and nothing about what was decided: this is what a decision's fingerprint is made from."""
    return {k: proposal[k] for k in ("id", "kind", "title", "why", "lines", "about")}


def fingerprint(proposal: dict) -> str:
    return sha256_hex(content(proposal))


def clean_reason(reason: object) -> str | None:
    """A reason as a person typed it, as one short plain line (or None). Raises BadRequest when it is too long."""
    if reason is None:
        return None
    if not isinstance(reason, str):
        raise BadRequest("The reason must be text.", field="reason")
    text = " ".join("".join(ch if ch.isprintable() else " " for ch in reason).split())
    if len(text) > MAX_REASON:
        raise BadRequest(f"Keep the reason to {MAX_REASON} characters or fewer.", field="reason")
    return text or None


def _plain(value: object, limit: int = 300) -> str | None:
    """A value for a ledger entry's `about`: one short plain line."""
    if value is None:
        return None
    text = " ".join("".join(ch if ch.isprintable() else " " for ch in str(value)).split())
    return (text[:limit] or None)


def make(kind: str, pid: str, *, title: str, why: str, lines: list[str], about: dict, proposed_at: str | None, item: object,
         facts: dict | None = None) -> dict:
    """One proposal as Otto made it. `about`: a short list of names (it goes into the ledger entry of each decision).
    `facts`: what the rules below need to say whether an accept can still be undone; never stored."""
    return {"id": pid, "kind": kind, "label": LABEL, "title": _plain(title) or "A proposal from Otto", "why": why, "lines": [str(x) for x in lines if x],
            "about": {k: (v if isinstance(v, int) and not isinstance(v, bool) else _plain(v)) for k, v in about.items()},
            "proposed_at": proposed_at, "link": {"page": HOME[kind], "item": item}, "current": True, "facts": dict(facts or {})}


def _later_targets(row: dict | None, fixed: str) -> list[str]:
    """The "first versions that can" among a dependency row's own "no" answers that are past the version an advisory's
    publisher names as fixed, oldest first, each once. Empty when there is none, and a version that can't be read is
    left out: nothing is guessed."""
    from app.knowledge.versions import key
    if row is None or read_version(fixed) is None:
        return []
    known = {str(a.get("first_version")) for a in (row.get("answers") or {}).values()
             if isinstance(a, dict) and a.get("answer") == "no" and a.get("first_version") not in (None, "none_known")}
    later = [v for v in known if read_version(v) is not None and not at_least(read_version(fixed), v)]     # type: ignore[arg-type]
    return sorted(later, key=lambda v: key(read_version(v)))     # type: ignore[arg-type]


def _later_line(row: dict | None, fixed: str) -> str:
    """One sentence for a dependency proposal when the same row's post-quantum answers name later versions than the
    advisory's fix: two version numbers on one row are two different questions, not a contradiction."""
    later = _later_targets(row, fixed)
    if not later:
        return ""
    if len(later) == 1:
        return (f"This answers the advisory only. For post-quantum, this row's own answer names {later[0]} or later: an update to that "
                f"version is past {fixed} too.")
    return ("This answers the advisory only. For post-quantum, this row's own answers name later versions ("
            + ", ".join(f"{v} or later" for v in later) + f"): an update to one of those is past {fixed} too.")


def state_of(rows: list) -> str:
    return rows[-1].after if rows else "proposed"


def accept_stands(proposal: dict) -> str | None:
    """Why an accept of this proposal can no longer be undone (what it led to has run or been applied), or None. The
    one rule, also read by the Otto panel (app/assistant), which only reads."""
    return ProposalsMixin._otto_locked(proposal)


class ProposalsMixin:
    """Mixed into `Lab`."""

    db: Callable[..., Any]
    settings: Any
    jobs: Any
    mode: Any
    _plan: Callable[..., PlanRow]
    _plan_lock: Any
    _otto_lock: Any
    _claims: Callable[..., list[dict]]
    _items: Callable[..., list]
    _lock_spec: Callable[..., str]
    _shown: Callable[..., list[dict]]
    _fixes: Callable[..., list[dict]]
    _systems: Callable[..., list[dict]]
    _dependency_state: Callable[..., dict | None]
    _installed_packs: Callable[..., list]
    _pack_advisories: Callable[..., list]
    _closed_at: Callable[..., Any]
    assessment_for: Callable[..., Any]
    decision_name: Callable[..., str]

    # ---------------------------------------------------------------- the stored decisions

    @staticmethod
    def _decision_rows(db, plan_id: int) -> dict[str, list[OttoDecisionRow]]:
        out: dict[str, list[OttoDecisionRow]] = {}
        for row in db.scalars(select(OttoDecisionRow).where(OttoDecisionRow.plan_id == plan_id).order_by(OttoDecisionRow.id)).all():
            out.setdefault(row.proposal_id, []).append(row)
        return out

    def _otto_state(self, db, plan_id: int, proposal_id: str) -> str:
        """Where one proposal stands by the decisions on record: proposed, accepted or rejected."""
        row = db.scalars(select(OttoDecisionRow).where(OttoDecisionRow.plan_id == plan_id, OttoDecisionRow.proposal_id == proposal_id)
                         .order_by(OttoDecisionRow.id.desc()).limit(1)).first()
        return row.after if row is not None else "proposed"

    # ---------------------------------------------------------------- what Otto proposes, worked out now

    def _check_proposals(self, db, plan: PlanRow, upto) -> list[dict]:
        """One proposal for each ready pack test and each signing program of the file it fits."""
        imp = db.get(ImportRow, plan.import_id)
        fitting = checks.programs_that_fit(self._claims(imp))
        installed = {pack.fingerprint: row.installed_at for row, pack in self._installed_packs(db, upto)}
        out = []
        for pack, advisory in self._pack_advisories(db, upto):
            if advisory["test"]["state"] != "ready":
                continue
            digest = advisory["test"]["design_sha256"]
            design = pack.design(digest)
            if design is None:
                continue
            reading = advisory["reading"] or {}
            package = advisory["package"]["name"]
            fixed = (reading.get("fixed") or {}).get("version")
            cases = design["cases"]
            trial = (advisory["test"].get("trial") or {}).get("arms") or {}
            at = max(_aware(installed[pack.fingerprint]), _aware(imp.created_at)) if pack.fingerprint in installed else _aware(imp.created_at)
            for program in fitting:
                item = checks.existing_item(self, db, plan.id, digest, program["ref"])
                in_plan = item is not None and not item.removed
                runs = int(db.scalar(select(func.count(TestRunRow.id)).where(TestRunRow.plan_item_id == item.id)) or 0) if item is not None else 0
                live = item is not None and any(job is not None and job.status != "done"
                                                for job in (self.jobs.get((item.id, phase)) for phase in ("first", "retest", "proof")))
                if program["component"] == package:
                    why = (f"The advisory is about {package}, and your file lists {program['label']}."
                           + (f" Its publisher names {fixed} as the fixed version." if fixed else ""))
                else:
                    why = (f"{program['label']} checks ECDSA P-256 signatures, and this test hands a program published signature cases of the "
                           f"kind the advisory describes. The advisory is about {package}, not about {program['component']}: no version "
                           f"number can say whether {program['component']} has the same weakness, so the test asks the program itself.")
                tried = []
                a, f = trial.get("affected") or {}, trial.get("fixed") or {}
                if "total" in a and "total" in f:
                    tried.append(f"Tried on public copies before the pack was signed: {package} {a.get('version')} got {a['wrong']} of {a['total']} "
                                 f"wrong, {package} {f.get('version')} got {f['wrong']} wrong, and the control that must fail did.")
                out.append(make(
                    "check", check_id(advisory["id"], digest, program["ref"]),
                    title=f"{designs.title_of(design)} on {program['label']}", why=why,
                    lines=[design["question"].replace("{program}", program["label"]),
                           f"{len(cases['ids'])} published {'case' if len(cases['ids']) == 1 else 'cases'} from Project Wycheproof, pinned by SHA-256.",
                           "Control that must fail: " + designs.BLOCKS[designs.BLOCK]["controls"][designs.CONTROL],
                           *tried],
                    about={"advisory": advisory["id"], "program": program["label"], "design": digest, "pack": pack.version},
                    proposed_at=iso(at), item=advisory["id"],
                    facts={"advisory_id": advisory["id"], "design_sha256": digest, "program_ref": program["ref"], "pack_fingerprint": pack.fingerprint,
                           "item_id": item.id if item is not None else None, "in_plan": in_plan, "runs": runs, "live": bool(live)}))
        return out

    def _fix_proposals(self, db, plan: PlanRow, fixes: list[dict]) -> list[dict]:
        """One proposal for each fix that is Otto's: a change it wrote (or will write) for the file's own program, and
        the library update a test pack carries for a failed advisory check."""
        out = []
        for fix in fixes:
            otto, pack_fix = fix.get("otto"), fix.get("otto_fix")
            last_run = max((a["run_id"] for a in fix.get("answers") or []), default=None)
            run = db.get(TestRunRow, last_run) if last_run is not None else None
            at = run.finished_at if run is not None else None
            if fix["kind"] == "code" and otto:
                component = fix["component"]
                program = f"{component['name']} {component['version']}"
                advisory = f"{otto['advisory']} ({otto.get('plain_name') or 'an advisory'})"
                if otto.get("pending"):
                    title = f"Have Otto write a change for {otto['advisory']} in {component['name']}"
                    lines = ["Live Otto is on: nothing is written yet. When you connect the code, Claude is asked to write the change, once, "
                             "within the spending limit.",
                             "What that click sends: the advisory text, the source file of the failing program and the cases it got wrong.",
                             "An answer that is not, byte for byte, one of our registered demo programs is refused."]
                else:
                    title = f"{otto.get('title') or 'A change written by Otto'} ({component['name']})"
                    # (These lines stay on the card after the change is connected and merged, so they say what the change
                    # does and what Accept does, and nothing about where things stand: the card's own status line says that.)
                    lines = ["What it changes: " + str(otto.get("summary") or "").strip(),
                             "Written by Otto. Accepting it runs nothing and changes nothing: you then connect the code, and the proof "
                             "reruns every locked test on the changed code before anything is offered for review."]
                out.append(make("fix", code_fix_id(fix["id"][4:] if fix["id"].startswith("fix-") else fix["id"]), title=title,
                                why=f"The advisory check for {advisory} failed on {program}, which is your own code.",
                                lines=lines,
                                about={"advisory": otto["advisory"], "program": program, "fix": fix["id"], "written": "no" if otto.get("pending") else "yes",
                                       "prompt_sha256": otto.get("prompt_sha256"), "answer_sha256": otto.get("answer_sha256")},
                                proposed_at=at, item=fix["id"],
                                facts={"fix_id": fix["id"], "code": True, "connected": fix.get("change") is not None or fix.get("connection") is not None}))
            elif fix["kind"] == "text" and pack_fix and pack_fix.get("kind") == "update":
                item_id = fix["answers"][-1]["item_id"] if fix.get("answers") else pack_fix.get("item_id")
                program = pack_fix.get("program") or f"{pack_fix['library']}"
                here = pack_fix.get("here") or {}
                out.append(make("fix", update_fix_id(item_id), title=f"Update {pack_fix['library']} to {pack_fix['version']}",
                                why=(f"The advisory check for {pack_fix['advisory']} ({pack_fix.get('plain_name') or 'an advisory'}) failed on "
                                     f"{program}, and its publisher names {pack_fix['version']} as the fixed version."),
                                lines=[str(pack_fix.get("summary") or ""), str((pack_fix.get("public") or {}).get("line") or pack_fix.get("reason") or ""),
                                       "This is other people's code: the app offers no code change and no pull request for it. Whoever owns "
                                       "the software updates it; Retest then proves it here."],
                                about={"advisory": pack_fix["advisory"], "library": pack_fix["library"], "version": pack_fix["version"],
                                       "program": program, "fix": fix["id"], "pack": pack_fix.get("pack"),
                                       "public_copies": pack_fix.get("state")},
                                proposed_at=at, item=fix["id"],
                                # (a retest on the fixed version that has a result, also while it is still running, and one that is
                                # running with no result yet: from either moment on, the accept stands)
                                facts={"fix_id": fix["id"], "code": False, "retested": here.get("state", "not_yet") != "not_yet",
                                       "live": bool(here.get("live"))}))
        return out

    def _plan_proposals(self, db, plan: PlanRow, shown: list[dict], fixes: list[dict], decided: set[str] | None = None) -> list[dict]:
        """From a fixed rule over the results: when an advisory check's newest result on a signing program of the file
        is a failure, Otto proposes to put fixing it on that program's Signatures track, as something to fix first.
        `decided`: the proposals a person's decision stands on (accepted or rejected). Such a one stays when a newer
        result of its check passes, and then reads done; one that is open (never decided, or open again after an undo)
        is no longer proposed then."""
        claims = self._claims(db.get(ImportRow, plan.import_id))
        systems = {s["target"]: s for s in self._systems(claims) if s["kind"] == "software"}
        newest: dict[int, dict] = {}
        for r in shown:
            if r["kind"] == research.ADVISORY_KIND and r["tone"] in ("pass", "fail") \
                    and (r["item_id"] not in newest or r["run_id"] > newest[r["item_id"]]["run_id"]):
                newest[r["item_id"]] = r
        out = []
        # A change to a system's plan needs a plan to change: the roadmap places a system only once its status has been
        # measured ("Not placed yet" until then). Asked once, and only when a result could lead to a proposal.
        placed = {s["key"] for s in self._migration_states(db, plan) if s.get("status")} if newest else set()     # type: ignore[attr-defined]
        for item_id, result in newest.items():
            item = db.get(PlanItemRow, item_id)
            spec, _ = read_spec(db.get(TestSpecRow, item.spec_hash)) if item is not None else ({}, False)
            system = systems.get(str((spec.get("target") or {}).get("claim")))
            advisory = (spec.get("inputs") or {}).get("advisory") or {}
            if system is None or not advisory.get("id"):
                continue
            pid = plan_id_for(system["key"], item_id)
            if system["key"] not in placed and pid not in (decided or set()):
                continue        # no plan for this system yet: nothing is proposed until Measure status has placed it
            done = None
            if result["tone"] != "fail":
                if pid not in (decided or set()):
                    continue
                # decided earlier, and a newer result of the check passes now: it is told from the failure it came from
                done = result
                failed = db.scalars(select(TestRunRow).join(ReviewRow, ReviewRow.run_id == TestRunRow.id)
                                    .where(TestRunRow.plan_item_id == item_id, ReviewRow.code == "failed")
                                    .order_by(TestRunRow.id.desc()).limit(1)).first()
                if failed is None:
                    continue
                result = {**result, "run_id": failed.id, "component": failed.component_name, "version": failed.component_version}
            review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == result["run_id"])).first()
            wrong = len((review.detail or {}).get("wrong") or []) if review is not None else 0
            run = db.get(TestRunRow, result["run_id"])
            program = f"{result['component']} {result['version']}" if result.get("version") else str(result.get("component"))
            fix = next((f for f in fixes if any(a.get("item_id") == item_id for a in f.get("answers") or [])), None)
            counted = f"{wrong} published {'case' if wrong == 1 else 'cases'}" if wrong else "published cases"
            passed_on = None
            if done is not None:
                done_run = db.get(TestRunRow, done["run_id"])
                passed_on = {"version": done.get("version"), "at": done_run.finished_at if done_run is not None else None, "run_id": done["run_id"]}
            out.append(make(
                "plan", pid,
                title=f"Fix {system['name']} before its signatures move to post-quantum",
                why=(f"{program} gave the wrong answer on {counted} of the kind {advisory['id']} describes "
                     f"({advisory.get('plain_name') or 'an advisory'}). Moving a program that checks signatures wrongly carries the fault along."),
                lines=["Proposed for the migration plan: something to fix first, on the Signatures track.",
                       "Accepting changes nothing on any system and runs nothing.",
                       "When a newer result of this check passes, it comes off the to-do list. It stays in the history."],
                about={"system": system["key"], "track": "signatures", "advisory": advisory["id"], "program": program, "item": item_id,
                       "run": result["run_id"], "fix": fix["id"] if fix else None},
                proposed_at=run.finished_at if run is not None else None, item=system["key"],
                facts={"system_key": system["key"], "track": "signatures", "item_id": item_id, "fix_id": fix["id"] if fix else None,
                       "advisory_id": advisory["id"], "wrong": wrong, "program": program, "done": passed_on}))
        return out

    def _named_by(self, db, plan: PlanRow, state: dict | None, upto) -> dict[str, list[dict]]:
        """For each library row of the dependency list (by its key): the published advisories of the installed packs
        that name it, each with what this assessment has measured. An advisory names a library when the knowledge base
        has recognised the row as the package the advisory is about, and the version in the list is below the version
        its publisher names as fixed. "Recognised" is by the row's exact package address (a name alone only where the
        row has no address and the knowledge base lists that bare name as safe to match): a package of the same name
        from another ecosystem is not named."""
        if state is None:
            return {}
        claims = self._claims(db.get(ImportRow, plan.import_id))
        programs = research.programs(claims)
        shown = self._shown(db, plan, self._items(db, plan.id))
        out: dict[str, list[dict]] = {}
        for row in state["rows"]:
            library = str(row.get("library") or "")
            if not library:
                continue        # not a library the knowledge base recognises: never matched by its bare name
            here = read_version(row.get("version"))
            for pack, advisory in self._pack_advisories(db, upto):
                reading = advisory["reading"] or {}
                fixed = (reading.get("fixed") or {}).get("version")
                if advisory["package"]["name"].casefold() != library.casefold() or not fixed:
                    continue
                if here is None or read_version(fixed) is None or at_least(here, str(fixed)):
                    continue    # a version that can't be read is never guessed at; at or past the fixed version it is not named
                version_note = "below_fixed"
                measured = self._measured_here(db, plan, advisory, programs, shown, library, row.get("version"))
                out.setdefault(row["key"], []).append({
                    "advisory": advisory["id"], "plain_name": reading.get("plain_name") or advisory["id"], "fixed": fixed, "pack": pack.version,
                    "version_note": version_note, "test": advisory["test"]["state"], "fix": advisory["fix"], "measured": measured,
                    "library": library, "version": row.get("version"), "row": row["id"], "row_key": row["key"], "label": row["label"]})
        return out

    def _measured_here(self, db, plan: PlanRow, advisory: dict, programs: list[dict], shown: list[dict], library: str,
                       version: str | None) -> dict:
        """What this assessment has measured about one advisory on one library version: the newest result of that
        advisory's check on a program of the file with the same name and version, in the reviewer's own terms."""
        digest = advisory["test"]["design_sha256"] if advisory["test"]["state"] == "ready" else None
        if digest is None:
            return {"state": "not_checked", "why": "no_test"}
        same = [p for p in programs if p["component"].casefold() == library.casefold() and p["version"] == version]
        if not same:
            return {"state": "not_checked", "why": "not_in_file"}
        for program in same:
            item = checks.existing_item(self, db, plan.id, digest, program["ref"])
            if item is None or item.removed:
                continue
            results = [r for r in shown if r["item_id"] == item.id and r["version"] == version]
            decided = [r for r in results if r["tone"] in ("pass", "fail")]
            if decided:
                newest = max(decided, key=lambda r: r["run_id"])
                return {"state": "affected" if newest["tone"] == "fail" else "not_affected", "item_id": item.id, "run_id": newest["run_id"]}
            return {"state": "not_checked", "why": "couldnt" if results else "not_run", "item_id": item.id}
        return {"state": "not_checked", "why": "not_added"}

    def _dependency_proposals(self, db, plan: PlanRow, state: dict | None, upto) -> list[dict]:
        """From a fixed rule over the dependency list and the installed packs: for a library that an advisory names,
        where the pack carries the publisher's fixed version as a fix, Otto proposes the status "update first". One
        proposal for one library, version and advisory, however many rows of the list name it (`facts.row_keys`)."""
        from app.present import otto as present_otto      # (words only; imported here to keep this module's top small)
        out: dict[str, dict] = {}
        rows_by_key = {r["key"]: r for r in (state or {}).get("rows") or []}
        for row_key, named in self._named_by(db, plan, state, upto).items():
            for n in named:
                fix = n["fix"]
                if fix.get("kind") != "update" or n["version_note"] != "below_fixed":
                    continue
                pid = dependency_id(n["library"], n["version"], n["advisory"])
                if pid in out:
                    out[pid]["facts"]["row_keys"].append(row_key)
                    out[pid]["facts"]["rows"].append(n["row"])
                    continue
                public = present_otto.public_copies_row(n["fix"], None)
                out[pid] = make(
                    "dependency", pid,
                    title=f"Update {n['library']} {n['version']} to {fix['version']} before the move",
                    why=(f"Your dependency list has {n['label']}. Advisory {n['advisory']} ({n['plain_name']}) is about {n['library']}, and its "
                         f"publisher names {fix['version']} as the fixed version."),
                    lines=[str(fix.get("summary") or ""), public["line"],
                           _later_line(rows_by_key.get(row_key), str(fix["version"])),
                           "Proposed: mark this library “update first”. Accepting changes nothing on any system and runs nothing."],
                    about={"library": n["library"], "version": n["version"], "fixed": fix["version"], "advisory": n["advisory"],
                           "pack": n["pack"], "public_copies": fix.get("state")},
                    proposed_at=(state or {}).get("list", {}).get("at"), item=n["row"],
                    facts={"rows": [n["row"]], "row_keys": [row_key], "advisory_id": n["advisory"]})
        return list(out.values())

    def _proposals(self, db, plan: PlanRow, kinds: tuple[str, ...] | None = None, fixes: list[dict] | None = None,
                   dependency_state: dict | None = None) -> list[dict]:
        """Every proposal of this assessment with where it stands, in a fixed order: checks, fixes, plan changes,
        dependency statuses. A proposal that was decided and is no longer made is kept, from its last decision's copy.
        `fixes` and `dependency_state`: what the caller has already worked out, so it is not worked out twice."""
        wanted = kinds or KINDS
        upto = self._closed_at(plan.id)
        rows = self._decision_rows(db, plan.id)
        made: list[dict] = []
        if "check" in wanted:
            made += self._check_proposals(db, plan, upto)
        shown = None
        if "fix" in wanted or "plan" in wanted:
            if fixes is None:
                fixes = self._fixes(db, plan)
            if "fix" in wanted:
                made += self._fix_proposals(db, plan, fixes)
            if "plan" in wanted:
                shown = self._shown(db, plan, self._items(db, plan.id))
                # (a plan change stays when its check has passed since only where a person's decision stands on it:
                # accepted, or rejected. One that is open again after an undo is no longer proposed then, like one nobody
                # ever decided; its decisions stay on the record.)
                made += self._plan_proposals(db, plan, shown, fixes, {pid for pid, decided in rows.items() if state_of(decided) != "proposed"})
        if "dependency" in wanted:
            state = dependency_state if dependency_state is not None else self._dependency_state(db, plan)
            made += self._dependency_proposals(db, plan, state, upto)
        have = {p["id"] for p in made}
        for pid, decided in rows.items():
            if pid not in have and decided[-1].kind in wanted:
                kept = dict(decided[-1].proposal or {})
                made.append({"id": pid, "kind": decided[-1].kind, "label": LABEL, "title": kept.get("title") or "A proposal from Otto",
                             "why": kept.get("why") or "", "lines": list(kept.get("lines") or []), "about": dict(kept.get("about") or {}),
                             "proposed_at": None, "link": {"page": HOME.get(decided[-1].kind, "overview"), "item": None}, "current": False, "facts": {}})
        blocked = self._decisions_blocked(plan.id)
        order = {k: n for n, k in enumerate(KINDS)}
        made.sort(key=lambda p: order.get(p["kind"], 9))
        return [self._with_state(p, rows.get(p["id"], []), blocked) for p in made]

    def _decisions_blocked(self, plan_id: int) -> str | None:
        """Why nothing can be decided in this assessment right now, or None."""
        if self._closed_at(plan_id) is not None:
            return CLOSED
        status = harness.status()
        if not status.installed:
            return status.sentence + NO_OTTO_TAIL
        return None

    @staticmethod
    def _otto_locked(proposal: dict) -> str | None:
        """Why an accept of this proposal can no longer be undone: what it led to has run or been applied."""
        facts, kind = proposal["facts"], proposal["kind"]
        if kind == "check" and (facts.get("runs") or facts.get("live")):
            return "This check has run, so it stays in the test plan."
        if kind == "fix" and facts.get("code") and facts.get("connected"):
            return "The code is connected and the change is on its branch, so this accept stands."
        if kind == "fix" and not facts.get("code") and facts.get("retested"):
            return "A retest has run on the updated version, so this accept stands."
        if kind == "fix" and not facts.get("code") and facts.get("live"):
            return "A retest on the updated version is running, so this accept stands."
        if kind == "plan" and facts.get("done"):
            return DONE
        return None

    def _with_state(self, proposal: dict, rows: list, blocked: str | None) -> dict:
        state = state_of(rows)
        legacy = False
        if proposal["kind"] == "check" and not rows and proposal["facts"].get("in_plan"):
            state, legacy = "accepted", True         # added before decisions were recorded (an earlier version of the app)
        current = proposal["current"]
        gone = None if current else NOT_CURRENT
        actions: dict[str, str | None] = {}
        if state == "proposed":
            actions["accept"] = blocked or gone
            actions["reject"] = blocked or gone
        elif state == "accepted":
            actions["undo"] = blocked or (LEGACY if legacy else None) or gone or self._otto_locked(proposal)
        else:
            actions["reconsider"] = blocked or gone or (DONE_REJECTED if proposal["facts"].get("done") else None)
        history = [{"number": r.number, "decision": r.decision, "by": r.by, "at": r.at, "reason": r.reason, "before": r.before, "after": r.after,
                    "proposal_sha256": r.proposal_sha256, "ledger_entry": r.claim_id, "proposal": r.proposal} for r in rows]
        return {**proposal, "fingerprint": fingerprint(proposal), "state": state, "legacy": legacy, "actions": actions, "decisions": history,
                "objective_id": next((r.objective_id for r in rows if r.objective_id), None)}

    # ---------------------------------------------------------------- reading

    def otto_proposals(self, plan_id: int, kinds: tuple[str, ...] | None = None) -> list[dict]:
        with self.db() as db:
            return self._proposals(db, self._plan(db, plan_id), kinds)

    def otto_proposal(self, plan_id: int, proposal_id: str) -> dict:
        kind = _kind_of_id(proposal_id)
        for p in self.otto_proposals(plan_id, (kind,) if kind else None):
            if p["id"] == proposal_id:
                return p
        raise NotFound("That proposal is not in this assessment.")

    def otto_waiting(self, plan_id: int | None) -> dict:
        """How many of Otto's proposals in this assessment nobody has decided yet, by kind."""
        counts = {k: 0 for k in KINDS}
        if plan_id is None:
            return counts
        for p in self.otto_proposals(plan_id):
            if p["state"] == "proposed" and p["current"]:
                counts[p["kind"]] += 1
        return counts

    def otto_proposals_view(self, plan_id: int) -> dict:
        """Every proposal of Otto's in this assessment as a screen shows it, with the "Waiting for you" counts."""
        from app.present import otto as present_otto
        proposals = self.otto_proposals(plan_id)
        counts = {k: sum(1 for p in proposals if p["kind"] == k and p["state"] == "proposed" and p["current"]) for k in KINDS}
        return {"plan_id": plan_id, "waiting": present_otto.waiting_view(counts),
                "proposals": [present_otto.proposal_view(p, self.otto_ledger_about(plan_id, p.get("objective_id"))) for p in proposals],
                "blocked_reason": self._decisions_blocked(plan_id)}

    def otto_decide_view(self, plan_id: int, proposal_id: str, decision: str, reason: object = None) -> dict:
        from app.present import otto as present_otto
        p = self.otto_decide(plan_id, proposal_id, decision, reason)
        return present_otto.proposal_view(p, self.otto_ledger_about(plan_id, p.get("objective_id")))

    def otto_proposals_evidence(self, plan_id: int) -> list[dict]:
        """For the evidence file: every proposal of Otto's in this assessment, decided or not, as it stands, with every
        decision on it (what was decided, by whom, when, the reason, the copy of the proposal it was made on with its
        SHA-256, and its entry in the assessment's Otto ledger)."""
        from app.present import otto as present_otto
        out = []
        for p in self.otto_proposals(plan_id):
            shown = present_otto.proposal_view(p)
            out.append({**content(p), "label": LABEL, "proposed_at": p.get("proposed_at"), "current": bool(p["current"]),
                        "fingerprint": p["fingerprint"], "state": p["state"], "status": shown["status"]["word"], "legacy": bool(p.get("legacy")),
                        "ledger_entry": p.get("objective_id"),
                        "decisions": [{k: d[k] for k in ("number", "decision", "by", "at", "reason", "before", "after", "proposal_sha256",
                                                         "ledger_entry", "proposal")} for d in p["decisions"]]})
        return out

    def otto_project_block(self, assessments: list) -> dict:
        """The Project overview's block about Otto: for each assessment of the project, how many proposals wait for a
        decision, and what changed since the newest test pack was installed (the checks it proposed, the decisions made
        and the results recorded since). It counts what the pages already say; it decides nothing."""
        from app.present import otto as present_otto
        with self.db() as db:
            packs = self._pack_rows(db)                # type: ignore[attr-defined]
            last = packs[-1] if packs else None
            plans = {a.id: db.scalars(select(PlanRow.id).where(PlanRow.import_id == a.import_id)).first() if a.import_id else None
                     for a in assessments}
        rows = []
        for a in assessments:
            plan_id = plans.get(a.id)
            if plan_id is None:
                rows.append({"assessment": a, "waiting": {k: 0 for k in KINDS}, "since": None, "why": "No file has been brought in yet."})
                continue
            proposals = self.otto_proposals(plan_id)
            can = self._decisions_blocked(plan_id) is None
            waiting = {k: sum(1 for p in proposals if can and p["kind"] == k and p["state"] == "proposed" and p["current"]) for k in KINDS}
            since = None
            if last is not None and (a.closed_at is None or _aware(a.closed_at) >= _aware(last.installed_at)):
                brought = [p for p in proposals if p["kind"] == "check" and p["about"].get("pack") == last.version]
                with self.db() as db:
                    decided = [r for r in db.scalars(select(OttoDecisionRow).where(OttoDecisionRow.plan_id == plan_id)).all()
                               if _aware(r.created_at) >= _aware(last.installed_at)]
                    runs = db.scalars(select(TestRunRow).join(TestSpecRow, TestSpecRow.hash == TestRunRow.spec_hash)
                                      .where(TestRunRow.plan_id == plan_id, TestSpecRow.kind == research.ADVISORY_KIND)
                                      .order_by(TestRunRow.id)).all()
                    newest: dict[int, TestRunRow] = {}
                    for run in runs:
                        if _stamp_after(run.finished_at, last.installed_at):
                            newest[run.plan_item_id] = run
                    labels = [r["label"] for r in (self._result(db, run) for run in newest.values()) if r]      # type: ignore[attr-defined]
                # (the updates this pack brings for libraries of the dependency list that its advisories name)
                updates = [p for p in proposals if p["kind"] == "dependency" and p["about"].get("pack") == last.version]
                since = {"brought": {s: sum(1 for p in brought if p["state"] == s) for s in ("proposed", "accepted", "rejected")},
                         "updates": {s: sum(1 for p in updates if p["state"] == s) for s in ("proposed", "accepted", "rejected")},
                         "decisions": len(decided), "results": labels}
            rows.append({"assessment": a, "waiting": waiting, "since": since,
                         "why": None if since is not None or last is None else "It was closed before this pack was installed."})
        return present_otto.project_block(rows, {"version": last.version, "installed_at": iso(last.installed_at)} if last else None)

    def otto_result_blocks(self, db, plan: PlanRow) -> dict[int, dict]:
        """Evidence, for the results of the plan's advisory checks (by plan item): what stands behind each check. The
        advisory and the signed pack it came from, its design's fingerprint, how its test did when it was tried on
        public copies, every decision on Otto's proposal for it with who and when, and the entries of the check and of
        those decisions in the assessment's Otto ledger. It repeats records and words no result. Empty for a plan with
        no advisory check, which is every plan before a person accepted one."""
        from app.present import otto as present_otto
        checks_here = list(db.scalars(select(OttoCheckRow).where(OttoCheckRow.plan_id == plan.id).order_by(OttoCheckRow.id)).all())
        if not checks_here:
            return {}
        upto = self._closed_at(plan.id)
        proposals = {(p.get("facts") or {}).get("item_id"): p for p in self._proposals(db, plan, ("check",)) if p["current"]}
        packed = {advisory["id"]: (pack, advisory) for pack, advisory in self._pack_advisories(db, upto)}
        out: dict[int, dict] = {}
        for check in checks_here:
            found = packed.get(check.advisory_id)
            proposal = proposals.get(check.plan_item_id)
            ledger = list(self._ledger_about(plan.id, check.objective_id))      # type: ignore[attr-defined]
            if proposal is not None:
                ledger += self.otto_ledger_about(plan.id, proposal.get("objective_id"))
            ledger.sort(key=lambda e: e["seq"])
            out[check.plan_item_id] = present_otto.result_block(
                advisory_id=check.advisory_id, plain_name=((found[1]["reading"] or {}).get("plain_name") if found else None),
                pack_version=check.pack_version, design_sha256=check.design_sha256,
                trial=present_otto._trial_lines(found[1]) if found else [], ledger=ledger,
                proposal=present_otto.proposal_view(proposal) if proposal is not None else None)
        return out

    def otto_ledger_about(self, plan_id: int, objective_id: str | None) -> list[dict]:
        a = self.assessment_for(plan_id=plan_id)
        if a is None or not objective_id:
            return []
        try:
            return assurance.Ledger(self.settings.data_dir, a.id).about_proposal(objective_id)
        except harness.OttoNotInstalled:
            return []

    # ---------------------------------------------------------------- deciding

    def otto_decide(self, plan_id: int, proposal_id: str, decision: str, reason: object = None) -> dict:
        """Record one decision of a person on one of Otto's proposals: accept, reject (with an optional short reason),
        undo (of an accept, until it has run or been applied) or reconsider (of a reject). It runs nothing."""
        if decision not in DECISIONS:
            raise BadRequest("A proposal can be accepted, rejected, undone or taken up again.", field="decision")
        why = clean_reason(reason) if decision == "reject" else None
        status = harness.status()
        if not status.installed:
            raise Conflict(status.sentence + NO_OTTO_TAIL)
        a = self.assessment_for(plan_id=plan_id)
        if a is None:
            raise NotFound("That assessment does not exist.")
        if a.closed_at is not None:
            raise Conflict(CLOSED)
        ledger = assurance.Ledger(self.settings.data_dir, a.id)
        kind = _kind_of_id(proposal_id)
        with self._otto_lock, self._plan_lock, self.db() as db:
            plan = self._plan(db, plan_id)
            proposal = next((p for p in self._proposals(db, plan, (kind,) if kind else None) if p["id"] == proposal_id), None)
            if proposal is None:
                raise NotFound("That proposal is not in this assessment.")
            if decision not in proposal["actions"]:
                raise Conflict(_wrong_step(proposal["state"], decision))
            refused = proposal["actions"][decision]
            if refused:
                raise Conflict(refused)
            before, after = proposal["state"], STEPS[(proposal["state"], decision)]
            about = dict(proposal["about"])
            earlier = self._decision_rows(db, plan_id).get(proposal_id, [])
            number, at = len(earlier) + 1, now_stamp()
            by = self.decision_name()         # the name a person typed once (phase 6a), or "You"
            # Before anything is written, anywhere: the entry this decision would make, shown to the app's own pinned
            # checker. An entry it does not take is never put into the ledger, so "nothing was changed" is true.
            would_be = {"proposal": proposal_id, "proposal_kind": proposal["kind"], "proposal_sha256": proposal["fingerprint"],
                        "title": proposal["title"], "decision": decision, "before": before, "after": after, "by": by, "at": at, "reason": why,
                        "number": number, "about": about}
            if assurance.run_checker({"kind": "decision", "proposal": proposal_id, "proposal_kind": proposal["kind"]}, would_be,
                                     assurance.DECISION_CHECKER) != "accept":
                raise Conflict("The decision could not be recorded: the record checker did not take it. Nothing was changed.")
            if proposal["kind"] == "check":
                if decision == "accept":
                    about["lock_entry"] = self._accept_check(db, plan, proposal, ledger)
                elif decision == "undo":
                    self._undo_check(db, plan, proposal)
            objective = next((r.objective_id for r in earlier if r.objective_id), None)
            objective, claim, verdict = ledger.record_decision(
                objective_id=objective, proposal_id=proposal_id, kind=proposal["kind"], title=proposal["title"],
                proposal_sha256=proposal["fingerprint"], decision=decision, before=before, after=after, by=by, at=at, reason=why,
                number=number, about=about)
            if verdict != "accept":
                # The checker took this entry a moment ago and gives no answer now (it did not run in time). The ledger
                # keeps the attempt, marked as not accepted; it is no decision, and the proposal stands as it was.
                db.rollback()
                raise Conflict("The decision was not recorded: Otto's ledger could not check its entry just now. The proposal stands as "
                               "it was; the attempt stays in the ledger, marked as not accepted. Try again.")
            db.add(OttoDecisionRow(plan_id=plan_id, proposal_id=proposal_id, kind=proposal["kind"], decision=decision, before=before, after=after,
                                   number=number, reason=why, by=by, at=at, proposal=content(proposal),
                                   proposal_sha256=proposal["fingerprint"], objective_id=objective, claim_id=claim))
            db.commit()
        return self.otto_proposal(plan_id, proposal_id)

    def _accept_check(self, db, plan: PlanRow, proposal: dict, ledger) -> str:
        """Accept of a proposed check: lock the test and put it in the test plan, exactly as "+ Add test" would. Its
        lock entry goes into the assessment's Otto ledger before the check can run. Returns the lock entry's id.
        Nothing is run."""
        facts = proposal["facts"]
        found = next(((pack, advisory) for pack, advisory in self._pack_advisories(db, None)
                      if advisory["id"] == facts["advisory_id"] and pack.fingerprint == facts["pack_fingerprint"]), None)
        design = found[0].design(facts["design_sha256"]) if found is not None else None
        program = next((p for p in checks.programs_that_fit(self._claims(db.get(ImportRow, plan.import_id)))
                        if p["ref"] == facts["program_ref"]), None)
        if found is None or design is None or program is None:
            raise Conflict("That check is no longer in the installed test packs for this file, so it was not added.")
        pack, advisory = found
        item, spec_hash, _ = checks.add_design_item(self, db, plan, design, {"version": pack.version, "fingerprint": pack.fingerprint},
                                                    checks.advisory_info(advisory), program)
        row = db.scalars(select(OttoCheckRow).where(OttoCheckRow.plan_item_id == item.id)).first()
        if row is not None:
            return row.objective_id
        objective = ledger.lock_check(title=designs.title_of(design), program=program["label"], spec_hash=spec_hash,
                                      design_sha256=designs.design_sha256(design), pack_fingerprint=pack.fingerprint,
                                      pack_version=pack.version, advisory_id=advisory["id"])
        db.add(OttoCheckRow(plan_id=plan.id, plan_item_id=item.id, spec_hash=spec_hash, advisory_id=advisory["id"],
                            design_sha256=designs.design_sha256(design), pack_version=pack.version,
                            pack_fingerprint=pack.fingerprint, objective_id=objective))
        return objective

    def _undo_check(self, db, plan: PlanRow, proposal: dict) -> None:
        """Undo of an accepted check that has not run: it leaves the test plan. Its locked test and its lock entry stay
        on record (nothing is deleted), and accepting it again brings the same check back."""
        item = db.get(PlanItemRow, proposal["facts"].get("item_id")) if proposal["facts"].get("item_id") is not None else None
        if item is None or item.plan_id != plan.id:
            raise Conflict("That check is not in the test plan.")
        if db.scalar(select(func.count(TestRunRow.id)).where(TestRunRow.plan_item_id == item.id)):
            raise Conflict("This check has run, so it stays in the test plan.")
        item.removed = True

    def otto_keeps_in_plan(self, db, item_id: int) -> str | None:
        """Why a test can't be taken out of the test plan with its own remove button: it is an advisory check that came
        from an accepted proposal. Its place to be undone is Advisories, until it has run. A check that was added before
        decisions were recorded has no accept to undo there, so its own remove button works as it always did."""
        check = db.scalars(select(OttoCheckRow).where(OttoCheckRow.plan_item_id == item_id)).first()
        item = db.get(PlanItemRow, item_id) if check is not None else None
        if check is None or item is None:
            return None
        spec, _ = read_spec(db.get(TestSpecRow, item.spec_hash))
        proposal_id = check_id(check.advisory_id, check.design_sha256, str((spec.get("target") or {}).get("claim")))
        if self._otto_state(db, check.plan_id, proposal_id) != "accepted":
            return None
        return ("This check came from an accepted proposal. Until it has run, Undo on Advisories takes it out of the test plan. "
                "Once it has run, it stays.")


def _kind_of_id(proposal_id: str) -> str | None:
    head = str(proposal_id).split("-", 1)[0]
    return {"check": "check", "fix": "fix", "plan": "plan", "dep": "dependency"}.get(head)


def _wrong_step(state: str, decision: str) -> str:
    said = {"proposed": "has not been decided yet", "accepted": "is accepted", "rejected": "was rejected"}[state]
    can = {"proposed": "It can be accepted or rejected.", "accepted": "Its accept can be undone until it has run or been applied.",
           "rejected": "It can be taken up again with Reconsider."}[state]
    return f"This proposal {said}. {can}"


def _stamp_after(stamp: str | None, moment: datetime) -> bool:
    try:
        return _aware(datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))) >= _aware(moment)
    except ValueError:
        return False


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


__all__ = ["ProposalsMixin", "LABEL", "BY", "KINDS"]

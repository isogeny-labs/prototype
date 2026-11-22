"""Phase 5b: the Assessment Overview's blocks and the Project overview (every assessment side by side, what changed
between two, and which share systems). Every number is read from the page it links to, the way that page reads it;
nothing here words or decides a result. No score, no trend."""
from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import func, select

from app.db import (
    AssessmentRow, EvidenceExportRow, ImportRow, PlanRow, ProjectRow, ReviewRow, TestRunRow, VerifyRunRow, iso,
)
from app.engine import research
from app.errors import NotFound
from app.ledger import groups as G
from app.ledger.relations import migration_view_if_written

VERIFY_WORDS = ("True", "False", "Couldn't check")


def _link(page: str, group: str | None = None, item: str | None = None, assessment_id: int | None = None) -> dict:
    return {"page": page, "item": item, "group": group, "assessment_id": assessment_id}


def _tally(labels) -> list[tuple[str, int]]:
    out: dict[str, int] = {}
    for label in labels:
        if label:
            out[label] = out.get(label, 0) + 1
    return list(out.items())


class OverviewMixin:
    """Mixed into `Lab`."""

    db: Callable[..., Any]
    checks_view: Callable[[int], dict]
    fixes_view: Callable[[int], dict]
    migration_view: Callable[[int], dict]
    lab_view: Callable[[int], dict]
    dependencies_view: Callable[..., dict]
    latest_verify: Callable[[int], dict]

    # ---------------------------------------------------------------- one assessment

    def assessment_blocks(self, import_id: int | None, plan_id: int | None) -> dict | None:
        """The Overview's blocks for one assessment: one per work group, open findings, and the evidence."""
        if import_id is None:
            return None
        verify = self._verify_counts(import_id)
        if plan_id is None:
            groups = [{**G.group_frame(k), "checks": None, "fixes": None, "facts": [], "empty_text": G.EMPTY_CHECKS[k]}
                      for k in G.GROUP_KEYS]
            groups[0]["facts"] = verify["facts"]
            return {"groups": groups, "findings": self._findings(verify["false"], 0, 0), "evidence": {"runs": verify["runs"], "last_download": None}}
        checks = self.checks_view(plan_id)
        fixes = {g["key"]: g for g in self.fixes_view(plan_id)["groups"]}
        by = {g["key"]: g for g in checks["groups"]}
        groups = []
        failed = 0
        blockers = 0
        for key in G.GROUP_KEYS:
            g = by[key]
            facts: list[dict] = []
            if key == "verification":
                facts = verify["facts"]
            elif key == "encryption":
                # Each test once, by its newest result, read the way Evidence reads it (a retest's after result, else the
                # first), so the Overview, Evidence and the Project overview never disagree.
                newest = [r for r in (row.get("after") or row.get("result") for row in self.lab_view(plan_id)["rows"]) if r]
                for label, n in _tally(r["label"] for r in newest):
                    facts.append({"label": label, "value": n, "link": _link("evidence", "encryption")})
                failed = sum(1 for r in newest if r.get("code") == "failed")
            elif key == "migration":
                facts = self._track_facts(plan_id)
            elif key == "dependencies":
                libs = checks["libraries"]
                blockers = sum(len(lib["blocks"]) for lib in libs)
                if libs:
                    facts = [{"label": "Libraries", "value": len(libs), "link": _link("migration/dependencies")},
                             {"label": "Answered", "value": sum(1 for lib in libs if lib["state"] == "done"), "link": _link("migration/dependencies")},
                             {"label": "Measured", "value": sum(1 for lib in libs if lib["measured"]), "link": _link("migration/dependencies")},
                             {"label": "Blockers", "value": blockers, "link": _link("migration/dependencies")}]
            f = fixes.get(key)
            groups.append({**G.group_frame(key), "checks": g["counts"],
                           # where the group's items came from (22 November 2026), as Checks counts them
                           "source_counts": g.get("source_counts") or [],
                           "fixes": f["counts"] if f is not None and (f["fix_ids"] or key != "verification") else None,
                           "facts": facts,
                           "empty_text": None if (g["rows"] or facts) else (g["empty_text"] or G.EMPTY_CHECKS[key])})
        with self.db() as db:
            runs = db.scalar(select(func.count(ReviewRow.id)).join(TestRunRow, TestRunRow.id == ReviewRow.run_id)
                             .where(TestRunRow.plan_id == plan_id)) or 0
            last = db.scalars(select(EvidenceExportRow).where(EvidenceExportRow.plan_id == plan_id)
                              .order_by(EvidenceExportRow.id.desc()).limit(1)).first()
        blocks = {"groups": groups, "findings": self._findings(verify["false"], failed, blockers),
                  "evidence": {"runs": int(runs) + verify["runs"],
                               "last_download": {"at": iso(last.created_at), "fingerprint": last.fingerprint} if last else None}}
        # Sandbox research (prototype): one line that says how many watched weaknesses have no fix yet, and opens the
        # Watch list. Only while the switch is on and the list holds something; otherwise the Overview is as before.
        watch = self.watch_list_summary(plan_id)        # type: ignore[attr-defined]
        if watch is not None and watch["line"]:
            blocks["watch_list"] = watch
        return blocks

    def _verify_counts(self, import_id: int) -> dict:
        with self.db() as db:
            runs = db.scalars(select(VerifyRunRow).where(VerifyRunRow.import_id == import_id).order_by(VerifyRunRow.id.desc())).all()
        if not runs:
            return {"facts": [], "false": 0, "runs": 0}
        results = [r for r in runs[0].results or [] if isinstance(r, dict)]
        facts = [{"label": word, "value": sum(1 for r in results if r.get("result") == word),
                  "link": _link("inventory/verify", "verification")} for word in VERIFY_WORDS]
        return {"facts": facts, "false": facts[1]["value"], "runs": len(runs)}

    def _track_facts(self, plan_id: int) -> list[dict]:
        """How many systems stand at each status, track by track, in the Systems page's own words."""
        view = migration_view_if_written(self, plan_id)
        if view is None:
            return []                      # Migration not opened yet: nothing measured, and looking locks nothing
        systems = view["systems"]
        out = []
        tracks: dict[str, list[str]] = {}
        for s in systems:
            for t in s.get("tracks") or []:
                tracks.setdefault(t.get("short_title") or t["title"], []).append(t["status"]["label"])
        for title, labels in tracks.items():
            for label, n in _tally(labels):
                out.append({"label": f"{title}: {label}", "value": n, "link": _link("migration/roadmap", "migration")})
        return out

    @staticmethod
    def _findings(false: int, failed: int, blockers: int) -> list[dict]:
        return [{"label": "False claims", "value": false, "link": _link("inventory/verify", "verification")},
                {"label": "Failed tests", "value": failed, "link": _link("evidence", "encryption")},
                {"label": "Dependency blockers", "value": blockers, "link": _link("migration/dependencies", "dependencies")}]

    # ---------------------------------------------------------------- one project

    def _assessment_facts(self, a: AssessmentRow) -> dict:
        """What one assessment found, keyed by what each thing is, so two assessments can be compared."""
        out: dict[str, Any] = {"claims": {}, "tests": {}, "tracks": {}, "blockers": {}, "systems": {}, "has_results": False,
                               "deps_listed": False}
        if a.import_id is None:
            return out
        with self.db() as db:
            imp = db.get(ImportRow, a.import_id)
            plan = db.scalars(select(PlanRow).where(PlanRow.import_id == a.import_id)).first()
            claims = list(imp.claims) if imp is not None else []
            claim_dicts = [{"location": c.location, "location_kind": c.location_kind, "kind": c.kind, "ref": c.ref,
                            "detail": c.detail, "text": c.text, "claimed_value": c.claimed_value} for c in claims]
            plan_id = plan.id if plan is not None else None
            verify = db.scalars(select(VerifyRunRow).where(VerifyRunRow.import_id == a.import_id)
                                .order_by(VerifyRunRow.id.desc()).limit(1)).first()
        for s in research.servers(claim_dicts):
            out["systems"][s] = {"name": s, "kind": "server"}
        for p in research.programs(claim_dicts):
            out["systems"][p["label"]] = {"name": p["label"], "kind": "software"}
        if verify is not None:
            out["has_results"] = True
            for r in verify.results or []:
                if not isinstance(r, dict):
                    continue
                c = r.get("claim") or {}
                key = (c.get("location"), c.get("kind"), c.get("claimed_value"))
                out["claims"][key] = {"label": c.get("text") or "", "result": r.get("result"), "finding": r.get("result") == "False",
                                      "cleared": r.get("result") == "True",
                                      "item": f"claim-{r.get('claim_id')}", "page": "inventory/verify"}
        if plan_id is None:
            return out
        lab = self.lab_view(plan_id)
        # A result's group is named by its heading on Evidence ("Server: localhost:8443"), never by its internal key.
        headings = {g["key"]: g.get("heading") or "" for g in lab.get("groups") or []}
        for row in lab["rows"]:
            shown = row.get("after") or row.get("result")
            if not shown:
                continue
            out["has_results"] = True
            where = row.get("group") or ""
            key = (row["kind"], where, row["title"])
            heading = headings.get(where, "") if where else ""
            out["tests"][key] = {"label": f"{row['title']}" + (f" ({heading})" if heading else ""), "result": shown["label"],
                                 "finding": shown["tone"] == "fail", "cleared": shown.get("code") == "passed", "item": f"test-{row['item_id']}", "page": "evidence"}
        try:
            for s in (migration_view_if_written(self, plan_id) or {"systems": []})["systems"]:
                for t in s.get("tracks") or []:
                    if t["status"]["code"] == "not_measured":
                        continue
                    title = t.get("short_title") or t["title"]
                    out["tracks"][(s["name"], title)] = {"label": f"{s['name']} · {title}", "result": t["status"]["label"],
                                                          "item": s["key"], "page": "migration/roadmap"}
        except NotFound:
            pass
        try:
            dview = self.dependencies_view(plan_id, with_impact=False)
            out["deps_listed"] = dview.get("list_file") is not None
            for g in dview.get("groups") or []:
                for r in g.get("rows") or []:
                    for b in r.get("blocks") or []:
                        out["blockers"][(r["label"], b["system"], b["track"])] = {
                            "label": f"{r['label']} blocks {b['system']} · {b['track_words']}", "result": "Blocks",
                            "finding": True, "item": r["id"], "page": "migration/dependencies"}
        except NotFound:
            pass
        return out

    def compare_assessments(self, older: AssessmentRow, newer: AssessmentRow) -> dict:
        """What changed between two assessments of one project. It compares results; it makes none."""
        a, b = self._assessment_facts(older), self._assessment_facts(newer)

        def line(entry: dict, assessment: AssessmentRow, extra: str | None = None) -> dict:
            return {"label": entry["label"], "sub": extra or entry.get("result") or "",
                    "link": _link(entry["page"], None, entry["item"], assessment.id)}
        new, gone, moved, single = [], [], [], []
        for part in ("claims", "tests"):
            for key, entry in b[part].items():
                before = a[part].get(key)
                if entry.get("finding") and before is not None and not before.get("finding"):
                    new.append(line(entry, newer))
            for key, entry in a[part].items():
                after = b[part].get(key)
                # No longer a finding only when the newer assessment's own check says so: now True, or Passed. A finding
                # that now reads Couldn't check (or Couldn't trust this run) was not answered there, so it is listed
                # under "Not checked in both" and never counted as fixed.
                if entry.get("finding") and after is not None and not after.get("finding"):
                    if after.get("cleared"):
                        gone.append(line(after, newer, f"{entry['result']} before, {after['result']} now"))
                    else:
                        single.append(line(after, newer, f"{entry['result']} before, {after['result']} now: not answered in {self._title(newer)}"))
        # A blocker exists only as a finding: it is new when the older assessment had a dependency list without it, and
        # no longer a finding when the newer one has a list without it.
        if a["deps_listed"] and b["deps_listed"]:
            for key, entry in b["blockers"].items():
                if key not in a["blockers"]:
                    new.append(line(entry, newer))
            for key, entry in a["blockers"].items():
                if key not in b["blockers"]:
                    gone.append(line(entry, older, "Blocked before; the newer list's answer no longer blocks"))
        elif a["deps_listed"] != b["deps_listed"]:
            where, facts = (older, a) if a["deps_listed"] else (newer, b)
            single.append({"label": "The dependency list", "sub": f"Added only in {self._title(where)}",
                           "link": _link("migration/dependencies", None, None, where.id)})
        for key, entry in b["tracks"].items():
            before = a["tracks"].get(key)
            if before is not None and before["result"] != entry["result"]:
                moved.append(line(entry, newer, f"{before['result']} to {entry['result']}"))
        for part in ("claims", "tests", "tracks"):
            for key in set(a[part]) ^ set(b[part]):
                entry, where = (a[part][key], older) if key in a[part] else (b[part][key], newer)
                single.append(line(entry, where, f"Checked only in {self._title(where)}"))
        return {"from_id": older.id, "to_id": newer.id,
                "lists": [{"key": "new", "title": "New findings", "items": new},
                          {"key": "gone", "title": "No longer findings", "items": gone},
                          {"key": "moved", "title": "Tracks that moved", "items": moved},
                          {"key": "single", "title": "Not checked in both", "items": single}]}

    @staticmethod
    def _title(a: AssessmentRow) -> str:
        return a.name or f"Assessment {a.number}"

    def project_overview(self, project_id: int, from_id: int | None = None, to_id: int | None = None,
                         include_archived: bool = False) -> dict:
        with self.db() as db:
            p = db.get(ProjectRow, project_id)
            if p is None:
                raise NotFound("That project does not exist.")
            every = db.scalars(select(AssessmentRow).where(AssessmentRow.project_id == p.id).order_by(AssessmentRow.id.desc())).all()
            for a in every:
                db.expunge(a)
        shown = [a for a in every if include_archived or not a.archived]
        rows = []
        facts = {}
        for a in sorted(shown, key=lambda x: (x.closed_at is not None, -x.id)):   # open ones first, newest first
            with self.db() as db:
                brief = self._assessment_brief(db, a)   # type: ignore[attr-defined]
            facts[a.id] = self._assessment_facts(a)
            counts = self._headline(a)
            rows.append({**brief, "headline": counts, "has_results": facts[a.id]["has_results"]})
        with_results = [a for a in sorted(shown, key=lambda x: -x.id) if facts[a.id]["has_results"]]
        compare = None
        pick = {a.id: a for a in shown}
        if from_id in pick and to_id in pick and from_id != to_id:
            older, newer = sorted((pick[from_id], pick[to_id]), key=lambda x: x.id)
            compare = self.compare_assessments(older, newer)
        elif len(with_results) >= 2:
            compare = self.compare_assessments(with_results[1], with_results[0])
        shared = self._shared_systems(shown, facts)
        # Phase 5c: proposals waiting in each assessment, and what changed since the newest test pack.
        ordered = sorted(shown, key=lambda x: (x.closed_at is not None, -x.id))
        return {"id": project_id, "rows": rows, "compare": compare, "shared": shared,
                "otto": self.otto_project_block(ordered),      # type: ignore[attr-defined]
                "choices": [{"id": a.id, "title": self._title(a)} for a in sorted(shown, key=lambda x: -x.id)]}

    def _headline(self, a: AssessmentRow) -> dict:
        from app.projects.counts import assessment_counts
        counts = assessment_counts(self, a.import_id)
        blockers = None
        if a.import_id is not None:
            with self.db() as db:
                plan = db.scalars(select(PlanRow).where(PlanRow.import_id == a.import_id)).first()
            if plan is not None:
                try:
                    view = self.dependencies_view(plan.id, with_impact=False)
                    if view.get("list_file") is not None:
                        blockers = sum(len(r.get("blocks") or []) for g in view.get("groups") or [] for r in g.get("rows") or [])
                except NotFound:
                    blockers = None
        return {**counts, "blockers": blockers}

    def _shared_systems(self, shown: list[AssessmentRow], facts: dict) -> list[dict]:
        named: dict[str, list[AssessmentRow]] = {}
        kinds: dict[str, str] = {}
        for a in shown:
            for name, s in facts[a.id]["systems"].items():
                named.setdefault(name, []).append(a)
                kinds[name] = s["kind"]
        out = []
        for name, where in named.items():
            if len(where) < 2:
                continue
            note = None
            if kinds[name] == "server":
                note = self._in_force_note(name)
            out.append({"name": name, "kind": kinds[name], "assessments": [{"id": a.id, "title": self._title(a)} for a in where],
                        "note": note})
        return out

    def _in_force_note(self, address: str) -> str | None:
        with self.db() as db:
            in_force, _ = self._settings_history(db, address)   # type: ignore[attr-defined]
            if in_force is None:
                return None
            plan = db.get(PlanRow, in_force.plan_id)
            a = db.scalars(select(AssessmentRow).where(AssessmentRow.import_id == plan.import_id)).first() if plan else None
        where = self._title(a) if a is not None else "another assessment"
        return f"A change applied in {where} is in force on this server until rolled back."

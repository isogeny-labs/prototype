"""The timeline's entries: one for each thing that happened in an assessment, made from the records it keeps.

One entry for one press. The runs a press started are in its entry, each with the word its own page gives it. A retest,
a proof, a try, a watch run and a Verify run already have a record that ties their runs; a first run, a measurement and
the measurement right after an Apply are tied by the press that started them (`action_runs`), and where no press is on
record (before names were kept) each such run is listed by itself.

It reads a `Reading` and writes nothing. No result is worded here and none is decided: an entry repeats the records.
"""

from __future__ import annotations

from typing import Any

from app.fixes.changes import REVIEWERS
from app.ledger import groups as G
from app.ledger.checks import VERIFY_TONES
from app.present import changewatch as watch_words
from app.present import migration as migration_words
from app.present import record as words
from app.present import times
from app.present.watchlist import CLOCK_NAME
from app.record.reading import Reading

# Where an entry is filed when several happened at the same moment: what must come first reads first.
_ORDER = (
    "start",
    "detail",
    "import",
    "action",
    "verify",
    "list",
    "tie",
    "otto",
    "look",
    "research",
    "press",
    "run",
    "retest",
    "mark",
    "dig",
    "connect",
    "proof",
    "pr",
    "approval",
    "merge",
    "choice",
    "setting",
    "try",
    "ask",
    "okay",
    "apply",
    "rollback",
    "devchange",
    "watch",
    "stop",
    "export",
    "signoff",
)
_RUN_AREA = {
    "verification": "observe",
    "encryption": "checks",
    "migration": "migration",
    "dependencies": "dependencies",
}
_PRESS_AREA = {
    "run": "checks",
    "run_all": "checks",
    "measure_status": "migration",
    "measure_dependencies": "dependencies",
}
_OTTO_AREA = {"check": "advisories", "fix": "fixes", "plan": "migration", "dependency": "dependencies"}


def _key(entry: dict) -> tuple:
    """Newest first by when it happened. Some records keep their time to the second only (a decision on a proposal, a
    download): those are placed by the finer time of their own row or press, so two things of the same second stand in
    the order they happened. The time that is shown stays the record's own."""
    kind, _, number = entry["id"].partition("-")
    when = times.instant(entry["sort_at"] or entry["at"])
    return (
        when.timestamp() if when is not None else 0.0,
        _ORDER.index(kind) if kind in _ORDER else len(_ORDER),
        int(number) if number.isdigit() else 0,
        entry["id"],
    )


class Entries:
    """Every entry of one assessment's timeline, newest first (`all`)."""

    def __init__(self, reading: Reading) -> None:
        self.r = reading
        self.out: list[dict] = []
        self.home_of_run: dict[int, str] = {}  # which entry each run is in
        self._home = self._homes()
        for build in (
            self._assessment,
            self._file,
            self._ticks,
            self._verify,
            self._plan_changes,
            self._presses,
            self._lone_runs,
            self._retests,
            self._marks,
            self._code,
            self._proofs,
            self._pull_requests,
            self._otto,
            self._looks,
            self._system_changes,
            self._migration,
            self._dependencies,
            self._change_watch,
            self._downloads,
            self._signoff,
        ):
            build()
        self.all = sorted((e for e in self.out if e["at"]), key=_key, reverse=True)
        self.by_id = {e["id"]: e for e in self.all}

    # ---------------------------------------------------------------- helpers

    def _add(
        self,
        entry_id: str,
        at: str | None,
        area: str,
        kind: str,
        icon: str,
        sentence: tuple[str, list[dict]],
        *,
        who: dict | None = None,
        also: list[dict] | None = None,
        decided_by: str | None = None,
        marks: list[str] | None = None,
        runs: list[dict] | None = None,
        outcome: dict | None = None,
        link: dict | None = None,
        apart: bool = False,
        decision: str | None = None,
        on: str | None = None,
        by: dict | None = None,
        people: list[dict] | None = None,
        rested: list[dict] | None = None,
        after: list[dict] | None = None,
        record: list[dict] | None = None,
        about: set[str] | None = None,
        pending: int = 0,
        title: str | None = None,
        sort_at: str | None = None,
    ) -> dict:
        lead, rest = sentence
        person = who or words.nobody()
        entry = {
            "id": entry_id,
            "at": at,
            "sort_at": sort_at,
            "area": area,
            "kind": kind,
            "icon": icon,
            "lead": lead,
            "rest": rest,
            "who": person,
            "also": list(also or []),
            "decided_by": decided_by,
            "marks": list(marks or []),
            "runs": list(runs or []),
            "outcome": outcome,
            "link": link,
            "apart": apart,
            "decision": decision,
            "on": on,
            "by": by or person,
            "people": list(people or []),
            "rested": list(rested or []),
            "after": list(after or []),
            "record": list(record or []),
            "about": set(about or ()),
            "pending": pending,
            "title": title or lead.rstrip(":."),
        }
        self.out.append(entry)
        return entry

    def _pressed(self, action: dict | None) -> dict:
        """Who pressed, as a press recorded it; "Not recorded" where no press is on record."""
        if action is None:
            return words.nobody()
        return words.who(action["by"], action["by_source"], pressed=words.button(action["kind"], action["detail"]))

    def _homes(self) -> dict[str, list[dict]]:
        """Each run in the one entry it belongs to: {entry id: its runs, in the order they ran}."""
        r, homes = self.r, {}
        for run in sorted(r.runs.values(), key=lambda x: x["run_id"]):
            press = r.action_by_id.get(r.press_of_run.get(run["run_id"], -1))
            if press is not None and press["kind"] == "applied" and press["detail"].get("apply_id"):
                home = f"apply-{press['detail']['apply_id']}"
            elif press is not None and press["kind"] == "rolled_back" and press["detail"].get("rollback_id"):
                home = f"rollback-{press['detail']['rollback_id']}"
            elif run["origin"] in ("after_apply", "after_rollback"):
                home = self._after(run) or f"run-{run['run_id']}"
            elif run["phase"] == "retest":
                home = f"retest-{run['rerun']}"
            elif run["phase"] == "proof":
                home = f"proof-{run['rerun']}"
            elif run["phase"] in ("watch", "watch_base"):
                home = f"watch-{run['rerun']}"
            elif run["phase"] in ("try", "try_nginx", "try_clients"):
                home = f"try-{run['rerun']}"
            elif press is not None:
                home = f"press-{press['id']}"
            else:
                home = f"run-{run['run_id']}"
            homes.setdefault(home, []).append(run)
            self.home_of_run[run["run_id"]] = home
        return homes

    def _after(self, run: dict) -> str | None:
        """The Apply (or its Roll back) a measurement was made right after, where no press says so: the newest one of
        that change before the run."""
        when = times.instant(run["at"])
        best = None
        for apply in self.r.applies:
            if apply["change_key"] != run["change_key"]:
                continue
            if run["origin"] == "after_apply":
                at, home = apply["at"], f"apply-{apply['id']}"
            elif apply["rollback"] is not None:
                at, home = apply["rollback"]["at"], f"rollback-{apply['rollback']['id']}"
            else:
                continue
            then = times.instant(at)
            if when is not None and then is not None and then <= when:
                best = home
        return best

    def _change_title(self, key: str) -> str:
        return str(((self.r.change_history.get(key) or {}).get("change") or {}).get("title") or "A change")

    def _change_area(self, key: str) -> str:
        return "fixes" if G.group_of_change(key) == "encryption" else "migration"

    def _change_homes(self, key: str, item_id: int | None = None) -> tuple[str | None, str | None]:
        """(the fix whose box a change is acted on in, the system it changes), each None where there is none."""
        fix_id = next(
            (fid for fid, f in self.r.fix_words.items() if (f.get("change_box") or {}).get("id") == key), None
        )
        if item_id is None:
            item_id = next((t["item_id"] for t in self.r.tries if t["change_key"] == key), None)
        return fix_id, (self.r.system_of_item.get(item_id) if item_id is not None else None)

    def _change_link(self, key: str, item_id: int | None = None) -> dict:
        """Where a change lives: the migration plan's on its system (Migration plan), the server fix's in Fixes."""
        fix_id, system = self._change_homes(key, item_id)
        if self._change_area(key) == "migration" and system is not None:
            return {"page": "migration/systems", "item": system}
        if fix_id is not None:
            return {"page": "fixes", "item": fix_id}
        return {"page": "fixes" if self._change_area(key) == "fixes" else "migration/systems", "item": None}

    def _change_about(self, key: str, item_id: int | None = None) -> set[str]:
        fix_id, system = self._change_homes(key, item_id)
        return (
            {f"change:{key}"} | ({f"fix:{fix_id}"} if fix_id else set()) | ({f"system:{system}"} if system else set())
        )

    def _run_about(self, runs: list[dict]) -> set[str]:
        about = set()
        for run in runs:
            if run.get("claim_id") is not None:
                about.add(f"claim:{run['claim_id']}")
            elif run["group"] == "encryption" and run["phase"] in ("first", "retest"):
                about.add(f"test:{run['item_id']}")
            elif run.get("system_key"):
                about.add(f"system:{run['system_key']}")
            elif run.get("library_row"):
                about.add(f"library:{run['library_row']}")
        return about

    @staticmethod
    def _icon(runs: list[dict]) -> str:
        tags = {(run.get("source_tag") or {}).get("key") for run in runs}
        return "live" if tags == {"live"} else "flask"

    # ---------------------------------------------------------------- the assessment itself, and files in and out

    def _assessment(self) -> None:
        r, a = self.r, self.r.assessment
        if a is None:
            return
        started = next((x for x in r.actions if x["kind"] in ("assessment_started", "assessment_rerun")), None)
        made, brought = times.instant(a["at"]), times.instant(r.imp["at"])
        if started is None and made is not None and brought is not None and made >= brought:
            # a file brought in with no assessment named makes its own ("Imported without a project"): the same press
            started = next((x for x in r.actions if x["kind"] == "file_imported"), None)
        purpose = r.details[0]["purpose"] if r.details else None
        rerun = (
            "an earlier assessment of this project"
            if started is not None and started["kind"] == "assessment_rerun"
            else None
        )
        self._add(
            f"start-{a['id']}",
            a["at"],
            "assessment",
            "people",
            "grid",
            words.assessment_started(a["title"], purpose, rerun),
            who=self._pressed(started),
            link={"page": "overview", "item": None},
            people=[words.role("started", self._pressed(started), a["at"])],
        )
        changed = {x["detail"].get("detail_id"): x for x in r.actions if x["kind"] in ("assessment_changed", "closed")}
        for detail in r.details[1:]:
            press = changed.get(detail["id"])
            self._add(
                f"detail-{detail['id']}",
                detail["at"],
                "assessment",
                "people",
                "grid",
                words.details_changed(detail["purpose"], detail["reference"]),
                who=self._pressed(press),
                link={"page": "overview", "item": None},
                people=[words.role("changed", self._pressed(press), detail["at"])],
            )
        for press in r.actions:
            # a rename, a move or the archive leaves no other record: the press is its record
            fields = {
                k: v for k, v in (press["detail"].get("changed") or {}).items() if k not in ("purpose", "reference")
            }
            if press["kind"] != "assessment_changed" or not fields:
                continue
            self._add(
                f"action-{press['id']}",
                press["at"],
                "assessment",
                "people",
                "grid",
                words.assessment_changed(fields),
                who=self._pressed(press),
                link={"page": "overview", "item": None},
                people=[words.role("changed", self._pressed(press), press["at"])],
            )

    def _file(self) -> None:
        r, imp = self.r, self.r.imp
        press = next((x for x in r.actions if x["kind"] in ("file_imported", "assessment_rerun")), None)
        servers = len({c["location"] for c in imp["claims"] if c["location_kind"] == "server"})
        programs = len({c["location"] for c in imp["claims"] if c["location_kind"] == "software"})
        self._add(
            f"import-{imp['id']}",
            imp["at"],
            "assessment",
            "files",
            "file",
            words.file_imported(imp["filename"], len(imp["claims"]), servers, programs),
            who=self._pressed(press),
            marks=[words.DEMO_DATA] if imp["is_demo"] else [],
            link={"page": "inventory/import", "item": None},
            people=[words.role("brought_in", self._pressed(press), imp["at"])],
            record=[words.fact("File", imp["filename"]), words.fact("Format", imp["format"])],
        )

    def _downloads(self) -> None:
        for export in self.r.exports:
            press = self.r.action("evidence_downloaded", "export_id", export["id"])
            self._add(
                f"export-{export['id']}",
                export["at"],
                "assessment",
                "files",
                "download",
                words.evidence_downloaded(export["fingerprint"]),
                who=self._pressed(press),
                link={"page": "evidence", "item": None, "section": "files"},
                people=[words.role("downloaded", self._pressed(press), export["at"])],
                record=[words.fact("Fingerprint (SHA-256)", export["fingerprint"])],
                sort_at=press["at"] if press is not None else None,  # (a download's own time is kept to the second)
            )

    def _signoff(self) -> None:
        r, signed = self.r, self.r.signoff
        if signed is None or r.assessment is None:
            return
        press = next((x for x in r.actions if x["kind"] == "closed"), None)
        name = words.who(signed["by"], "signoff")
        people = [words.role("signed_off", name, signed["at"])]
        if press is not None:
            people.append(words.role("pressed", self._pressed(press), press["at"]))
        self._add(
            f"signoff-{signed['id']}",
            signed["at"],
            "assessment",
            "people",
            "signoff",
            words.closed(signed["by"], signed["note"]),
            who=name,
            also=[self._pressed(press)] if press is not None else [],
            link={"page": "overview", "item": None},
            decision="signed_off",
            on=r.assessment["title"],
            people=people,
        )

    # ---------------------------------------------------------------- "I own this system", and Verify

    def _ticks(self) -> None:
        r = self.r
        for press in r.actions:
            if press["kind"] not in ("address_confirmed", "address_unconfirmed"):
                continue
            detail = press["detail"]
            address, on, confirmed = (
                str(detail.get("address")),
                press["kind"] == "address_confirmed",
                bool(detail.get("confirmed")),
            )
            about = {f"system:server:{address}"} | {
                f"claim:{c['id']}" for c in r.imp["claims"] if c["location"] == address
            }
            self._add(
                f"action-{press['id']}",
                press["at"],
                "observe",
                "people",
                "person",
                words.address_ticked(address, on, confirmed),
                who=self._pressed(press),
                link={"page": "inventory/import", "item": None},
                decision=("confirmed" if confirmed else None) if on else "unconfirmed",
                on=f"“I own this system” for {address}",
                people=[words.role("ticked", self._pressed(press), press["at"])],
                record=[
                    words.fact("Address", address),
                    words.fact("Looked up as", detail.get("resolved_ip") or "not looked up"),
                ],
                about=about,
            )

    def _verify(self) -> None:
        for run in self.r.verify_runs:
            results = [res for res in run["results"] if isinstance(res, dict)]
            runs = [
                {
                    "run_id": None,
                    "verify_run_id": run["id"],
                    "claim_id": res.get("claim_id"),
                    "item_id": None,
                    "phase": "verify",
                    "group": "verification",
                    "name": (res.get("claim") or {}).get("text") or "",
                    "ran_on": (res.get("claim") or {}).get("location") or "",
                    "label": res.get("result"),
                    "tone": VERIFY_TONES.get(res.get("result", ""), "warn"),
                    "source_tag": res.get("source_tag"),
                    "at": run["finished_at"],
                    "fingerprint": None,
                    "link": {"page": "inventory/verify", "item": f"claim-{res.get('claim_id')}"},
                }
                for res in results
            ]
            press = self.r.action("verify", "verify_run_id", run["id"])
            self._add(
                f"verify-{run['id']}",
                run["started_at"],
                "observe",
                "runs",
                self._icon(runs),
                words.verify_ran(len(runs)),
                who=self._pressed(press),
                decided_by=words.BY_RULES,
                runs=runs,
                link={"page": "inventory/verify", "item": None},
                people=[words.role("started", self._pressed(press), run["started_at"])],
                about=self._run_about(runs),
            )

    # ---------------------------------------------------------------- the test plan, its runs and its retests

    def _plan_changes(self) -> None:
        r = self.r
        for press in r.actions:
            detail = press["detail"]
            if press["kind"] == "test_added":
                ids = [*detail.get("added", []), *detail.get("back", [])]
                sentence = words.test_added(
                    [r.items[i]["title"] for i in ids if i in r.items], len(detail.get("back", []))
                )
            elif press["kind"] == "test_removed":
                ids = list(detail.get("removed", []))
                sentence = words.test_removed(next((r.items[i]["title"] for i in ids if i in r.items), None))
            elif press["kind"] == "tests_reordered":
                ids = list(detail.get("order", []))
                sentence = words.tests_reordered([r.items[i]["title"] for i in ids if i in r.items])
            else:
                continue
            self._add(
                f"action-{press['id']}",
                press["at"],
                "checks",
                "people",
                "list",
                sentence,
                who=self._pressed(press),
                link={"page": "checks", "item": None},
                people=[words.role("changed", self._pressed(press), press["at"])],
                about={f"test:{i}" for i in ids} if press["kind"] != "tests_reordered" else set(),
            )

    def _presses(self) -> None:
        r = self.r
        for press in r.actions:
            if press["kind"] not in _PRESS_AREA:
                continue
            runs = self._home.get(f"press-{press['id']}", [])
            queued = list(press["detail"].get("items") or [])
            title = r.items[queued[0]]["title"] if press["kind"] == "run" and queued and queued[0] in r.items else None
            link = {
                "run": {"page": "evidence", "item": f"test-{queued[0]}" if queued else None},
                "run_all": {"page": "checks", "item": None},
                "measure_status": {"page": "migration/systems", "item": None},
                "measure_dependencies": {"page": "migration/dependencies", "item": None},
            }[press["kind"]]
            self._add(
                f"press-{press['id']}",
                press["at"],
                _PRESS_AREA[press["kind"]],
                "runs",
                self._icon(runs),
                words.ran(press["kind"], len(queued) or len(runs), title),
                who=self._pressed(press),
                decided_by=words.BY_REVIEWER,
                runs=runs,
                link=link,
                people=[words.role("started", self._pressed(press), press["at"])],
                about=self._run_about(runs),
                pending=max(0, len(queued) - len(runs)) if r.busy else 0,
            )

    def _lone_runs(self) -> None:
        for home, runs in self._home.items():
            if not home.startswith("run-"):
                continue
            run = runs[0]
            self._add(
                home,
                run["at"],
                _RUN_AREA.get(run["group"], "checks"),
                "runs",
                self._icon(runs),
                words.ran_alone(run["name"], run["ran_on"], run["origin_label"]),
                decided_by=words.BY_REVIEWER,
                runs=runs,
                link=run["link"],
                people=[words.role("started", words.nobody(), None)],
                about=self._run_about(runs),
            )

    def _retests(self) -> None:
        r = self.r
        for retest in r.retests:
            runs = self._home.get(f"retest-{retest['id']}", [])
            press = r.action(("retest", "retest_now"), "retest_id", retest["id"])
            now = press is not None and press["kind"] == "retest_now"
            name = " ".join(str(x) for x in (retest["component"], retest["version"]) if x)
            queued = len((press or {}).get("detail", {}).get("items") or []) or len(runs)
            about = self._run_about(runs)
            if now and press is not None and press["item"]:
                about.add(press["item"])
            self._add(
                f"retest-{retest['id']}",
                retest["at"],
                "checks",
                "runs",
                self._icon(runs),
                words.retested(name, queued, now),
                who=self._pressed(press),
                decided_by=words.BY_REVIEWER,
                runs=runs,
                link={"page": "evidence", "item": None},
                people=[words.role("started", self._pressed(press), retest["at"])],
                record=[words.fact("From version", retest["baseline"]), words.fact("To version", retest["version"])],
                about=about,
                pending=max(0, queued - len(runs)) if r.busy else 0,
                title=f"Retest on {name}",
            )

    def _marks(self) -> None:
        r = self.r
        for kind, rows in (("mark", r.marks), ("dig", r.digs)):
            for row in rows:
                run = r.runs.get(row["run_id"])
                if run is None:
                    continue
                press = next(
                    (
                        x
                        for x in r.actions
                        if x["kind"] == ("marked_reviewed" if kind == "mark" else "dig_deeper")
                        and x["item"] == f"run:{row['run_id']}"
                    ),
                    None,
                )
                sentence = (
                    words.marked_reviewed(run["name"], run["ran_on"], run["label"])
                    if kind == "mark"
                    else words.asked_to_dig(run["name"], run["ran_on"])
                )
                self._add(
                    f"{kind}-{row['id']}",
                    row["at"],
                    _RUN_AREA.get(run["group"], "checks"),
                    "people",
                    "person",
                    sentence,
                    who=self._pressed(press),
                    link=run["link"],
                    decision="marked_reviewed" if kind == "mark" else None,
                    on=f"{run['name']} on {run['ran_on']}: {run['label']}" if kind == "mark" else None,
                    people=[words.role("marked" if kind == "mark" else "asked", self._pressed(press), row["at"])],
                    record=[words.fact("Run fingerprint (SHA-256)", run["fingerprint"])]
                    if run.get("fingerprint")
                    else [],
                    about=self._run_about([run]),
                )

    # ---------------------------------------------------------------- Fixes: a code change, from Connect to the merge

    def _fix_of_change(self, change_id: int | None) -> dict | None:
        return self.r.changes.get(change_id) if change_id is not None else None

    def _code(self) -> None:
        r, connection = self.r, self.r.connection
        if connection is None:
            return
        press = r.action("code_connected", "connection_id", connection["id"])
        change = next(iter(r.changes.values()), None)
        self._add(
            f"connect-{connection['id']}",
            connection["at"],
            "fixes",
            "people",
            "person",
            words.code_connected(connection["repository"], connection["branch"], change["title"] if change else None),
            who=self._pressed(press),
            marks=[words.FROM_OTTO] if change is not None and change["written_by"] == "otto" else [],
            link={"page": "fixes", "item": change["fix_id"] if change else None},
            people=[words.role("connected", self._pressed(press), connection["at"])],
            record=[
                words.fact("Repository", connection["repository"]),
                words.fact("Branch", connection["branch"]),
                words.fact("Commit it was connected at", connection["base_commit"]),
                *([words.fact("The change's commit", change["head_commit"])] if change else []),
            ],
            about={f"fix:{change['fix_id']}"} if change else set(),
        )

    def _proofs(self) -> None:
        r = self.r
        for proof in r.proofs:
            change = self._fix_of_change(proof["change_id"])
            runs = self._home.get(f"proof-{proof['id']}", [])
            press = r.action(("code_connected", "proof_started"), "proof_id", proof["id"])
            name = " ".join(str(x) for x in (r.plan["component"], proof["version"]) if x)
            self._add(
                f"proof-{proof['id']}",
                proof["at"],
                "fixes",
                "runs",
                "flask",
                words.proof_ran(name, proof["tests"]),
                who=self._pressed(press),
                decided_by=words.BY_REVIEWER,
                runs=runs,
                outcome=words.badge(words.PROOF_WORDS.get(proof["state"])),
                link={"page": "fixes", "item": change["fix_id"] if change else None, "section": "proof"},
                people=[words.role("started", self._pressed(press), proof["at"])],
                record=[
                    words.fact("Proof", proof["id"]),
                    *(
                        [words.fact("Proof record fingerprint (SHA-256)", proof["record_sha256"])]
                        if proof["record_sha256"]
                        else []
                    ),
                ],
                about={f"fix:{change['fix_id']}"} if change else set(),
                pending=max(0, proof["tests"] - len(runs)) if r.busy and proof["state"] == "running" else 0,
                title=f"Proof on {name}",
            )

    def _pull_requests(self) -> None:
        r = self.r
        for pr in r.pull_requests.values():
            change = self._fix_of_change(pr["change_id"])
            fix_id = change["fix_id"] if change else None
            link, about = {"page": "fixes", "item": fix_id}, ({f"fix:{fix_id}"} if fix_id else set())
            on = f"Pull request #{pr['number']}: {pr['title']}"
            opened = r.action("pull_request_opened", "pull_request_id", pr["id"])
            self._add(
                f"pr-{pr['id']}",
                pr["at"],
                "fixes",
                "people",
                "person",
                words.pull_request_opened(pr["number"], pr["title"], [REVIEWERS.get(x, x) for x in pr["reviewers"]]),
                who=self._pressed(opened),
                link=link,
                people=[words.role("opened", self._pressed(opened), pr["at"])],
                about=about,
            )
            approvals = []
            for approval in pr["approvals"]:
                press = r.action("approved", "approval_id", approval["id"])
                demo = approval["reviewer"] != "you"
                named = words.who(approval["name"], "reviewer", demo=demo)
                pressed = self._pressed(press)
                approvals.append((approval, named, pressed))
                self._add(
                    f"approval-{approval['id']}",
                    approval["at"],
                    "fixes",
                    "people",
                    "approve",
                    words.approved(pr["number"]),
                    who=pressed if press is not None else named,
                    also=[named] if press is not None and demo else [],
                    marks=[words.DEMO_DATA] if demo else [],
                    link=link,
                    decision="approved",
                    on=on,
                    by=named if demo or press is None else pressed,
                    people=self._approved_by(approval, named, pressed, press is not None),
                    about=about,
                )
            merge = pr["merge"]
            if merge is None:
                continue
            press = r.action("merged", "merge_id", merge["id"])
            people = [words.role("merged", self._pressed(press), merge["at"], words.MERGE_NOTE)]
            for approval, named, pressed in approvals:
                people += self._approved_by(approval, named, pressed, pressed["recorded"])
            self._add(
                f"merge-{merge['id']}",
                merge["at"],
                "fixes",
                "people",
                "merge",
                words.merged(pr["number"], r.connection["branch"] if r.connection else "main", merge["commit"]),
                who=self._pressed(press),
                link=link,
                decision="merged",
                on=on,
                people=people,
                rested=self._merge_rested(pr, change),
                after=self._merge_after(change, merge["at"]),
                record=[
                    *(
                        [
                            words.fact("Repository", r.connection["repository"]),
                            words.fact("Branch", r.connection["branch"]),
                        ]
                        if r.connection
                        else []
                    ),
                    words.fact("Merge commit", merge["commit"]),
                    *(
                        [
                            words.fact("The change's commit", change["head_commit"]),
                            words.fact("The commit it starts from", change["base_commit"]),
                        ]
                        if change
                        else []
                    ),
                    words.fact("Pull request", f"#{pr['number']}"),
                    words.fact("Proof", pr["proof_id"]),
                ],
                about=about,
                title=f"Merged pull request #{pr['number']}",
            )

    @staticmethod
    def _approved_by(approval: dict, named: dict, pressed: dict, has_press: bool) -> list[dict]:
        """The Who lines of one approval: the name it was given under and, where a press is on record, who pressed."""
        if approval["reviewer"] == "you":
            return [words.role("approved", pressed if has_press else named, approval["at"])]
        lines = [words.role("approved_as", named, approval["at"], words.ONE_LOGIN_NOTE)]
        if has_press:
            lines.append(words.role("pressed", pressed, approval["at"]))
        return lines

    def _chips(self, runs: list[dict]) -> list[dict]:
        return [words.chip(run["label"], run["tone"], run["name"]) for run in runs]

    def _merge_rested(self, pr: dict, change: dict | None) -> list[dict]:
        """What a merge rested on: the proof its pull request was opened on, and the failed results the fix answers."""
        r, out = self.r, []
        proof = next((p for p in r.proofs if p["id"] == pr["proof_id"]), None)
        fix_id = change["fix_id"] if change else None
        if proof is not None:
            name = " ".join(str(x) for x in (r.plan["component"], proof["version"]) if x)
            chips = [c for c in [words.badge(words.PROOF_WORDS.get(proof["state"]))] if c]
            out.append(
                words.rested(
                    f"Proof on {name}",
                    f"{words.PROOF_RESTED} {words.BY_REVIEWER[0].upper()}{words.BY_REVIEWER[1:]}.",
                    [words.chip(c["label"], c["tone"]) for c in chips],
                    {"page": "fixes", "item": fix_id, "section": "proof"},
                    words.OPEN_THE_PROOF,
                )
            )
        answered = [r.runs[a["run_id"]] for a in (change or {}).get("runs") or [] if a.get("run_id") in r.runs]
        if answered:
            out.append(
                words.rested(
                    words.findings_title(len(answered)),
                    words.FINDINGS_TEXT,
                    self._chips(answered),
                    {"page": "evidence", "item": None},
                    words.OPEN_IN_RESULTS,
                )
            )
        return out

    def _merge_after(self, change: dict | None, merged_at: str) -> list[dict]:
        """What came after a merge: each retest started after it, with the words of the tests the fix answers."""
        r, out = self.r, []
        then = times.instant(merged_at)
        answers = {a.get("item_id") for a in (change or {}).get("runs") or []}
        for retest in r.retests:
            when = times.instant(retest["at"])
            if then is None or when is None or when < then:
                continue
            runs = [run for run in self._home.get(f"retest-{retest['id']}", []) if run["item_id"] in answers]
            name = " ".join(str(x) for x in (retest["component"], retest["version"]) if x)
            out.append(
                words.rested(
                    f"Retest on {name}",
                    words.RETEST_AFTER,
                    self._chips(runs),
                    {"page": "evidence", "item": None},
                    words.OPEN_IN_RESULTS,
                )
            )
        return out

    # ---------------------------------------------------------------- Otto's proposals, looks and research runs

    def _otto(self) -> None:
        for d in self.r.otto_decisions:
            about_of = d["about"]
            link = {
                "check": {"page": "advisories", "item": about_of.get("advisory")},
                "fix": {"page": "fixes", "item": about_of.get("fix")},
                "plan": {"page": "migration/systems", "item": about_of.get("system")},
                "dependency": {"page": "migration/dependencies", "item": None},
            }.get(d["kind"], {"page": "advisories", "item": None})
            about = {f"proposal:{d['proposal']}"}
            for key, prefix in (("advisory", "advisory:"), ("fix", "fix:"), ("system", "system:")):
                if about_of.get(key):
                    about.add(prefix + str(about_of[key]))
            named = words.who(d["by"], "decides")
            self._add(
                f"otto-{d['id']}",
                d["at"],
                _OTTO_AREA.get(d["kind"], "advisories"),
                "people",
                "person",
                words.otto_decided(d["kind"], d["title"], d["decision"], d["reason"]),
                who=named,
                marks=[words.FROM_OTTO],
                link=link,
                decision=d["decision"],
                on=words.otto_on(d["kind"], d["title"], d["decision"], d["reason"]),
                people=[words.role("decided", named, d["at"])],
                record=[words.fact("Proposal", d["proposal"])],
                about=about,
                title=f"{words.OTTO_DECISIONS[d['decision']]}: {words.OTTO_WHAT.get(d['kind'], words.OTTO_PROPOSAL)}",
                sort_at=d["made"],
            )

    def _looks(self) -> None:
        for look in self.r.lookups:
            named = words.who(look["by"], "clock" if look["by"] == CLOCK_NAME else "decides")
            self._add(
                f"look-{look['id']}",
                look["at"],
                "advisories",
                "people",
                "clock" if look["by"] == CLOCK_NAME else "person",
                words.looked(look["libraries"], len(look["advisories"]), look["source"]),
                who=named,
                link={"page": "advisories", "item": None},
                people=[words.role("looked", named, look["at"])],
                about={f"advisory:{a}" for a in look["advisories"]},
                sort_at=look["made"],
            )
        for run in self.r.research.values():
            named = (
                words.who(run["by"], "clock" if run["by"] == CLOCK_NAME else "decides") if run["by"] else words.nobody()
            )
            self._add(
                f"research-{run['key']}",
                run["at"],
                "advisories",
                "runs",
                "flask",
                words.research_ran(len(run["advisories"]), run["ended"], run["pack"]),
                who=named,
                marks=[words.FROM_OTTO],
                link={"page": "advisories", "item": None},
                people=[words.role("started", named, run["at"])],
                about={f"advisory:{a}" for a in run["advisories"]},
                sort_at=run["made"],
            )

    # ---------------------------------------------------------------- a change to a system

    def _system_changes(self) -> None:
        r = self.r
        tries = {t["id"]: t for t in r.tries}
        for tried in r.tries:
            key = tried["change_key"]
            runs = self._home.get(f"try-{tried['id']}", [])
            press = r.action("change_tried", "try_id", tried["id"])
            self._add(
                f"try-{tried['id']}",
                tried["at"],
                self._change_area(key),
                "runs",
                "flask",
                words.change_tried(tried["title"]),
                who=self._pressed(press),
                decided_by=words.BY_REVIEWER,
                runs=runs,
                outcome=words.badge(words.TRY_WORDS.get(str(tried["outcome"]))),
                link=self._change_link(key, tried["item_id"]),
                people=[words.role("tried", self._pressed(press), tried["at"])],
                record=[words.fact("Change fingerprint (SHA-256)", tried["change_fp"])],
                about=self._change_about(key, tried["item_id"]),
                title="Try on a test copy",
            )
        requests = {q["id"]: q for q in r.requests}
        for request in r.requests:
            key, title = request["change_key"], self._change_title(request["change_key"])
            link, about = self._change_link(key), self._change_about(key)
            press = r.action("approval_asked", "request_id", request["id"])
            self._add(
                f"ask-{request['id']}",
                request["at"],
                self._change_area(key),
                "people",
                "person",
                words.approval_asked(title, [REVIEWERS.get(x, x) for x in request["reviewers"]]),
                who=self._pressed(press),
                link=link,
                people=[words.role("asked", self._pressed(press), request["at"])],
                about=about,
            )
            for approval in request["approvals"]:
                okay = r.action("change_approved", "apply_approval_id", approval["id"])
                demo = approval["reviewer"] != "you"
                named, pressed = words.who(approval["name"], "reviewer", demo=demo), self._pressed(okay)
                self._add(
                    f"okay-{approval['id']}",
                    approval["at"],
                    self._change_area(key),
                    "people",
                    "approve",
                    words.change_approved(title),
                    who=pressed if okay is not None else named,
                    also=[named] if okay is not None and demo else [],
                    marks=[words.DEMO_DATA] if demo else [],
                    link=link,
                    decision="approved",
                    on=f"The change: {title}",
                    by=named if demo or okay is None else pressed,
                    people=self._approved_by(approval, named, pressed, okay is not None),
                    about=about,
                )
        for apply in r.applies:
            key = apply["change_key"]
            tried = tries.get(apply["try_id"])
            title = tried["title"] if tried else self._change_title(key)
            link, about = (
                self._change_link(key, tried["item_id"] if tried else None),
                self._change_about(key, tried["item_id"] if tried else None),
            )
            press = r.action("applied", "apply_id", apply["id"])
            runs = self._home.get(f"apply-{apply['id']}", [])
            request = requests.get(apply["request_id"])
            people = [words.role("applied", self._pressed(press), apply["at"])]
            rested = []
            if tried is not None:
                chips = [c for c in [words.badge(words.TRY_WORDS.get(str(tried["outcome"])))] if c]
                rested.append(
                    words.rested(
                        "Try on a test copy",
                        words.TRY_RESTED,
                        [words.chip(c["label"], c["tone"]) for c in chips],
                        link,
                        words.OPEN_THE_CHANGE,
                    )
                )
            if request is not None:
                for approval in request["approvals"]:
                    okay = r.action("change_approved", "apply_approval_id", approval["id"])
                    named = words.who(approval["name"], "reviewer", demo=approval["reviewer"] != "you")
                    people += self._approved_by(approval, named, self._pressed(okay), okay is not None)
                rested.append(
                    words.rested(
                        words.APPROVALS_TITLE,
                        words.approvals_text(
                            [a["name"] for a in request["approvals"]],
                            [REVIEWERS.get(x, x) for x in request["reviewers"]],
                        ),
                        [],
                        link,
                        words.OPEN_THE_CHANGE,
                    )
                )
            self._add(
                f"apply-{apply['id']}",
                apply["at"],
                self._change_area(key),
                "system",
                "apply",
                words.applied(title, apply["address"], apply["accepted"]),
                who=self._pressed(press),
                decided_by=words.BY_REVIEWER if runs else None,
                runs=runs,
                link=link,
                decision="applied",
                on=f"{title}, on {apply['address']}",
                people=people,
                rested=rested,
                after=[self._measured_after(runs, words.AFTER_APPLY, link)],
                record=[
                    words.fact("Change fingerprint (SHA-256)", apply["change_fp"]),
                    words.fact("Server", apply["address"]),
                ],
                about=about,
            )
            back = apply["rollback"]
            if back is None:
                continue
            undo = r.action("rolled_back", "rollback_id", back["id"])
            again = self._home.get(f"rollback-{back['id']}", [])
            self._add(
                f"rollback-{back['id']}",
                back["at"],
                self._change_area(key),
                "system",
                "rollback",
                words.rolled_back(title, apply["address"], back["accepted"]),
                who=self._pressed(undo),
                decided_by=words.BY_REVIEWER if again else None,
                runs=again,
                link=link,
                decision="rolled_back",
                on=f"{title}, on {apply['address']}",
                people=[words.role("rolled_back", self._pressed(undo), back["at"])],
                after=[self._measured_after(again, words.AFTER_ROLLBACK, link)],
                record=[
                    words.fact("Change fingerprint (SHA-256)", apply["change_fp"]),
                    words.fact("Server", apply["address"]),
                ],
                about=about,
            )

    def _measured_after(self, runs: list[dict], title: str, link: dict) -> dict:
        return words.rested(
            title,
            words.MEASURED_AFTER if runs else words.NOT_MEASURED_AFTER,
            self._chips(runs),
            link,
            words.OPEN_THE_CHANGE,
        )

    # ---------------------------------------------------------------- the migration plan and the dependency list

    def _system_name(self, key: str) -> str:
        return self.r.system_names.get(key) or key.split(":", 1)[-1]

    def _migration(self) -> None:
        r = self.r
        for choice in r.choices:
            system = self._system_name(choice["system"])
            titles = (
                migration_words.OPTION_TITLES
                if choice["system"].startswith("server:")
                else migration_words.PROGRAM_OPTION_TITLES
            )
            option = titles.get(choice["option"], choice["option"])
            press = r.action("option_chosen", "choice_id", choice["id"])
            self._add(
                f"choice-{choice['id']}",
                choice["at"],
                "migration",
                "people",
                "person",
                words.option_chosen(option, system, choice["reason"], choice["review_date"]),
                who=self._pressed(press),
                link={"page": "migration/systems", "item": choice["system"]},
                decision="chose",
                on=f"{option}, for {system}",
                people=[words.role("chose", self._pressed(press), choice["at"])],
                about={f"system:{choice['system']}"},
            )
        for setting in r.settings:
            system = self._system_name(setting["system"])
            field = migration_words.FIELD_LABELS.get(setting["field"], setting["field"])
            value = migration_words.VALUE_LABELS.get(setting["field"], {}).get(setting["value"], setting["value"])
            press = r.action("setting_changed", "setting_id", setting["id"])
            self._add(
                f"setting-{setting['id']}",
                setting["at"],
                "migration",
                "people",
                "person",
                words.setting_changed(system, field, value),
                who=self._pressed(press),
                link={"page": "migration/systems", "item": setting["system"]},
                decision="setting",
                on=f"{system}: {field.rstrip('?')} is {value}",
                people=[words.role("changed", self._pressed(press), setting["at"])],
                about={f"system:{setting['system']}"},
            )

    def _dependencies(self) -> None:
        r = self.r
        for listed in r.lists:
            press = r.action("dependency_list_added", "list_id", listed["id"])
            self._add(
                f"list-{listed['id']}",
                listed["at"],
                "dependencies",
                "files",
                "file",
                words.dependency_list_added(listed["filename"], listed["libraries"], listed["format"]),
                who=self._pressed(press),
                link={"page": "migration/dependencies", "item": None},
                people=[words.role("brought_in", self._pressed(press), listed["at"])],
                record=[words.fact("File", listed["filename"]), words.fact("Fingerprint (SHA-256)", listed["sha256"])],
            )
        for tie in r.ties:
            system = self._system_name(tie["system"]) if tie["system"] else None
            press = r.action("library_tied", "tie_id", tie["id"])
            self._add(
                f"tie-{tie['id']}",
                tie["at"],
                "dependencies",
                "people",
                "person",
                words.library_tied(tie["top"], system),
                who=self._pressed(press),
                link={"page": "migration/dependencies", "item": None},
                decision="tied",
                on=f"{tie['top']}: part of {system}" if system else f"{tie['top']}: part of none of these systems",
                people=[words.role("chose", self._pressed(press), tie["at"])],
                about={f"system:{tie['system']}"} if tie["system"] else set(),
            )

    # ---------------------------------------------------------------- Change watch (kept apart) and the Watch list

    def _change_watch(self) -> None:
        r = self.r
        for change in r.watch.get("changes") or []:
            if not change.get("when"):
                continue
            press = next(
                (
                    x
                    for x in r.actions
                    if x["kind"] == "demo_change_brought_in" and x["detail"].get("commit") == change["head"]
                ),
                None,
            )
            demo = bool(change.get("is_demo"))
            author = words.who(change.get("author") or "The commit names no author", "author", demo=demo)
            people = [words.role("author", author, change["when"])]
            if press is not None:
                people.append(words.role("brought_in", self._pressed(press), press["at"]))
            self._add(
                f"devchange-{change['id']}",
                change["when"],
                "watch",
                "files",
                "file",
                words.developer_change(change["title"], change["branch"], change["head"]),
                who=self._pressed(press) if press is not None else author,
                also=[author] if press is not None else [],
                marks=[words.DEMO_DATA] if demo else [],
                link={"page": "change-watch", "item": change["id"]},
                apart=True,
                people=people,
                record=[words.fact("Branch", change["branch"]), words.fact("Commit", change["head"])],
                about={f"developer-change:{change['id']}"},
            )
        for watch in r.watch_runs:
            runs = self._home.get(f"watch-{watch['id']}", [])
            press = r.action("picked_tests_run", "watch_run_id", watch["id"])
            status = watch["status"]
            change_id = f"change-{watch['head_commit'][:12]}"
            self._add(
                f"watch-{watch['id']}",
                watch["at"],
                "watch",
                "runs",
                "flask",
                words.picked_tests_ran(watch["tests"], watch["branch"], watch["head_commit"]),
                who=self._pressed(press),
                decided_by=words.BY_REVIEWER,
                runs=runs,
                outcome=(
                    {"label": watch_words.STATUS_WORDS[status], "tone": watch_words.STATUS_TONES[status]}
                    if status in watch_words.STATUS_WORDS
                    else None
                ),
                link={"page": "change-watch", "item": change_id},
                apart=True,
                people=[words.role("started", self._pressed(press), watch["at"])],
                record=[
                    words.fact("Branch", watch["branch"]),
                    words.fact("The change's commit", watch["head_commit"]),
                    words.fact("The commit it starts from", watch["base_commit"]),
                    *(
                        [words.fact("Watch record fingerprint (SHA-256)", watch["record_sha256"])]
                        if watch["record_sha256"]
                        else []
                    ),
                ],
                about={f"developer-change:{change_id}"},
                title="Run the picked tests",
            )
        for mark in r.watch_marks:
            named = words.who(mark["by"], "decides")
            self._add(
                f"stop-{mark['id']}",
                mark["at"],
                "watch",
                "people",
                "person",
                words.watch_marked(mark["kind"], mark["item"], mark["reason"]),
                who=named,
                link={"page": "change-watch", "item": None, "section": "watch-list"},
                decision="stop" if mark["kind"] == "stop" else "watch",
                on=str(mark["item"]) + (f". Reason: {mark['reason']}" if mark["reason"] else ""),
                sort_at=mark["made"],
                people=[words.role("decided", named, mark["at"])],
            )


def entries(lab: Any, plan_id: int) -> Entries:
    """The timeline of one plan, read now from its records."""
    return Entries(Reading(lab, plan_id))


__all__ = ["Entries", "entries"]

"""Where it is used (change impact, phase 4e, first half). Mixed into Lab.

For one part that a change touches (a server, a signing program, or a library at one version), every system of the
person's that reaches it, so they know what to check again after the change:

  - in this assessment, from its scanner file: the server or signing program itself;
  - in this assessment, from its newest dependency list: the component itself, and every top entry (the customer's own
    software) that reaches it by any path, with that path and the system the top entry is tied to;
  - elsewhere in the organization: every other assessment whose scanner file or newest dependency list names the same
    thing, leaving out archived assessments, archived projects and projects in an archived folder. A closed
    assessment reads only its own file and list, so what it shows no longer changes with other assessments.

"The same thing" (each line says which rule matched):
  - a server: the same address;
  - a library with a package address on both sides: the same package address and the same version;
  - otherwise a library the knowledge base recognises on both sides (the way Dependencies recognises one): the same
    library and the same version;
  - otherwise, only when the knowledge base recognises neither side: the same name and the same version text, capital
    letters ignored (the rule that ties a dependency entry to a signing program: "1.4.3-otto" is not "1.4.3").
A library's version is compared as the app reads versions (knowledge/versions.py: a distribution's package is read as
its upstream version); one it can't read matches only the same text.

It reads the scanner files, the dependency lists and the knowledge base. It runs nothing, writes nothing and decides
nothing: no result, no status and no count anywhere else changes because of it. What each fix is about is read from
the fix as Fixes already has it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select

from app.db import AssessmentRow, DependencyListRow, FolderRow, ImportRow, PlanRow, ProjectRow
from app.dependencies.tree import build_tree, from_store, label, reached_from, top_keys
from app.engine import research
from app.knowledge.base import knowledge_base, purl_base
from app.knowledge.versions import key as version_key, read_version

SERVER, SOFTWARE = "server", "software"


@dataclass(frozen=True)
class Part:
    """What a change touches. kind "server" (address) or "software" (name and version, with its package address
    when it has one). `library` is the knowledge base's id when the knowledge base recognises it."""

    kind: str
    address: str | None = None
    name: str | None = None
    version: str | None = None
    purl: str | None = None
    library: str | None = None
    roles: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        if self.kind == SERVER:
            return str(self.address)
        return f"{self.name} {self.version}".strip() if self.version else str(self.name)


def server_part(address: str) -> Part:
    return Part(kind=SERVER, address=str(address))


def software_part(name: str, version: str | None, purl: str | None = None) -> Part:
    entry = knowledge_base().find(purl, name)
    return Part(
        kind=SOFTWARE,
        name=str(name),
        version=version,
        purl=purl,
        library=entry.library if entry else None,
        roles=tuple(entry.roles) if entry else (),
    )


def same_version(a: object, b: object) -> bool:
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    va, vb = read_version(a), read_version(b)
    if va is not None and vb is not None:
        return version_key(va) == version_key(vb)
    return a.strip().casefold() == b.strip().casefold()


def software_match(part: Part, name: object, version: object, purl: object = None) -> str | None:
    """How a component (name, version, package address) is the same software as `part`, or None. The rules are in
    the module's description, in the order they are tried."""
    if part.kind != SOFTWARE or not isinstance(name, str):
        return None
    mine, theirs = purl_base(part.purl), purl_base(purl)
    if mine is not None and theirs is not None:
        return "package" if mine == theirs and same_version(part.version, version) else None
    entry = knowledge_base().find(purl, name)
    if part.library is not None or entry is not None:
        return (
            "knowledge_base"
            if (entry is not None and entry.library == part.library and same_version(part.version, version))
            else None
        )
    # software the knowledge base knows nothing about (the customer's own, or our demo programs): the exact version
    # text, as a dependency entry is tied to a signing program ("1.4.3-otto" is another program than "1.4.3")
    same_text = (
        isinstance(version, str)
        and isinstance(part.version, str)
        and version.strip().casefold() == part.version.strip().casefold()
    )
    return "name_version" if same_text and name.strip().casefold() == str(part.name or "").strip().casefold() else None


def server_match(part: Part, address: object) -> str | None:
    if part.kind != SERVER or not isinstance(address, str):
        return None
    return "address" if address.strip().casefold() == str(part.address).strip().casefold() else None


class ImpactMixin:
    """Mixed into Lab. Needs: db, and from the other mixins: _plan, _claims, _programs, _latest_list, _dependency_state,
    _systems, assessment_for."""

    # Provided by Lab and its other mixins. Declared here for the type check only: nothing is assigned.
    db: Callable[..., Any]
    _claims: Callable[..., list[dict]]
    _programs: Callable[..., list[dict]]
    _latest_list: Callable[..., Any]
    _dependency_state: Callable[..., dict | None]
    _systems: Callable[..., list[dict]]
    assessment_for: Callable[..., Any]

    # ---------------------------------------------------------------- one assessment's facts, read once

    def _impact_facts(self, db, import_id: int, newest: int | None) -> dict:
        """What one assessment names, for matching: its servers, its programs (with their system keys) and its newest
        dependency list's components (with the row id Dependencies gives each library). An import never changes and a
        list is never changed (a newer one is a new row), so this is kept by (import, list)."""
        cache = self.__dict__.setdefault("_impact_cache", {})
        key = (import_id, newest)
        if key in cache:
            return cache[key]
        imp = db.get(ImportRow, import_id)
        claims = self._claims(imp) if imp is not None else []
        servers = list(research.servers(claims))
        programs = [
            {
                "name": str(p["component"]),
                "version": p.get("version"),
                "ref": p["ref"],
                "role": p.get("role"),
                "system": "software:" + p["ref"] if p.get("role") != "key_exchange" else None,
            }
            for p in research.programs(claims)
        ]
        components: list[dict] = []
        if newest is not None:
            row = db.get(DependencyListRow, newest)
            dl = from_store(row.parsed)
            pairs = [(p["component"], p["version"]) for p in self._programs(claims)]
            tree = build_tree(dl, pairs)
            row_ids = {r.key: f"row-{n + 1}" for n, r in enumerate(tree.rows)}
            components = [
                {"key": c.key, "name": c.name, "version": c.version, "purl": c.purl, "row": row_ids.get(c.key)}
                for c in sorted(dl.components.values(), key=lambda c: c.order)
            ]
        cache[key] = {"servers": servers, "programs": programs, "components": components}
        return cache[key]

    # ---------------------------------------------------------------- the reader

    def _impact_context(self, db, plan: PlanRow, ctx: dict | None = None) -> dict:
        """What every place lookup of one read shares, worked out once: the claims, the systems, the dependency
        state, the list itself and its top entries. Pass the same dict to each `_impact` call of one read."""
        ctx = {} if ctx is None else ctx
        if "claims" not in ctx:
            imp = db.get(ImportRow, plan.import_id)
            ctx["claims"] = self._claims(imp)
            ctx["systems"] = {s["key"]: s for s in self._systems(ctx["claims"])}
            if "state" not in ctx:
                ctx["state"] = self._dependency_state(db, plan)
            ctx["dl"], ctx["tops"] = None, set()
            if ctx["state"] is not None:
                row = self._latest_list(db, imp.id)
                ctx["dl"] = from_store(row.parsed)
                ctx["tops"] = top_keys(
                    ctx["dl"], [(p["component"], p["version"]) for p in self._programs(ctx["claims"])]
                )
            mine = self.assessment_for(plan_id=plan.id)
            ctx["mine"] = mine.id if mine is not None else None
            ctx["closed"] = mine is not None and mine.closed_at is not None
        return ctx

    def _impact(self, db, plan: PlanRow, part: Part, *, own_row: str | None = None, ctx: dict | None = None) -> dict:
        """Every place `part` is used, as plain facts (present/impact.py words them). `own_row`: the key of the
        dependency list row whose own panel asks (that row is not listed as a place it is used). `ctx`: from
        `_impact_context`, shared by the lookups of one read."""
        ctx = self._impact_context(db, plan, ctx)
        claims, systems, state = ctx["claims"], ctx["systems"], ctx["state"]
        here: list[dict] = []
        reached: dict[str, dict] = {}  # system key -> the system, for the count

        def reach(system_key: str | None) -> dict | None:
            s = systems.get(system_key) if system_key else None
            if s is not None:
                reached[s["key"]] = s
            return {"key": s["key"], "name": s["name"], "kind": s["kind"]} if s is not None else None

        # (a) the scanner file
        if part.kind == SERVER:
            if any(server_match(part, a) for a in research.servers(claims)):
                here.append(
                    {
                        "kind": "file",
                        "as": "server",
                        "how": "address",
                        "system": reach("server:" + str(part.address)),
                        "label": str(part.address),
                    }
                )
        else:
            for p in research.programs(claims):
                how = software_match(part, p["component"], p.get("version"))
                if how:
                    system = reach("software:" + p["ref"]) if p.get("role") != "key_exchange" else None
                    here.append(
                        {
                            "kind": "file",
                            "as": "signing program" if p.get("role") != "key_exchange" else "key exchange program",
                            "how": how,
                            "system": system,
                            "label": p["label"],
                        }
                    )
        # (b) the newest dependency list
        listed = state is not None
        if state is not None:
            dl, tops = ctx["dl"], ctx["tops"]
            shown_tops = {t["key"]: t for t in state["tops"]}
            rows_by_key = {r["key"]: r for r in state["rows"]}

            def tie_of(top_key: str) -> dict:
                t = shown_tops.get(top_key)
                tie = (t or {}).get("tie") or {}
                return {"system": reach(tie.get("system")), "source": tie.get("source"), "shown": t is not None}

            matched: list[str] = []
            if part.kind == SERVER:
                for top_key, t in shown_tops.items():
                    if t["tie"]["system"] == "server:" + str(part.address):
                        here.append({"kind": "part_of", "label": t["label"], "tie": tie_of(top_key)})
            else:
                for c in sorted(dl.components.values(), key=lambda c: c.order):
                    how = software_match(part, c.name, c.version, c.purl)
                    if how:
                        matched.append(c.key)
                        if c.key == own_row:
                            continue
                        r = rows_by_key.get(c.key)
                        if c.key in tops:
                            here.append(
                                {
                                    "kind": "top",
                                    "label": label(c),
                                    "how": how,
                                    "tie": tie_of(c.key),
                                    "described": c.key == dl.described,
                                }
                            )
                        else:
                            here.append({"kind": "row", "label": label(c), "how": how, "row": r["id"] if r else None})
            seen: set[str] = set()
            for key in matched:
                for top_key, via in reached_from(dl, key, tops):
                    if top_key in seen or top_key in matched:
                        continue
                    seen.add(top_key)
                    here.append(
                        {
                            "kind": "user",
                            "label": label(dl.components[top_key]),
                            "via": via,
                            "tie": tie_of(top_key),
                            "described": top_key == dl.described,
                        }
                    )
        # (c) elsewhere in the organization
        closed = ctx["closed"]
        elsewhere = [] if closed else self._impact_elsewhere(db, part, ctx)
        return {
            "part": {"kind": part.kind, "label": part.label, "library": part.library, "roles": list(part.roles)},
            "here": here,
            "listed": listed,
            "closed": closed,
            "elsewhere": elsewhere,
            "count": len(reached) + len(elsewhere),
        }

    def _impact_visible(self, db, mine: int | None) -> list[tuple[AssessmentRow, ProjectRow, int | None]]:
        """Every other assessment with a file that the organization shows, newest first: not archived, in a project that
        is not archived, in no archived folder. Each with the id of its import's newest dependency list (or None)."""
        folders = {f.id: f for f in db.scalars(select(FolderRow)).all()}

        def folder_hidden(folder_id: int | None) -> bool:
            seen: set[int] = set()
            while folder_id is not None and folder_id not in seen:
                seen.add(folder_id)
                f = folders.get(folder_id)
                if f is None:
                    return False
                if f.archived:
                    return True
                folder_id = f.parent_id
            return False

        rows = db.execute(
            select(AssessmentRow, ProjectRow)
            .join(ProjectRow, ProjectRow.id == AssessmentRow.project_id)
            .order_by(AssessmentRow.id.desc())
        ).all()
        newest = dict(
            db.execute(
                select(DependencyListRow.import_id, func.max(DependencyListRow.id)).group_by(
                    DependencyListRow.import_id
                )
            ).all()
        )
        return [
            (a, p, newest.get(a.import_id))
            for a, p in rows
            if not (a.id == mine or a.import_id is None or a.archived or p.archived or folder_hidden(p.folder_id))
        ]

    def _impact_elsewhere(self, db, part: Part, ctx: dict) -> list[dict]:
        if "visible" not in ctx:
            ctx["visible"] = self._impact_visible(db, ctx["mine"])
        found: dict[int, dict] = {}
        for a, p, newest in ctx["visible"]:
            facts = self._impact_facts(db, a.import_id, newest)
            hit = self._impact_hit(part, facts)
            if hit is None:
                continue
            slot = found.get(p.id)
            if slot is None:  # newest first: the first one found in a project is its newest
                found[p.id] = {
                    "project": {"id": p.id, "name": p.name},
                    "assessment": {
                        "id": a.id,
                        "title": a.name or f"Assessment {a.number}",
                        "closed": a.closed_at is not None,
                    },
                    "more": 0,
                    **hit,
                }
            else:
                slot["more"] += 1
        return list(found.values())

    @staticmethod
    def _impact_hit(part: Part, facts: dict) -> dict | None:
        """How one other assessment names the part: {"as", "how", "label", "link"} for its first match, or None."""
        if part.kind == SERVER:
            for address in facts["servers"]:
                if server_match(part, address):
                    return {
                        "as": "server",
                        "how": "address",
                        "label": address,
                        "link": {"page": "migration/systems", "item": "server:" + address},
                    }
            return None
        for p in facts["programs"]:
            how = software_match(part, p["name"], p["version"])
            if how:
                text = f"{p['name']} {p['version']}" if p["version"] else p["name"]
                return {
                    "as": "signing program" if p["system"] else "key exchange program",
                    "how": how,
                    "label": text,
                    "link": {"page": "migration/systems", "item": p["system"]}
                    if p["system"]
                    else {"page": "inventory/import", "item": None},
                }
        for c in facts["components"]:
            how = software_match(part, c["name"], c["version"], c["purl"])
            if how:
                text = f"{c['name']} {c['version']}" if c["version"] else c["name"]
                return {
                    "as": "dependency list",
                    "how": how,
                    "label": text,
                    "link": {"page": "migration/dependencies", "item": c["row"]},
                }
        return None

    # ---------------------------------------------------------------- what each fix is about

    def _fix_impact(self, db, plan: PlanRow, fix: dict, answered: dict, ctx: dict) -> dict | None:
        """The block "What this change touches" for one fix of Fixes, or None for Change watch's entry (it is counted
        nowhere and is about a developer's branch). What the fix is about is read from the fix as Fixes has it."""
        from app.present import impact as words

        source = fix.get("source_kind")
        if source == "developer_change":
            return None
        ctx = self._impact_context(db, plan, ctx)
        if "changes" not in ctx:
            ctx["changes"] = {c["key"]: c for c in self._plan_changes(db, plan)}  # type: ignore[attr-defined]
        changes: dict = ctx["changes"]
        part: Part | None = None
        change: dict | None = None
        compatible: str | None = None
        signing_change = False
        what = "a program"
        if source == "migration":
            system = ctx["systems"].get(fix["migration"]["system"])
            if system is None:
                return None
            if system["kind"] == "server":
                part = server_part(system["name"])
                change = changes.get("migration:" + system["key"]) if fix["migration"]["what"] == "howto" else None
            else:
                program = system.get("program") or {}
                part = software_part(str(program.get("component") or system["name"]), program.get("version"))
                signing_change = True
        elif source == "dependency":
            state = ctx["state"] or {}
            row = next((r for r in state.get("rows") or [] if r["key"] == fix["dependency"]["row_key"]), None)
            if row is None:
                return None
            part = software_part(row["name"], row.get("version"), row.get("purl"))
            firsts = [
                b.get("first_version")
                for s in (state.get("systems") or {}).values()
                for bs in s["blockers"].values()
                for b in bs
                if b["row_key"] == row["key"]
            ]
            first = next((f for f in firsts if f and f != "none_known"), None)
            compatible = f"{first} or later" if first else "a newer version"
            what = "a library"
        elif source == "applied_change":
            change = changes.get(fix.get("change_key"))
            if change is None or not change.get("address"):
                return None
            part = server_part(change["address"])
        elif fix.get("kind") == "code":
            component = fix.get("component") or {}
            part = software_part(str(component.get("name")), component.get("version"))
            matches = (((fix.get("change") or {}).get("built") or {}).get("matches")) or {}
            compatible = matches.get("version") or "the fixed version"
            what = "a signing program"
        else:
            run, address = answered.get(fix["id"], (None, None))
            if address is not None:
                part = server_part(address)
                item_ids = {a["item_id"] for a in fix.get("answers") or []}
                change = next(
                    (c for c in changes.values() if c.get("kind") == "tls" and c.get("_item_id") in item_ids), None
                )
            else:
                otto, real = fix.get("otto_fix") or {}, fix.get("real_library") or {}
                name = (run.component_name if run is not None else None) or real.get("name")
                version = (run.component_version if run is not None else None) or real.get("version")
                if not name:
                    return None
                part = software_part(str(name), version)
                compatible = (
                    (otto.get("version") if otto.get("kind") == "update" else None)
                    or real.get("fixed")
                    or "the fixed version"
                )
                what = "a library" if part.library else "a program"
        if part is None:
            return None
        facts = self._impact(db, plan, part, ctx=ctx)
        if part.kind == SERVER and change is None:
            connect = words.CONNECT_TEXT_ONLY
        else:
            connect = words.connect_line(facts["part"], change=change, signing_change=signing_change, what=what)
        return words.block(
            facts,
            on_fix=True,
            compatible_for=compatible,
            connect=connect,
            apply_note=bool(part.kind == SERVER and change is not None and change.get("target")),
        )

    def _dependency_impact(self, db, plan: PlanRow, state: dict | None) -> dict[str, dict]:
        """Phase 4e: "Where it is used" for every library row of the Dependencies view, by the row's key."""
        from app.present import impact as words

        if state is None:
            return {}
        ctx = self._impact_context(db, plan, {"state": state})
        return {
            r["key"]: words.block(
                self._impact(
                    db, plan, software_part(r["name"], r.get("version"), r.get("purl")), own_row=r["key"], ctx=ctx
                ),
                on_fix=False,
            )
            for r in state["rows"]
        }

    def _row_users(self, db, plan: PlanRow, state: dict | None) -> dict[str, list[dict]]:
        """For every library row of the dependency list: every top entry that reaches it ({"key", "label", "via"}), by
        the same walk as "Where it is used". The what-if card's "Where the library is used" reads this, so the two
        never disagree."""
        if state is None:
            return {}
        ctx = self._impact_context(db, plan, {"state": state})
        dl, tops = ctx["dl"], ctx["tops"]
        return {
            r["key"]: [
                {"key": top, "label": label(dl.components[top]), "via": via}
                for top, via in reached_from(dl, r["key"], tops)
            ]
            for r in state["rows"]
            if r["key"] in dl.components
        }


__all__ = ["ImpactMixin", "Part", "server_part", "software_part", "software_match", "server_match", "same_version"]

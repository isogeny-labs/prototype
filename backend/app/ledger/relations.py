"""Phase 5b: what each item relates to, for the Related block of every detail panel.

Only recorded links are used: the claim a test targets (its ref, or its address and kind), the results a fix came from,
a system's address or program, a migration system's own fixes, a library's tie and blockers. A link two steps away
through one of these (a fix and the system its failed test ran on) is still a recorded fact. Nothing is guessed: with
no recorded link there is no line. Every word shown comes from the page the item lives on.
"""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import func, select

from app.db import ImportRow, PlanItemRow, TestSpecRow, VerifyRunRow
from app.errors import NotFound
from app.lab.testlab import HIDDEN_ORIGINS, MIGRATION_ORIGIN, read_spec
from app.ledger.checks import TEST_CLAIM_KINDS

LINES = (
    ("claim", "Claim"),
    ("test", "Checks"),
    ("fix", "Fix"),
    ("system", "System and track"),
    ("library", "Library"),
    ("advisory", "Advisory"),
)  # phase 5c: the sixth line, on an advisory check, its result and its fix


def migration_view_if_written(lab: Any, plan_id: int) -> dict | None:
    """The Migration view, but only once its measurements are written down (opening Migration or Measure status does
    that). The pages of phase 5b only read: they never lock a measurement by looking. None before then."""
    with lab.db() as db:
        written = (
            db.scalar(
                select(func.count(PlanItemRow.id)).where(
                    PlanItemRow.plan_id == plan_id, PlanItemRow.origin == MIGRATION_ORIGIN
                )
            )
            or 0
        )
    if not written:
        return None
    try:
        return lab.migration_view(plan_id)
    except NotFound:
        return None


class RelationsMixin:
    """Mixed into `Lab`."""

    db: Callable[..., Any]
    _plan: Callable[..., Any]
    lab_view: Callable[[int], dict]
    fixes_view: Callable[[int], dict]
    fix_states: Callable[[int], list[dict]]
    migration_view: Callable[[int], dict]
    dependencies_view: Callable[..., dict]
    _migration_states: Callable[..., list[dict]]
    _systems: Callable[[list[dict]], list[dict]]

    def relation_graph(self, plan_id: int) -> dict:
        """{"nodes": {key: {kind, label, sub, link}}, "edges": {key: set(keys)}, "alias": {key: key}}."""
        nodes: dict[str, dict] = {}
        edges: dict[str, set] = {}
        alias: dict[str, str] = {}

        def link(a: str, b: str) -> None:
            if a in nodes and b in nodes and a != b:
                edges.setdefault(a, set()).add(b)
                edges.setdefault(b, set()).add(a)

        with self.db() as db:
            plan = self._plan(db, plan_id)
            imp = db.get(ImportRow, plan.import_id)
            claims = list(imp.claims) if imp is not None else []
            verify = db.scalars(
                select(VerifyRunRow)
                .where(VerifyRunRow.import_id == plan.import_id)
                .order_by(VerifyRunRow.id.desc())
                .limit(1)
            ).first()
            results = (
                {r.get("claim_id"): r.get("result") for r in (verify.results or []) if isinstance(r, dict)}
                if verify
                else {}
            )
            items = [
                i
                for i in db.scalars(select(PlanItemRow).where(PlanItemRow.plan_id == plan_id)).all()
                if not i.removed and i.origin not in HIDDEN_ORIGINS
            ]
            specs = {i.id: read_spec(db.get(TestSpecRow, i.spec_hash))[0] for i in items}
            states = self._migration_states(db, plan)
        system_of_item = {s["item_id"]: s["key"] for s in states}

        for c in claims:
            nodes[f"claim:{c.id}"] = {
                "kind": "claim",
                "label": c.text,
                "sub": results.get(c.id) or "Not verified yet",
                "link": {"page": "inventory/verify" if results else "inventory/import", "item": f"claim-{c.id}"},
            }
        lab = {r["item_id"]: r for r in self.lab_view(plan_id)["rows"]}
        for item in items:
            spec = specs.get(item.id) or {}
            row = lab.get(item.id) or {}
            shown = row.get("after") or row.get("result")
            target = spec.get("target") or {}
            where = target.get("address") or next((c.location for c in claims if c.ref == target.get("claim")), None)
            if row.get("after") and row["after"].get("component"):
                # the newest result is a retest's, on another version of the program: say the version it ran on, so that
                # "Passed" never stands beside the version the file names when it was measured on a newer one
                where = row["after"]["component"]
            nodes[f"test:{item.id}"] = {
                "kind": "test",
                "label": spec.get("title") or "A test",
                "sub": " · ".join(x for x in (where, shown["label"] if shown else "Not run yet") if x),
                "link": {"page": "evidence", "item": f"test-{item.id}"},
            }
        mview = migration_view_if_written(self, plan_id)
        if mview is None:
            # Migration not opened yet: the systems the file names, not measured (nothing is written down by looking).
            claim_dicts = [
                {
                    "location": c.location,
                    "location_kind": c.location_kind,
                    "kind": c.kind,
                    "ref": c.ref,
                    "detail": c.detail,
                    "text": c.text,
                    "claimed_value": c.claimed_value,
                }
                for c in claims
            ]
            mview = {
                "systems": [
                    {"key": s["key"], "name": s["name"], "tracks": [], "status": {"label": "Not measured yet"}}
                    for s in self._systems(claim_dicts)
                ],
                "roadmap": {"bands": []},
            }
        bands: dict[tuple[str, str], str] = {}
        for band in (mview.get("roadmap") or {}).get("bands") or []:
            for r in band.get("rows") or []:
                bands[(r["system_key"], r.get("track") or "")] = band["title"]
        for s in mview.get("systems") or []:
            tracks = []
            for t in s.get("tracks") or []:
                band = bands.get((s["key"], t.get("short_title") or t["title"])) or bands.get((s["key"], "Both tracks"))
                tracks.append(
                    f"{t['short_title'] if t.get('short_title') else t['title']}: {t['status']['label']}"
                    + (f", {band}" if band else "")
                )
            sub = " · ".join(tracks) if tracks else s["status"]["label"]
            nodes[f"system:{s['key']}"] = {
                "kind": "system",
                "label": s["name"],
                "sub": sub,
                "link": {"page": "migration/roadmap", "item": s["key"]},
                "also": {"page": "migration/systems", "item": s["key"]},
            }
        fixes_view = self.fixes_view(plan_id)
        for f in fixes_view.get("fixes") or []:
            nodes[f"fix:{f['id']}"] = {
                "kind": "fix",
                "label": f["title"],
                "sub": f["status"]["word"],
                "link": {"page": "fixes", "item": f["id"]},
            }
            if f.get("change_box"):
                alias[f"change:{f['change_box']['id']}"] = f"fix:{f['id']}"
        for s in mview.get("systems") or []:
            change = s.get("change")
            if change and f"change:{change['id']}" not in alias:
                alias[f"change:{change['id']}"] = f"system:{s['key']}"
        try:
            dview = self.dependencies_view(plan_id, with_impact=False)
        except NotFound:
            dview = {"groups": []}
        for g in dview.get("groups") or []:
            for r in g.get("rows") or []:
                blocks = r.get("blocks") or []
                sub = (
                    " · ".join(f"blocks {b['system']} · {b['track_words']}" for b in blocks)
                    if blocks
                    else " · ".join(c["answer_words"] for c in r.get("cells") or [])
                )
                nodes[f"library:{r['id']}"] = {
                    "kind": "library",
                    "label": r["label"],
                    "sub": sub,
                    "link": {"page": "migration/dependencies", "item": r["id"]},
                }
                for b in blocks:
                    link(f"library:{r['id']}", f"system:{b['system']}")
                    link(f"library:{r['id']}", f"fix:{b['fix_id']}")

        # Phase 5c: the advisories of the installed test packs, each linked to its checks in this plan (a recorded link:
        # the locked test names its advisory). Through a check, its fix relates to the advisory too.
        for a in self.otto_relations(plan_id):  # type: ignore[attr-defined]
            nodes[f"advisory:{a['id']}"] = {
                "kind": "advisory",
                "label": f"{a['name']} ({a['id']})",
                "sub": a["sub"],
                "link": {"page": "advisories", "item": a["id"]},
            }
            for item_id in a["items"]:
                link(f"advisory:{a['id']}", f"test:{item_id}")

        # claims <-> tests <-> systems
        for item in items:
            spec = specs.get(item.id) or {}
            target = spec.get("target") or {}
            key = f"test:{item.id}"
            for c in claims:
                if target.get("claim") and c.ref == target.get("claim"):
                    link(key, f"claim:{c.id}")
                elif (
                    target.get("address")
                    and c.location == target.get("address")
                    and c.kind in TEST_CLAIM_KINDS.get(str(spec.get("kind")), ())
                ):
                    link(key, f"claim:{c.id}")
            if target.get("address"):
                link(key, f"system:server:{target['address']}")
            if target.get("claim"):
                link(key, f"system:software:{target['claim']}")
        for c in claims:
            if c.location_kind == "server":
                link(f"claim:{c.id}", f"system:server:{c.location}")
            else:
                link(f"claim:{c.id}", f"system:software:{c.ref}")
        # fixes <-> the results they came from, and through them the claims and systems
        for f in self.fix_states(plan_id):
            fkey = f"fix:{f['id']}"
            for a in f.get("answers") or []:
                item_id = a.get("item_id")
                if item_id in system_of_item:
                    link(fkey, f"system:{system_of_item[item_id]}")
                    continue
                tkey = f"test:{item_id}"
                link(fkey, tkey)
                for n in list(edges.get(tkey, ())):
                    if n.startswith(("claim:", "system:", "advisory:")):
                        link(fkey, n)
            if f.get("change_key"):
                alias.setdefault(f"change:{f['change_key']}", fkey)
        for s in states:
            for fix_id in (s.get("fix_ids") or {}).values():
                link(f"system:{s['key']}", f"fix:{fix_id}")
        return {"nodes": nodes, "edges": edges, "alias": alias}

    def related(self, plan_id: int, key: str, graph: dict | None = None) -> list[dict]:
        """The Related block for one item: up to five lines, each only when a relation is recorded."""
        g = graph or self.relation_graph(plan_id)
        key = g["alias"].get(key, key)
        near = g["edges"].get(key, set())
        out = []
        for kind, title in LINES:
            entries = [dict(g["nodes"][n], key=n) for n in sorted(near) if g["nodes"].get(n, {}).get("kind") == kind]
            if entries:
                out.append(
                    {
                        "kind": kind,
                        "title": title,
                        "items": [
                            {
                                "key": e["key"],
                                "label": e["label"],
                                "sub": e["sub"],
                                "link": e["link"],
                                "also": e.get("also"),
                            }
                            for e in entries
                        ],
                    }
                )
        return out

    def resolve_link(self, plan_id: int, link: dict, graph: dict | None = None) -> dict:
        """A link that names a change ("change:<key>") opens where its change box is: the fix in Fixes or the system."""
        item = str(link.get("item") or "")
        if not item.startswith("change:"):
            return link
        g = graph or self.relation_graph(plan_id)
        target = g["alias"].get(item)
        node = g["nodes"].get(str(target)) if target else None
        if node is None:
            return {**link, "item": None}
        return dict(node["link"]) if node["kind"] == "fix" else dict(node.get("also") or node["link"])

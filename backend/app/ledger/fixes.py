"""Phase 5b: the Fixes view in the four work groups. A fix keeps every word and button it had; it gains its group, links
for where it came from, and the counts of each group. An item that also matters to another group is linked from that
group's foot, never listed twice."""
from __future__ import annotations

from app.engine.research import TITLES
from app.ledger import groups as G


def came_from_links(state: dict) -> list[dict]:
    """The results a fix came from, each a link to that result (Evidence, the system, or the library)."""
    if state.get("source_kind") == "dependency" or state.get("test_kind") == "capability":
        dep = state.get("dependency") or {}
        return [{"label": "The library's answer", "link": {"page": "migration/dependencies", "item": dep.get("row") or dep.get("row_key")}},
                {"label": "The track it blocks", "link": {"page": "migration/roadmap", "item": dep.get("system")}}]
    if state.get("source_kind") == "migration":
        system = None
        for a in state.get("answers") or []:
            system = a.get("system_key") or system
        return [{"label": "The migration plan", "link": {"page": "migration/systems", "item": system}}] if system else []
    if state.get("source_kind") == "developer_change":
        # phase 6d: the change itself on Change watch, then each test's run on the change (a row of that watch run on Checks)
        change = state.get("developer_change") or {}
        return ([{"label": "The developer's change", "link": {"page": "change-watch", "item": change.get("id")}}]
                + [{"label": f"{t.get('title')} on the change", "link": {"page": "checks", "item": f"watch-{t.get('item_id')}-in-{change.get('watch_run_id')}"}}
                   for t in change.get("tests") or []])
    out, seen = [], set()
    for a in state.get("answers") or []:
        item_id = a.get("item_id")
        if item_id is None or item_id in seen:
            continue
        seen.add(item_id)
        out.append({"label": TITLES.get(a.get("kind"), "A failed test"), "link": {"page": "evidence", "item": f"test-{item_id}"}})
    return out


def also_relates(state: dict, listed: set | None = None) -> list[str]:
    """The other groups a fix matters to (it is linked from their foot). `listed`: the (library, version) pairs of the
    dependency list, lower case."""
    group = G.group_of_fix(state)
    out = []
    if group == "dependencies":
        out.append("migration")   # a library update unblocks a migration track
    real = state.get("real_library")
    if group == "encryption" and real and (str(real.get("name") or "").casefold(), str(real.get("version") or "")) in (listed or set()):
        out.append("dependencies")   # the update for a failed test on a real library that is in the dependency list
    return [g for g in out if g != group]


def group_fixes(view: dict, pairs: list[tuple[dict, dict]], migration_systems: dict[int, str] | None = None,
                listed: set | None = None) -> dict:
    """Add the group, the links and the group headings to a Fixes view (in place) and return it."""
    systems = migration_systems or {}
    by_group: dict[str, list[dict]] = {k: [] for k in G.GROUP_KEYS}
    apart: dict[str, list[dict]] = {k: [] for k in G.GROUP_KEYS}     # phase 6d: listed under their own heading, never counted
    also: dict[str, list[dict]] = {k: [] for k in G.GROUP_KEYS}
    for state, detail in pairs:
        if state.get("source_kind") == "migration":
            for a in state.get("answers") or []:
                if a.get("item_id") in systems:
                    a.setdefault("system_key", systems[a["item_id"]])
        group = G.group_of_fix(state)
        detail["group"] = group
        detail["group_label"] = G.GROUP_LABELS[group]
        detail["came_from_links"] = came_from_links(state)
        detail["fix_state"] = G.fix_state(detail["status"]["word"])
        detail["apart"] = G.fix_is_apart(state)
        (apart if detail["apart"] else by_group)[group].append(detail)
        for other in also_relates(state, listed):
            also[other].append({"fix_id": detail["id"], "title": detail["title"], "group_label": G.GROUP_LABELS[group]})
    view["groups"] = [{**G.group_frame(k), "counts": G.counts(d["fix_state"] for d in by_group[k]),
                       "fix_ids": [d["id"] for d in by_group[k]], "empty_text": None if by_group[k] else G.EMPTY_FIXES[k],
                       "apart": ({"label": G.APART_LABEL, "note": G.APART_NOTE, "fix_ids": [d["id"] for d in apart[k]]}
                                 if apart[k] else None),
                       "also": also[k]} for k in G.GROUP_KEYS]
    return view

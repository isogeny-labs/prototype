"""From a read dependency list to group headings and rows (phase 4d, docs/SPEC.md section 7e).

- A top entry (a group heading) is the thing the list describes, any component the list marks as an application or a
  container, and any component whose name and version equal a signing program in the claims file. Top entries are the
  customer's own software: they are not looked up and get no answers.
- Every other component that is a library is a row, and belongs to the nearest top entry above it (ties go to the
  top entry that comes first in the file). A row no top entry reaches belongs to the thing the list describes.
- "How it got there" is the shortest path from its top entry; the evidence keeps every path's length.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from app.importer.sbom import NOT_LIBRARIES, TOP_TYPES, Component, DependencyList

LOOSE = "(not under any entry)"   # the heading for rows a list without a described thing leaves on their own


@dataclass
class Top:
    key: str
    name: str
    version: str | None
    kind: str
    order: int
    program: tuple[str, str] | None = None    # (name, version) of the signing program it equals, if any


@dataclass
class Row:
    key: str
    name: str
    version: str | None
    purl: str | None
    kind: str
    owner: str                     # the key of its top entry
    via: list[str] = field(default_factory=list)    # the names in between, nearest the top entry first
    paths: int = 1                 # how many shortest paths lead to it


@dataclass
class Tree:
    format: str
    tops: list[Top]
    rows: list[Row]
    not_libraries: int


def label(c: Component | Top | Row) -> str:
    return f"{c.name} {c.version}".strip() if c.version else c.name


def build_tree(dl: DependencyList, programs: list[tuple[str, str]]) -> Tree:
    wanted = {(n.casefold(), v) for n, v in programs}
    comps = dl.components
    tops: dict[str, Top] = {}
    for c in sorted(comps.values(), key=lambda c: c.order):
        program = next(((n, v) for n, v in programs if (c.name.casefold(), c.version) == (n.casefold(), v)), None)
        if c.key == dl.described or c.kind in TOP_TYPES or program is not None or (c.name.casefold(), c.version) in wanted:
            tops[c.key] = Top(key=c.key, name=c.name, version=c.version, kind=c.kind, order=c.order, program=program)
    # the nearest top entry of every component, by a search from all top entries at once (earlier ones win ties)
    owner: dict[str, str] = {}
    distance: dict[str, int] = {}
    parent: dict[str, str] = {}
    counts: dict[str, int] = {}
    queue: deque[str] = deque()
    for top in sorted(tops.values(), key=lambda t: t.order):
        owner[top.key], distance[top.key], counts[top.key] = top.key, 0, 1
        queue.append(top.key)
    while queue:
        here = queue.popleft()
        for nxt in dl.edges.get(here, []):
            if nxt in tops:
                continue                       # another group heading starts its own group
            d = distance[here] + 1
            if nxt not in distance:
                distance[nxt], owner[nxt], parent[nxt], counts[nxt] = d, owner[here], here, counts[here]
                queue.append(nxt)
            elif distance[nxt] == d and owner[nxt] == owner[here]:
                counts[nxt] = min(counts[nxt] + counts[here], 10_000)
    loose_owner = dl.described if dl.described in tops else None
    rows: list[Row] = []
    not_libraries = 0
    for c in sorted(comps.values(), key=lambda c: c.order):
        if c.key in tops:
            continue
        if c.kind in NOT_LIBRARIES:
            not_libraries += 1
            continue
        if c.key in owner:
            via, step = [], parent.get(c.key)
            while step is not None and step not in tops:
                via.append(label(comps[step]))
                step = parent.get(step)
            rows.append(Row(key=c.key, name=c.name, version=c.version, purl=c.purl, kind=c.kind, owner=owner[c.key],
                            via=list(reversed(via)), paths=counts.get(c.key, 1)))
        else:
            if loose_owner is None:
                tops.setdefault(LOOSE, Top(key=LOOSE, name=LOOSE, version=None, kind="none", order=10**9))
            rows.append(Row(key=c.key, name=c.name, version=c.version, purl=c.purl, kind=c.kind, owner=loose_owner or LOOSE))
    used = {r.owner for r in rows}
    # The thing the list describes is a heading only when rows hang directly under it (the view names it on top anyway);
    # every other top entry is the customer's own software and is always shown, with or without libraries.
    shown = [t for t in sorted(tops.values(), key=lambda t: t.order)
             if (t.key not in (LOOSE, dl.described) or t.key in used or t.program is not None)]
    return Tree(format=dl.format, tops=shown, rows=rows, not_libraries=not_libraries)


def top_keys(dl: DependencyList, programs: list[tuple[str, str]]) -> set[str]:
    """Every component that is a top entry by the rule above (the thing the list describes, an application or a
    container, or a component whose name and version equal a signing program of the file). The same rule as
    build_tree's, before it leaves out headings with nothing under them."""
    wanted = {(n.casefold(), v) for n, v in programs}
    return {c.key for c in dl.components.values()
            if c.key == dl.described or c.kind in TOP_TYPES or (c.name.casefold(), c.version) in wanted}


def reached_from(dl: DependencyList, key: str, tops: set[str]) -> list[tuple[str, list[str]]]:
    """Change impact (phase 4e): every top entry from which the component `key` can be reached, each with its shortest
    path (the labels of the components in between, nearest the top entry first). Unlike the grouping of build_tree
    (each row under one heading only), EVERY top entry that reaches it is listed. A path stops at the first top entry
    it meets: that one is the customer's software that uses it, and whatever uses that software is that software's
    own question (so the thing the whole list describes is not named on every row). In file order of the top
    entries; the component itself is never listed as reaching itself."""
    users: dict[str, list[str]] = {}
    for parent, children in dl.edges.items():
        for child in children:
            users.setdefault(child, []).append(parent)
    comps = dl.components
    nearer: dict[str, str | None] = {key: None}     # component -> the next component on its shortest way down to `key`
    queue: deque[str] = deque([key])
    while queue:
        here = queue.popleft()
        if here != key and here in tops:
            continue                               # a top entry: the walk up stops here
        for up in users.get(here, []):
            if up in nearer or up not in comps:
                continue
            nearer[up] = here
            queue.append(up)
    out = []
    for top in sorted((t for t in nearer if t in tops and t != key), key=lambda t: comps[t].order):
        via, step = [], nearer[top]
        while step is not None and step != key:
            via.append(label(comps[step]))
            step = nearer[step]
        out.append((top, via))
    return out


def to_store(dl: DependencyList) -> dict:
    """What is kept of a list in the database: enough to rebuild the tree, and nothing that could run."""
    return {"format": dl.format, "described": dl.described,
            "components": [{"key": c.key, "name": c.name, "version": c.version, "purl": c.purl, "kind": c.kind, "order": c.order}
                           for c in sorted(dl.components.values(), key=lambda c: c.order)],
            "edges": dl.edges}


def from_store(data: dict) -> DependencyList:
    comps = {c["key"]: Component(key=c["key"], name=c["name"], version=c.get("version"), purl=c.get("purl"), kind=c.get("kind") or "library",
                                 order=int(c.get("order") or 0)) for c in data.get("components", [])}
    return DependencyList(format=data.get("format", ""), described=data.get("described"), components=comps,
                          edges={k: list(v) for k, v in (data.get("edges") or {}).items()})

"""Helpers for the Observatory's tests (not a test file, and not a conftest: a second file of that name would hide
tests/conftest.py). A walk of the Acme Pay demo through the same path as the buttons, with the map and every page's
own view kept at each stage; what the demo files themselves say, worked out here apart from the app; and the check
that a link opens something."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from app.config import DEMO_CBOM
from app.errors import NotFound
from app.ledger.relations import migration_view_if_written
from app.observatory import build
from app.web import models
from conftest import demo_plan, play_back_speed
from tests.view_helpers import problems

REPO = Path(__file__).resolve().parents[3]
DEMO_LIST = REPO / "demo" / "dependencies-demo.cdx.json"
CBOM = json.loads(DEMO_CBOM.read_text())
LISTED = json.loads(DEMO_LIST.read_text())
PAGES = {
    "observatory",
    "inventory/import",
    "inventory/verify",
    "checks",
    "evidence",
    "fixes",
    "migration/systems",
    "migration/roadmap",
    "migration/dependencies",
}
NEVER = re.compile(r"\b(secure|security score|score|severity|severe|critical|time.to.hack)\b", re.I)
NOT_YET = ("Not checked yet", "Not measured yet")


def snapshot(lab, plan, panels: bool = True, overview: bool = True) -> SimpleNamespace:
    """The map as it stands now, one panel for each of its boxes, and each page's own view at the same moment.
    `panels` and `overview` can be left out where a walk does not read them (each is a read of its own)."""
    view = build.view_of_plan(lab, plan.id)
    assert problems(view, models.ObservatoryView, "observatory") == []
    opened = {}
    for b in boxes(view) if panels else []:
        opened[b["key"]] = build.panel_of_plan(lab, plan.id, b["key"])
        assert problems(opened[b["key"]], models.ObservatoryPanel, b["key"]) == []
    try:
        verify = lab.latest_verify(plan.imp["id"])
    except NotFound:
        verify = None
    graph = lab.relation_graph(plan.id) if opened else None
    return SimpleNamespace(
        view=view,
        panels=opened,
        # the Related block every page shows for the same system, read at the same moment
        related={
            key: lab.related(plan.id, panel["related_key"], graph)
            for key, panel in opened.items()
            if panel["related_key"]
        },
        verify=verify,
        lab=lab.lab_view(plan.id),
        checks=lab.checks_view(plan.id),
        migration=migration_view_if_written(lab, plan.id),
        dependencies=lab.dependencies_view(plan.id, with_impact=False),
        overview=lab.assessment_blocks(plan.imp["id"], plan.id) if overview else None,
    )


def start(lab, small: bool = False) -> SimpleNamespace:
    """The demo file in, its address confirmed, its plan made. `small`: without the slowest test (the Independent
    exam), for the walks of the everyday set; the speed test plays back made-up timings either way."""
    play_back_speed(lab)
    plan = demo_plan(lab)
    if small:
        lab.remove_test(plan.id, plan.item["official_vectors"])
    plan.address = plan.imp["addresses"][0]["address"]
    plan.server = "server:" + plan.address
    plan.program = "software:lib-acme-sign"
    return plan


def add_list(lab, plan) -> dict:
    return lab.add_dependency_list(plan.id, DEMO_LIST.name, DEMO_LIST.read_bytes())


# ---------------------------------------------------------------- reading a map


def boxes(view: dict) -> list[dict]:
    return [b for s in view["services"] for b in s["boxes"]]


def box(view: dict, key: str) -> dict:
    return next(b for b in boxes(view) if b["key"] == key)


def spot(view: dict, key: str, name: str) -> dict:
    return next(s for s in box(view, key)["spots"] if s["key"] == name)


def checks(view_or_box: dict) -> list[dict]:
    found = boxes(view_or_box) if "services" in view_or_box else [view_or_box]
    return [c for b in found for s in b["spots"] for c in s["checks"]]


def check(view: dict, key: str, check_id: str) -> dict:
    return next(c for c in checks(box(view, key)) if c["id"] == check_id)


def lines(view: dict, kind: str | None = None) -> set[tuple[str, str, str, str]]:
    return {(ln["start"], ln["end"], ln["kind"], ln["label"]) for ln in view["lines"] if kind in (None, ln["kind"])}


def counts(view: dict) -> dict[str, int]:
    return {c["key"]: c["count"] for c in view["counts"]}


def summed(groups: list[dict]) -> dict[str, int]:
    """The counts by tag of the four work groups, added up (what the Overview shows group by group)."""
    out = {"live": 0, "lab": 0, "file": 0, "published": 0}
    for group in groups:
        for entry in group["source_counts"]:
            out[entry["key"]] += entry["count"]
    return out


def texts(value) -> list[str]:
    if isinstance(value, dict):
        return [t for v in value.values() for t in texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in texts(v)]
    return [value] if isinstance(value, str) else []


def every_link(value, out: list | None = None) -> list[dict]:
    """Every link anywhere in an answer (a dict with a page and an item)."""
    out = [] if out is None else out
    if isinstance(value, dict):
        if "page" in value and "item" in value:
            out.append(value)
        for v in value.values():
            every_link(v, out)
    elif isinstance(value, list):
        for v in value:
            every_link(v, out)
    return out


def known(lab, plan) -> dict[str, set]:
    """Everything a link of this assessment can open, read once from the pages themselves: the boxes of the map, the
    claims of Import and Verify, the rows of Checks and Evidence, the fixes, the systems and the libraries."""
    rows: set[str] = set()
    for group in lab.checks_view(plan.id)["groups"]:
        rows |= {r["id"] for r in group["rows"]}
        for part in (group.get("parts") or {}).values():
            rows |= {r["id"] for b in (part or {}).get("blocks") or [] for r in b["rows"]}
    claims = lab.import_json_for(plan.imp["id"])["claims"]
    systems = {"server:" + c["location"] for c in claims if c["location_kind"] == "server"}
    systems |= {"software:" + c["ref"] for c in claims if c["location_kind"] == "software"}
    libraries = lab.dependencies_view(plan.id, with_impact=False)
    return {
        "observatory": {b["key"] for b in boxes(build.view_of_plan(lab, plan.id))},
        "inventory/import": {f"claim-{c['id']}" for c in claims},
        "inventory/verify": {f"claim-{c['id']}" for c in claims},
        "evidence": rows,
        "checks": rows,
        "fixes": {f["id"] for f in lab.fixes_view(plan.id)["fixes"]},
        "migration/systems": systems,
        "migration/roadmap": systems,
        "migration/dependencies": {r["id"] for g in libraries["groups"] for r in g["rows"]},
    }


def opens(found: dict[str, set], link: dict) -> bool:
    """Does this link open something that is there: a page, and on it the item it names? `found`: from `known`."""
    page, item = link["page"], link["item"]
    return page in PAGES and (item is None or item in found.get(page, set()))


def really_opens(lab, plan, link: dict, found: dict[str, set]) -> bool:
    """The same, asked of the page's own read of that one item where the page has one (slower: for one link of each
    kind): a box's panel, a check's detail."""
    page, item = link["page"], link["item"]
    if item is not None and page == "observatory":
        return build.panel_of_plan(lab, plan.id, item)["key"] == item
    if item is not None and page in ("evidence", "checks"):
        try:
            return lab.check_detail(plan.id, item)["check"]["id"] == item
        except NotFound:
            return False
    return opens(found, link)


# ---------------------------------------------------------------- what the two demo files themselves say


def listed_tops() -> dict[str, dict]:
    """The dependency list's own software (every component it marks as an application), by its key."""
    return {c["bom-ref"]: c for c in LISTED["components"] if c["type"] == "application"}


def libraries_under(top: str) -> list[str]:
    """Every library the list's `dependsOn` lines lead to from one top entry, never passing another top entry."""
    below = {d["ref"]: d.get("dependsOn", []) for d in LISTED["dependencies"]}
    tops, found, queue = set(listed_tops()), [], [top]
    while queue:
        for nxt in below.get(queue.pop(0), []):
            if nxt not in tops and nxt not in found:
                found.append(nxt)
                queue.append(nxt)
    return found


def file_says_uses(source: str, target: str) -> bool:
    """Does the scanner file itself lead from one bom-ref to another, along `dependsOn` and `provides` only?"""
    below: dict[str, list[str]] = {}
    for d in CBOM["dependencies"]:
        below.setdefault(d["ref"], []).extend([*d.get("dependsOn", []), *d.get("provides", [])])
    seen, queue = {source}, [source]
    while queue:
        for nxt in below.get(queue.pop(0), []):
            if nxt == target:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False

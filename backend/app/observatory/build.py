"""The Observatory's read: the layout of the files (layout.py) with each check's own word laid on it.

Three answers, all worked out from the records on every read and none of them kept:
  - `view`: the map (the boxes, the places cryptography sits in each with their checks by name, the cryptography lane,
    the lines, the four counts by tag and what the files don't say);
  - `panel`: one box opened (a summary built from counts of the checks' own words, each check's plain sentence as its
    own page shows it, links to where each result lives, the lines of the files that name the box, and its Related
    block);
  - `place`: where one result sits on the map, keyed by the key its Related block uses.

Where each word comes from. A claim's word, sentence and tag: Verify's own result (`Lab.latest_verify`). A test's word,
sentence and tag, and its retest's: Evidence's own rows (`Lab.lab_view`: the first run, and beside it the newest
retest's, labelled with the version it ran on). A post-quantum status: the Migration plan's own tracks, read only once
its measurements were written down (`migration_view_if_written`: looking at the map locks nothing). A library's answer
summary and tag: Dependencies' own rows. The four counts: the sum of the Overview's counts by tag (`Lab.checks_view`).
The links between items and the Related block: `ledger/relations.py`.

What is never drawn: a try on a test copy (it is not the live system; its fix, which holds it, is linked), and a run
of Change watch (those runs are kept apart from the assessment's own results by the rules). Both follow from reading
Evidence's rows, which hold neither.

It only reads: no row is added or changed, no job is started, nothing is decided, and nothing asks Claude.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy import select

from app.db import DependencyListRow, ImportFileRow, ImportRow, PlanRow, iso
from app.dependencies.tree import from_store
from app.dependencies.tree import label as component_label
from app.errors import NotFound
from app.importer import structure as S
from app.importer.common import ImportFileError
from app.ledger.checks import VERIFY_TONES
from app.ledger.relations import migration_view_if_written
from app.names import TLS_VERSIONS, join_and
from app.observatory import layout as L
from app.present import observatory as words
from app.present import source as present_source
from app.present.times import instant

PAGE = "observatory"
FIRST_FEW = 3  # the libraries of a group that the map lists; the rest are on Dependencies
MAX_FILE_LINES = 12
_AFTER_CHANGE = ("after_apply", "after_rollback")
_HANDSHAKE_LINE = re.compile(r"(TLS 1\.[0-3]): (accepted|refused|unknown) - ")


def _link(page: str, item: str | None = None) -> dict:
    return {"page": page, "item": item}


def _box_link(key: str) -> dict:
    return _link(PAGE, key)


# ---------------------------------------------------------------- the files, read once


def _structure(lab: Any, import_id: int, fmt: str, data: bytes | None, sha256: str | None):
    """(the scanner file's structure or None, the one sentence that says why there is none)."""
    if fmt != "cyclonedx-cbom":
        return None, words.CSV_NOTE
    if data is None:
        return None, words.NO_COPY_NOTE
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        return None, words.COPY_CHANGED_NOTE
    cache = lab.__dict__.setdefault("_observatory_structures", {})  # an import's kept copy never changes
    if (import_id, digest) not in cache:
        try:
            cache[(import_id, digest)] = (S.read_structure(data), None)
        except ImportFileError as exc:
            cache[(import_id, digest)] = (None, words.unreadable_note(exc.message))
        except RecursionError:
            cache[(import_id, digest)] = (None, words.unreadable_note("This file is nested too deeply to read."))
    return cache[(import_id, digest)]


def _files(lab: Any, import_id: int) -> dict:
    with lab.db() as db:
        imp = db.get(ImportRow, import_id)
        if imp is None:
            raise NotFound("That import does not exist.")
        claims = [
            {
                "id": c.id,
                "ref": c.ref,
                "location": c.location,
                "location_kind": c.location_kind,
                "kind": c.kind,
                "claimed_value": c.claimed_value,
                "text": c.text,
                "source": c.source,
                "detail": dict(c.detail or {}),
            }
            for c in imp.claims
        ]
        kept = db.scalars(select(ImportFileRow).where(ImportFileRow.import_id == import_id)).first()
        data, sha256 = (bytes(kept.data), kept.sha256) if kept is not None else (None, None)
        row = db.scalars(
            select(DependencyListRow)
            .where(DependencyListRow.import_id == import_id)
            .order_by(DependencyListRow.id.desc())
            .limit(1)
        ).first()
        listed = (
            {"filename": row.filename, "at": iso(row.created_at), "parsed": dict(row.parsed or {})}
            if row is not None
            else None
        )
        info = {
            "id": imp.id,
            "filename": imp.filename,
            "format": imp.format,
            "is_demo": bool(imp.is_demo),
            "at": iso(imp.created_at),
        }
    structure, note = _structure(lab, import_id, info["format"], data, sha256)
    return {"scanner": info, "claims": claims, "structure": structure, "note": note, "listed": listed}


def _listed(files: dict, deps: dict | None) -> dict | None:
    """The dependency list as the layout takes it: what it describes, and Dependencies' own groups with their ties."""
    if files["listed"] is None or deps is None or deps.get("list_file") is None:
        return None
    dl = from_store(files["listed"]["parsed"])
    comp = dl.components.get(dl.described) if dl.described else None
    return {
        "described": (comp.name, comp.version) if comp is not None else None,
        "described_key": dl.described if comp is not None else None,
        "groups": deps.get("groups") or [],
        "dl": dl,
    }


def _read(lab: Any, import_id: int, plan_id: int | None, counts: bool = True) -> dict:
    """Everything one answer needs, read once: the files, the layout and the pages' own views. `counts`: the Checks
    view too, whose counts by tag the map shows (a box's panel shows no counts, and reads the rows of the same ledger
    without them)."""
    files = _files(lab, import_id)
    deps = lab.dependencies_view(plan_id, with_impact=False) if plan_id is not None else None
    listed = _listed(files, deps)
    got: dict = {
        "import_id": import_id,
        "plan_id": plan_id,
        "files": files,
        "deps": deps,
        "listed": listed,
        "layout": L.lay_out(files["claims"], files["structure"], listed),
        "verify": None,
        "lab": None,
        "checks": None,
        "migration": None,
    }
    try:
        got["verify"] = lab.latest_verify(import_id)
    except NotFound:
        pass
    if plan_id is not None:
        got["lab"] = lab.lab_view(plan_id)
        if counts:
            got["checks"] = lab.checks_view(plan_id)
        else:
            # Checks' own rows, each with the tag Checks gives it (the same rule on the same row)
            got["check_rows"] = {
                r["id"]: {**r, "source_tag": present_source.of_check_row(r)} for r in lab.ledger(plan_id)["rows"]
            }
        got["migration"] = migration_view_if_written(lab, plan_id)
    return got


# ---------------------------------------------------------------- each check, in the words of its own page


def _claim_checks(box: L.Box, got: dict) -> list[dict]:
    verify = got["verify"]
    if "verify_results" not in got:  # (read once for the map, not once for each box)
        found = (verify or {}).get("results") or []
        got["verify_results"] = {r.get("claim_id"): r for r in found if isinstance(r, dict)}
    results = got["verify_results"]
    table = words.SERVER_CLAIM_SPOT if box.kind == "server" else words.SOFTWARE_CLAIM_SPOT
    out = []
    for claim in box.claims:
        res = results.get(claim["id"])
        item = f"claim-{claim['id']}"
        check: dict = {
            "id": item,
            "kind": "claim",
            "spot": table.get(claim["kind"], "other"),
            "name": words.CLAIM_NAME,
            "says": words.claim_says(claim["kind"], claim["claimed_value"], claim["detail"]),
            "related_key": f"claim:{claim['id']}",
            "running": False,
            "came_from": None,
            "beside": [],
            "fix": None,
            "next": None,
        }
        if res is not None and res.get("result"):
            word = str(res["result"])
            check.update(
                word=word,
                tone=VERIFY_TONES.get(word, "warn"),
                code={"True": "true", "False": "false"}.get(word, "couldnt_check"),
                checked=True,
                tag=res.get("source_tag"),
                at=verify.get("finished_at"),
                plain=res.get("summary"),
                link=_link("inventory/verify", item),
                evidence_link=_link("evidence", item),
            )
        else:  # not verified yet: what the file says, as Import shows it
            check.update(
                word=words.NOT_CHECKED,
                tone=None,
                code=None,
                checked=False,
                tag=present_source.of_claim(got["files"]["scanner"]["filename"]),
                at=None,
                plain=claim["text"],
                link=_link("inventory/import", item),
                evidence_link=None,
            )
        out.append(check)
    return out


def _after_change(row: dict | None, result: dict) -> dict | None:
    """Checks' own row for this run, when the run is the measurement the app made right after an Apply or a Roll back
    (then the row says so, and carries that tag)."""
    if row is None or (row.get("came_from") or {}).get("key") not in _AFTER_CHANGE:
        return None
    return row if row.get("last_run_at") == result.get("finished_at") else None


def _shown(result: dict, row: dict | None) -> dict:
    """One reviewed run as Evidence words it: its word, its look, its sentence and its tag."""
    changed = _after_change(row, result)
    return {
        "word": result["label"],
        "tone": result["tone"],
        "code": result["code"],
        "tag": (changed or {}).get("source_tag") or result.get("source_tag"),
        "came_from": changed["came_from"]["label"] if changed else None,
        "at": result.get("finished_at"),
        "plain": result.get("plain"),
    }


def _test_checks(box: L.Box, got: dict) -> list[dict]:
    if "rows_of" not in got:  # Evidence's rows by the system each test is about (its own grouping), read once
        got["rows_of"] = {}
        for r in (got["lab"] or {}).get("rows") or []:
            got["rows_of"].setdefault(r.get("group"), []).append(r)
    rows = got["rows_of"].get(box.key, [])
    check_rows = _check_rows(got)
    table = words.SERVER_TEST_SPOT if box.kind == "server" else words.SOFTWARE_TEST_SPOT
    own = f"{box.name} {box.version}".strip() if box.name else None
    out = []
    for row in rows:
        item = f"test-{row['item_id']}"
        check: dict = {
            "id": item,
            "kind": "test",
            "spot": table.get(str(row.get("kind")), "other"),
            "name": row.get("title") or "",
            "says": None,
            "related_key": f"test:{row['item_id']}",
            "beside": [],
            "fix": None,
            "next": None,
        }
        result = row.get("result")
        if result:
            line = result.get("fix_line")
            check.update(
                **_shown(result, check_rows.get(item)),
                checked=True,
                running=False,
                link=_link("evidence", item),
                evidence_link=_link("evidence", item),
                fix=(
                    {
                        "text": f"{line['lead']} {line['rest']}".strip(),
                        "label": line.get("button") or words.LINK_FIX,
                        "link": _link("fixes", line["fix_id"]),
                    }
                    if line and line.get("fix_id")
                    else None
                ),
            )
        else:
            status = (row.get("result_status") or {}).get("status")
            check.update(
                word=words.NOT_CHECKED,
                tone=None,
                code=None,
                checked=False,
                running=status in ("waiting", "running"),
                tag=None,
                came_from=None,
                at=None,
                plain=None,
                link=_link("checks", item),
                evidence_link=None,
            )
        after = row.get("after")
        if after:
            # A retest ran on another version (or again on what it was): beside the first result, never in its place.
            shown = _shown(after, check_rows.get(f"retest-{row['item_id']}"))
            check["beside"].append(
                {
                    "label": shown["came_from"] or words.retest_label(after.get("component"), own),
                    **{k: shown[k] for k in ("word", "tone", "code", "tag", "at", "plain")},
                    "link": _link("evidence", item),
                }
            )
        out.append(check)
    return out


def _status_checks(box: L.Box, got: dict) -> list[dict]:
    """A system's post-quantum status, track by track, as the Migration plan words it (Measure status gives it; Run all
    does not)."""
    if not box.standing or box.system is None:
        return []
    system = next((s for s in (got["migration"] or {}).get("systems") or [] if s.get("key") == box.system), None)
    row = _check_rows(got).get(f"system-{box.system}")
    out = []
    for track in ("kex", "auth") if box.kind == "server" else ("signatures",):
        found = next((t for t in (system or {}).get("tracks") or [] if t.get("key") == track), None)
        code = (found or {}).get("status", {}).get("code") or "not_measured"
        measured = found is not None and code != "not_measured"
        check: dict = {
            "id": f"status-{track}",
            "kind": "status",
            "spot": words.TRACK_SPOT[track],
            "name": words.STATUS_NAME,
            "says": None,
            "track": track,
            "related_key": f"system:{box.system}",
            "running": bool(system and system.get("measuring")),
            "came_from": None,
            "beside": [],
            "fix": None,
            "link": _link("migration/systems", box.system),
        }
        if measured and found is not None and system is not None:
            check.update(
                word=found["status"]["label"],
                tone="warn" if code == "couldnt_check" else "neutral",
                code=code,
                checked=True,
                tag=system.get("source_tag"),
                at=(row or {}).get("last_run_at"),
                plain=found.get("sentence"),
                evidence_link=_link("evidence", f"system-{box.system}") if row else None,
                next=system.get("plan_line"),
            )
        else:
            check.update(
                word=words.NOT_MEASURED,
                tone=None,
                code=None,
                checked=False,
                tag=None,
                at=None,
                plain=None,
                evidence_link=None,
                next=None,
            )
        out.append(check)
    return out


def _check_rows(got: dict) -> dict[str, dict]:
    if "check_rows" not in got:
        got["check_rows"] = {r["id"]: r for g in (got["checks"] or {}).get("groups") or [] for r in g.get("rows") or []}
    return got["check_rows"]


def _one_tag(tags: list[dict | None]) -> dict | None:
    """Where every result rests on the same thing, that one tag (with the item's sentence only when all share it)."""
    found = [t for t in tags if t]
    if not found or len({t["key"] for t in found}) != 1:
        return None
    notes = {t.get("note") for t in found}
    return present_source.tag(found[0]["key"], notes.pop() if len(notes) == 1 else None)


def _tags_of(checks: list[dict]) -> list[dict | None]:
    return [t for c in checks for t in (c.get("tag"), *(b.get("tag") for b in c.get("beside") or []))]


def _spots(box: L.Box, got: dict) -> list[dict]:
    checks = _claim_checks(box, got) + _test_checks(box, got) + _status_checks(box, got)
    by_spot: dict[str, list[dict]] = {}
    for check in checks:
        by_spot.setdefault(check["spot"], []).append(check)
    spots = []
    for key in words.SERVER_SPOTS if box.kind == "server" else words.SOFTWARE_SPOTS:
        mine = by_spot.get(key)
        if not mine:
            continue
        claims = [c for c in mine if c["kind"] == "claim"]
        for c in claims:
            c["name"] = words.claim_name(c["says"], len(claims) == 1)
        said = [c["says"] for c in claims]
        any_checked = any(c["checked"] for c in mine)
        spots.append(
            {
                "key": key,
                "title": words.SPOT_TITLES[key],
                "file_says": words.file_says(said),
                "claimed": join_and(said) if said else None,
                "tag": None,
                "checked": any_checked,
                "empty_text": (
                    None
                    if any_checked
                    else words.NOT_MEASURED
                    if all(c["kind"] == "status" for c in mine)
                    else words.NOT_CHECKED
                ),
                "checks": mine,
            }
        )
    return spots


def _system_names(layout: L.Layout) -> list[str]:
    """The real names of what a top entry of the dependency list could be tied to: a server by the name its service has
    in the file (with its address where two servers share that name), a program by its name and version."""
    systems = layout.systems()
    shared: dict[str, int] = {}
    for b in systems:
        if b.kind == "server":
            shared[b.title] = shared.get(b.title, 0) + 1
    return [
        (b.title if shared[b.title] == 1 else f"{b.title} ({b.label})") if b.kind == "server" else b.label
        for b in systems
    ]


def _box(box: L.Box, got: dict) -> dict:
    """One box of the map, with its spots and tags. The checks keep everything the panel needs; `_public` trims them."""
    layout: L.Layout = got["layout"]
    spots = _spots(box, got)
    tag = _one_tag([t for s in spots for t in _tags_of(s["checks"])])
    if tag is None:
        for s in spots:
            s["tag"] = _one_tag(_tags_of(s["checks"]))
    note = None
    if box.kind == "own_software":
        if "not_tied" not in got:  # (the same sentence for every untied entry: worked out once)
            got["not_tied"] = words.not_tied(_system_names(layout))
        note = got["not_tied"]
    elif not spots:
        if "using" not in got:  # every box the file says uses an algorithm, worked out once for the map
            got["using"] = {use["box"] for algorithm in layout.algorithms for use in algorithm["uses"]}
        note = words.NOTHING_CHECKED_OF_IT if box.key in got["using"] else words.NO_CRYPTOGRAPHY_NAMED
    return {
        "key": box.key,
        "kind": box.kind,
        "title": box.title,
        "sub": words.box_sub(box.kind, box.address, box.files),
        "address": box.address,
        "in_files": list(box.files),
        "ties": [
            {"label": t["label"], "source": t["source"], "words": words.tie_words(t["label"], t["source"])}
            for t in box.ties
        ],
        "observed": any(c["checked"] for s in spots for c in s["checks"]),
        "note": note,
        "tag": tag,
        "spots": spots,
        "link": _box_link(box.key),
    }


_CHECK_KEYS = ("id", "kind", "name", "word", "tone", "code", "checked", "running", "came_from", "tag", "link")
_BESIDE_KEYS = ("label", "word", "tone", "code", "tag", "link")


def _public_check(check: dict, panel: bool) -> dict:
    out = {k: check.get(k) for k in _CHECK_KEYS}
    out["beside"] = [
        {**{k: b.get(k) for k in _BESIDE_KEYS}, **({"plain": b.get("plain"), "at": b.get("at")} if panel else {})}
        for b in check.get("beside") or []
    ]
    out["related_key"] = check["related_key"]
    if panel:
        out.update(plain=check.get("plain"), at=check.get("at"), fix=check.get("fix"), next=check.get("next"))
        out["links"] = check.get("links") or []
    return out


def _public_box(box: dict, panel: bool = False) -> dict:
    return {**box, "spots": [{**s, "checks": [_public_check(c, panel) for c in s["checks"]]} for s in box["spots"]]}


# ---------------------------------------------------------------- the cryptography lane and the lines


def _place_name(layout: L.Layout, key: str) -> tuple[str, bool]:
    box = layout.boxes.get(key)
    if box is not None:
        return box.label, box.kind == "server"
    container = next((c for c in layout.containers if c.key == key), None)
    return (_container_title(container) or key), False


def _container_title(container: L.Container | None) -> str | None:
    if container is None or container.title is None:
        return None
    return f"{container.title} {container.version}" if container.version else container.title


def _algorithms(layout: L.Layout) -> list[dict]:
    out = []
    for a in layout.algorithms:
        places = [words.use_words(u["through"], *_place_name(layout, u["box"])) for u in a["uses"]]
        out.append(
            {
                "key": a["key"],
                "kind_label": words.ALGORITHM_KIND,
                "plain": words.plain_name(a["technical"]),
                "technical": a["technical"],
                "named": words.ALGORITHM_NAMED,
                "used": words.used_in(list(dict.fromkeys(places))),
                "uses": [{"box": u["box"], "through": u["through"]} for u in a["uses"]],
            }
        )
    return out


def _library_row(row: dict) -> dict:
    return {
        "id": row["id"],
        "label": row["label"],
        "via_words": row.get("via_words") or "",
        "answers_short": row.get("answers_short") or "",
        # the tag Evidence gives the library's row, by the same rule (measured, else published, else only the list)
        "tag": present_source.of_answers(row.get("cells") or []),
        "link": _link("migration/dependencies", row["id"]),
    }


def _libraries(layout: L.Layout) -> list[dict]:
    out = []
    for group in layout.libraries:
        rows = [_library_row(r) for r in group["rows"]]
        n = len(rows)
        single = n == 1
        out.append(
            {
                "key": group["key"],
                "kind_label": words.LIBRARY_KIND if single else words.LIBRARIES_KIND,
                "title": rows[0]["label"] if single else words.libraries_title(group["top_label"], n),
                "sub": rows[0]["via_words"] if single else words.LIBRARIES_FROM,
                "owner": group["owner"],
                "count": n,
                "tag": _one_tag([r["tag"] for r in rows]),
                "rows": rows[:FIRST_FEW],
                "more": (
                    {
                        "count": n - FIRST_FEW,
                        "label": words.more_libraries(n - FIRST_FEW),
                        "link": _link("migration/dependencies"),
                        "link_label": words.MORE_LINK_LABEL,
                    }
                    if n > FIRST_FEW
                    else None
                ),
            }
        )
    return out


def _accepted_in_verify(verify: dict | None, address: str) -> tuple[str | None, list[str] | None]:
    """(when, the TLS versions the newest Verify run's recorded handshakes with this server show as accepted)."""
    if verify is None:
        return None, None
    for res in verify.get("results") or []:
        claim = res.get("claim") if isinstance(res, dict) else None
        if not isinstance(claim, dict) or claim.get("location") != address:
            continue
        states: dict[str, str] = {}
        for item in res.get("evidence") or []:
            title = str(item.get("title") or "") if isinstance(item, dict) else ""
            if not (title.startswith("TLS versions:") or "second try" in title):
                continue
            for line in str(item.get("output") or "").splitlines():
                m = _HANDSHAKE_LINE.match(line)
                if m:
                    states[m.group(1)] = m.group(2)  # (a second try's line comes later and stands)
        if states:
            return verify.get("finished_at"), [v for v in reversed(TLS_VERSIONS) if states.get(v) == "accepted"]
    return None, None


def _accepted_in_test(result: dict | None) -> tuple[str | None, list[str] | None]:
    """The same from one reviewed run of the Old TLS versions test: the table Evidence shows for it."""
    if result is None:
        return None, None
    for block in result.get("evidence") or []:
        rows = block.get("rows") if isinstance(block, dict) and block.get("type") == "table" else None
        if rows and all(len(r) == 3 and r[0] in TLS_VERSIONS for r in rows):
            return result.get("finished_at"), [r[0] for r in rows if r[2] == "accepted"]
    return None, None


def _seen(got: dict, box: L.Box) -> list[str] | None:
    """What the newest recorded handshakes with a server show: the TLS versions it accepted, or None when no record of
    this assessment lists them."""
    found = [_accepted_in_verify(got["verify"], str(box.address))]
    for row in (got["lab"] or {}).get("rows") or []:
        if row.get("group") == box.key and row.get("kind") == "tls_versions":
            found += [_accepted_in_test(row.get("result")), _accepted_in_test(row.get("after"))]
    newest: tuple[Any, list[str]] | None = None
    for at, seen in found:
        when = instant(at)
        if seen is not None and when is not None and (newest is None or when > newest[0]):
            newest = (when, seen)
    return newest[1] if newest is not None else None


def _lines(layout: L.Layout, boxes: dict[str, dict], got: dict) -> list[dict]:
    out = []
    groups = {g["key"]: g for g in layout.libraries}
    for line in layout.lines:
        if "libraries" in line:
            group = groups[line["to"]]
            via = group["rows"][0].get("via_words") if len(group["rows"]) == 1 else None
            label = words.libraries_line(line["libraries"], via)
        else:
            label = ", ".join(words.USE_LABELS.get(t, words.USES) for t in line["through"])
        out.append({"start": line["from"], "end": line["to"], "kind": "uses", "label": label})
    for box in layout.servers():
        shown = boxes[box.key]
        live = any((t or {}).get("key") == present_source.LIVE for s in shown["spots"] for t in _tags_of(s["checks"]))
        if live:
            out.append(
                {
                    "start": L.THIS_COMPUTER,
                    "end": box.key,
                    "kind": "live",
                    "label": words.live_label(_seen(got, box)),
                }
            )
        out.append({"start": L.CLIENTS, "end": box.key, "kind": "ask", "label": words.ASK_LABEL})
    return out


# ---------------------------------------------------------------- what the files don't say


def _gaps(layout: L.Layout) -> list[dict]:
    """The list under the map: what the files don't say, each with where it can be filled."""
    gaps: list[dict] = []
    servers = layout.servers()
    unanswered = [b.label for b in servers if b.key not in layout.answered]
    if unanswered:
        gaps.append(
            {
                "key": "software",
                "text": words.gap_software(unanswered, layout.untied, layout.listed),
                "link": _link("migration/dependencies"),
                "link_label": words.DEPENDENCIES_LABEL,
            }
        )
    if servers:
        gaps.append(
            {
                "key": "clients",
                "text": words.gap_clients([b.label for b in servers]),
                "link": None,
                "link_label": None,
            }
        )
    gaps.append({"key": "data_flows", "text": words.GAP_DATA_FLOWS, "link": None, "link_label": None})
    if layout.unplaced:
        gaps.append(
            {
                "key": "unplaced",
                "text": words.gap_unplaced([str(c.get("claimed_value") or "a claim") for c in layout.unplaced]),
                "link": _link("inventory/import"),
                "link_label": words.IMPORT_LABEL,
            }
        )
    if layout.containers[0].named == "unnamed_scanner":
        # (only a file whose structure was read can be said to name no service: a map drawn from the claims alone
        #  says so in its own sentence, and nothing about what the file names besides them)
        gaps.append({"key": "service", "text": words.GAP_NO_SERVICE, "link": None, "link_label": None})
    if not layout.listed:
        gaps.append(
            {
                "key": "libraries",
                "text": words.GAP_NO_LIST,
                "link": _link("migration/dependencies"),
                "link_label": words.DEPENDENCIES_LABEL,
            }
        )
    return gaps


# ---------------------------------------------------------------- the map


def _counts(got: dict, boxes: dict[str, dict]) -> list[dict]:
    """The four counts by tag. With a plan: the sum, over the four work groups, of the counts the Overview shows for
    each (`Lab.checks_view`), so the two pages agree. Without one (a file with no test plan yet): the claims and the
    systems of the file, each by its tag."""
    n = {k: 0 for k in present_source.KEYS}
    if got["checks"] is not None:
        for group in got["checks"].get("groups") or []:
            for entry in group.get("source_counts") or []:
                n[entry["key"]] += int(entry["count"])
    else:
        for box in boxes.values():
            for spot in box["spots"]:
                for check in spot["checks"]:
                    if check["kind"] == "claim" and check.get("tag"):
                        n[check["tag"]["key"]] += 1
        n[present_source.FILE] += sum(1 for b in got["layout"].boxes.values() if b.standing)
    return [
        {
            "key": k,
            "label": present_source.LABELS[k],
            "meaning": present_source.MEANINGS[k],
            "count": n[k],
            "line": words.COUNT_LINES[k],
        }
        for k in present_source.KEYS
    ]


def _newest(times: list[object]) -> str | None:
    """The newest of some recorded times, as it was recorded."""
    newest: tuple[Any, str] | None = None
    for t in times:
        when = instant(t)
        if when is not None and (newest is None or when > newest[0]):
            newest = (when, str(t))
    return newest[1] if newest is not None else None


def _built(got: dict) -> dict:
    """The filled map, before it is trimmed for the screen (the panel reads the same)."""
    if "built" in got:
        return got["built"]
    layout: L.Layout = got["layout"]
    boxes = {key: _box(box, got) for key, box in layout.boxes.items()}
    got["built"] = {"boxes": boxes, "lines": _lines(layout, boxes, got)}
    return got["built"]


def empty_view() -> dict:
    """An assessment with no file yet: nothing to draw, and the way to Import."""
    return {
        "plan_id": None,
        "import_id": None,
        "title": words.TITLE,
        "subline": words.SUBLINE,
        "state": "empty",
        "empty": {
            "text": words.EMPTY_TEXT,
            "link": _link("inventory/import"),
            "link_label": words.EMPTY_LINK_LABEL,
        },
        "banner": None,
        "counts": [
            {
                "key": k,
                "label": present_source.LABELS[k],
                "meaning": present_source.MEANINGS[k],
                "count": 0,
                "line": words.COUNT_LINES[k],
            }
            for k in present_source.KEYS
        ],
        "counts_note": words.COUNTS_NOTE,
        "map_title": words.MAP_TITLE,
        "built_from": [],
        "structure_note": None,
        "not_drawn": None,
        "outside": [],
        "services": [],
        "algorithms": [],
        "libraries": [],
        "libraries_note": None,
        "lines": [],
        "legend": words.LEGEND,
        "legend_note": words.LEGEND_NOTE,
        "gaps": {"title": words.GAPS_TITLE, "note": words.GAPS_NOTE, "items": []},
        "busy": False,
    }


def view(lab: Any, import_id: int, plan_id: int | None) -> dict:
    got = _read(lab, import_id, plan_id)
    layout: L.Layout = got["layout"]
    files = got["files"]
    built = _built(got)
    boxes = built["boxes"]
    checks = [c for b in boxes.values() for s in b["spots"] for c in s["checks"]]
    any_checked = any(c["checked"] for c in checks)
    live = any(line["kind"] == "live" for line in built["lines"])
    names = [files["scanner"]["filename"]] + ([files["listed"]["filename"]] if got["listed"] is not None else [])
    stamps = [files["scanner"]["at"]] + ([files["listed"]["at"]] if got["listed"] is not None else [])
    newest = _newest(stamps + [x.get("at") for c in checks for x in (c, *c["beside"])])
    services = []
    for container in layout.containers:
        services.append(
            {
                "key": container.key,
                "title": container.title,
                "version": container.version,
                "is_demo": files["scanner"]["is_demo"] if L.SCANNER in container.files else False,
                "sub": {
                    "both": words.SERVICE_BOTH,
                    "scanner": words.SERVICE_SCANNER,
                    "list": words.SERVICE_LIST,
                    "unnamed_scanner": words.SERVICE_UNNAMED,
                    "claims": words.SERVICE_CLAIMS,
                    "unnamed_list": words.LIST_UNNAMED,
                }[container.named],
                "in_files": list(container.files),
                "boxes": [_public_box(boxes[key]) for key in container.boxes],
            }
        )
    servers = layout.servers()
    return {
        "plan_id": plan_id,
        "import_id": import_id,
        "title": words.TITLE,
        "subline": words.SUBLINE,
        "state": "checked" if any_checked else "file_only",
        "empty": None,
        "banner": (
            None
            if any_checked
            else {
                "strong": words.BANNER_STRONG,
                "text": words.BANNER_TEXT,
                "link": _link("inventory/verify"),
                "link_label": words.BANNER_LINK_LABEL,
            }
        ),
        "counts": _counts(got, boxes),
        "counts_note": words.COUNTS_NOTE,
        "map_title": words.MAP_TITLE,
        "built_from": words.built_from(names, any_checked, newest, newest != files["scanner"]["at"]),
        "structure_note": files["note"],
        "not_drawn": words.not_drawn(layout.not_drawn) if layout.not_drawn else None,
        "outside": (
            [
                {"key": L.CLIENTS, "title": words.CLIENTS, "sub": words.CLIENTS_SUB},
                {
                    "key": L.THIS_COMPUTER,
                    "title": words.THIS_COMPUTER,
                    "sub": words.THIS_COMPUTER_SUB if live else words.THIS_COMPUTER_IDLE,
                },
            ]
            if servers
            else []
        ),
        "services": services,
        "algorithms": _algorithms(layout),
        "libraries": _libraries(layout),
        "libraries_note": (
            None
            if layout.listed
            else {
                "title": words.NO_LIST_TITLE,
                "sub": words.NO_LIST_SUB,
                "text": words.NO_LIST_TEXT,
                "link": _link("migration/dependencies"),
            }
        ),
        "lines": built["lines"],
        "legend": words.LEGEND,
        "legend_note": words.LEGEND_NOTE,
        "gaps": {
            "title": words.GAPS_TITLE,
            "note": words.GAPS_NOTE,
            "items": _gaps(layout),
        },
        "busy": bool(
            (got["lab"] or {}).get("busy")
            or (got["checks"] or {}).get("busy")
            or (got["migration"] or {}).get("busy")
            or (got["deps"] or {}).get("busy")
        ),
    }


# ---------------------------------------------------------------- one box, opened


def _file_lines(box: L.Box, got: dict) -> list[dict]:
    files = got["files"]
    structure: S.Structure | None = files["structure"]
    out = []
    found: list[tuple[str, str]] = []
    if structure is not None and box.part is not None:
        found += structure.lines.get(box.part, [])
        kind = S.TOP if structure.top is not None and structure.top.key == box.part else None
        places = [(kind or (S.SERVICE if box.kind in ("server", "service") else S.SOFTWARE), box.part)]
        if box.address:
            places.append((S.ADDRESS, box.address))
        for place in places:
            for asset in structure.reached.get(place, []):
                found += structure.lines.get(asset, [])[:1]  # each asset's own entry
    elif structure is not None and box.address:
        for asset in structure.reached.get((S.ADDRESS, box.address), []):
            found += structure.lines.get(asset, [])[:1]
    title = words.FILE_LINES_SCANNER
    if not found and L.SCANNER in box.files:
        title = words.CLAIMS_LINES
        found = [(str(c.get("source") or ""), str(c.get("text") or "")) for c in box.claims]
    found = list(dict.fromkeys(found))
    if found:
        out.append(
            {
                "title": title,
                "filename": files["scanner"]["filename"],
                "lines": [{"where": w, "text": t} for w, t in found[:MAX_FILE_LINES]],
                "more": max(0, len(found) - MAX_FILE_LINES),
            }
        )
    listed = got["listed"]
    tops = [t["top"] for t in box.ties] + ([box.top] if box.top else [])
    if listed is not None and tops:
        dl = listed["dl"]
        lines = []
        for key in tops:
            comp = dl.components.get(key)
            if comp is None:
                continue
            lines.append({"where": "components", "text": words.dependency_line(component_label(comp), comp.kind)})
            below = dl.edges.get(key) or []
            if below:
                lines.append(
                    {"where": "dependencies", "text": words.depends_on_line(component_label(comp), len(below))}
                )
        if lines:
            out.append(
                {
                    "title": words.FILE_LINES_LIST,
                    "filename": files["listed"]["filename"],
                    "lines": lines[:MAX_FILE_LINES],
                    "more": max(0, len(lines) - MAX_FILE_LINES),
                }
            )
    return out


def _box_gaps(box: L.Box, got: dict) -> list[dict]:
    layout: L.Layout = got["layout"]
    to_dependencies: dict[str, Any] = {
        "link": _link("migration/dependencies"),
        "link_label": words.DEPENDENCIES_LABEL,
    }
    nowhere: dict[str, Any] = {"link": None, "link_label": None}
    gaps: list[dict] = []
    if box.kind == "server":
        if box.key not in layout.answered:
            gaps.append(
                {
                    "key": "software",
                    "text": words.gap_software([box.label], layout.untied, layout.listed),
                    **to_dependencies,
                }
            )
        gaps.append({"key": "clients", "text": words.gap_clients_of(box.label), **nowhere})
    elif box.kind in ("program", "key_exchange_program", "software"):
        if box.ties and any(g["owner"] == box.key for g in layout.libraries):
            said = next(
                (
                    s.get("environment_line")
                    for s in (got["deps"] or {}).get("systems") or []
                    if s.get("key") == box.system and s.get("environment_line")
                ),
                None,
            )
            if said:  # Dependencies' own sentence about a system a top entry is tied to
                gaps.append({"key": "environment", "text": said, **to_dependencies})
        elif box.ties:
            gaps.append({"key": "libraries", "text": words.GAP_NO_LIBRARIES_LISTED, **to_dependencies})
        else:
            gaps.append({"key": "libraries", "text": words.gap_libraries(layout.listed), **to_dependencies})
        gaps.append({"key": "where", "text": words.GAP_WHERE_IT_RUNS, **nowhere})
    elif box.kind == "own_software":
        gaps.append({"key": "part_of", "text": words.gap_part_of(_system_names(layout)), **to_dependencies})
    return gaps


def _links(check: dict, fixes: list[dict]) -> list[dict]:
    """Where one check's result lives, and the fix that answers it where a recorded link says so."""
    out = []
    if check["kind"] == "claim":
        out.append({"label": words.LINK_CLAIM if check["checked"] else words.LINK_CLAIM_IMPORT, "link": check["link"]})
    elif check["kind"] == "test" and not check["checked"]:
        out.append({"label": words.LINK_TEST, "link": check["link"]})
    elif check["kind"] == "status":
        out.append({"label": words.LINK_SYSTEM, "link": check["link"]})
    if check.get("evidence_link"):
        out.append({"label": words.LINK_EVIDENCE, "link": check["evidence_link"]})
    for fix in fixes:
        out.append({"label": words.LINK_FIX, "link": fix["link"]})
    return out


def panel(lab: Any, import_id: int, plan_id: int | None, key: str) -> dict:
    got = _read(lab, import_id, plan_id, counts=False)
    layout: L.Layout = got["layout"]
    box = layout.boxes.get(key)
    if box is None:
        raise NotFound("That box is not on this map.")
    shown = _built(got)["boxes"][key]
    # The recorded links between items (the Related block's own). A box with no check and no system has none to read.
    linked = plan_id is not None and (box.system is not None or bool(shown["spots"]))
    graph = lab.relation_graph(plan_id) if linked else {"nodes": {}, "edges": {}, "alias": {}}

    def fixes_of(related_key: str) -> list[dict]:
        near = graph["edges"].get(graph["alias"].get(related_key, related_key), set())
        return [
            {"label": graph["nodes"][n]["label"], "sub": graph["nodes"][n]["sub"], "link": graph["nodes"][n]["link"]}
            for n in sorted(near)
            if graph["nodes"].get(n, {}).get("kind") == "fix"
        ]

    checks = [c for s in shown["spots"] for c in s["checks"]]
    for check in checks:
        # (a system's fixes are listed once for the box, not under each of its tracks)
        check["links"] = _links(check, fixes_of(check["related_key"]) if check["kind"] != "status" else [])
    related_key = f"system:{box.system}" if box.system else None
    fixes: dict[str, dict] = {}
    for found in [fixes_of(related_key)] if related_key else []:
        for fix in found:
            fixes.setdefault(str(fix["link"].get("item")), fix)
    for check in checks:
        for fix in fixes_of(check["related_key"]):
            fixes.setdefault(str(fix["link"].get("item")), fix)
    retests: dict[str, list[str]] = {}
    for check in checks:
        for beside in check["beside"]:
            retests.setdefault(beside["label"], []).append(beside["word"])
    stamps = [x.get("at") for c in checks if c["checked"] for x in (c, *c["beside"])]
    last = _newest(stamps)
    container = layout.container_of(box)
    library_groups = [g for g in _libraries(layout) if g["owner"] == key]
    return {
        "key": key,
        "kind_label": words.PANEL_KIND,
        "title": shown["title"],
        "sub": shown["sub"],
        "part_of": _container_title(container),
        "tag": shown["tag"],
        "last": (
            {"label": words.LAST_WORDS.get(str((shown["tag"] or {}).get("key")), "Last checked"), "at": last}
            if last
            else None
        ),
        "summary": words.summary(
            [c["word"] for c in checks if c["kind"] == "claim"],
            [c["word"] for c in checks if c["kind"] == "test"],
            [(words.TRACK_WORDS[c["track"]], c["word"]) for c in checks if c["kind"] == "status"],
            retests,
            box.kind == "server",
        ),
        "note": shown["note"],
        "ties": shown["ties"],
        "observed": shown["observed"],
        "spots": _public_box(shown, panel=True)["spots"],
        "libraries": library_groups,
        "fixes": list(fixes.values()),
        "gaps": {"title": words.BOX_GAPS_TITLE, "items": _box_gaps(box, got)},
        "file_lines": _file_lines(box, got),
        "related_key": related_key,
        "related": lab.related(plan_id, related_key, graph) if related_key and plan_id is not None else [],
        "link": _box_link(key),
    }


# ---------------------------------------------------------------- from a result back to the map


def place(lab: Any, import_id: int, plan_id: int | None, key: str) -> dict:
    """Where the item a panel is about sits on the map, by the key its Related block uses ("claim:3", "test:12",
    "system:server:localhost:8443", "library:row-2"); `place` is None when the item is not on the map."""
    kind, _, rest = key.partition(":")
    answer: dict = {"key": key, "place": None}
    if kind not in ("claim", "test", "system", "library") or not rest:
        return answer
    files = _files(lab, import_id)
    deps = lab.dependencies_view(plan_id, with_impact=False) if plan_id is not None else None
    layout = L.lay_out(files["claims"], files["structure"], _listed(files, deps))
    box: L.Box | None = None
    owner: str | None = None
    spot: str | None = None
    if kind == "claim":
        box = next((b for b in layout.boxes.values() if any(str(c["id"]) == rest for c in b.claims)), None)
        claim = next((c for c in (box.claims if box else []) if str(c["id"]) == rest), None)
        if box is not None and claim is not None:
            table = words.SERVER_CLAIM_SPOT if box.kind == "server" else words.SOFTWARE_CLAIM_SPOT
            spot = table.get(claim["kind"], "other")
    elif kind == "test" and plan_id is not None:
        test = next((t for t in lab.plan_view(plan_id).get("tests") or [] if str(t.get("id")) == rest), None)
        box = layout.boxes.get(str(test.get("group"))) if test else None
        if box is not None and test is not None:
            table = words.SERVER_TEST_SPOT if box.kind == "server" else words.SOFTWARE_TEST_SPOT
            spot = table.get(str(test.get("kind")), "other")
    elif kind == "system":
        box = next((b for b in layout.boxes.values() if b.system == rest), None)
    elif kind == "library":
        group = next((g for g in layout.libraries if any(r.get("id") == rest for r in g["rows"])), None)
        if group is not None:
            owner = group["owner"]
            box = layout.boxes.get(str(owner))
            spot = "libraries"
    if box is None and owner is None:
        return answer
    container = layout.container_of(box) if box is not None else next(c for c in layout.containers if c.key == owner)
    path = [_container_title(container), box.title if box is not None else None]
    path.append(words.LIBRARIES_KIND if spot == "libraries" else words.SPOT_TITLES[spot] if spot else None)
    answer["place"] = {
        "label": words.PLACE_LABEL,
        "path": [p for p in path if p],
        "box": box.key if box is not None else None,
        "link": _link(PAGE, box.key if box is not None else None),
        "link_label": words.PLACE_LINK_LABEL,
    }
    return answer


# ---------------------------------------------------------------- by plan, by assessment


def import_of(lab: Any, plan_id: int) -> int:
    with lab.db() as db:
        plan = db.get(PlanRow, plan_id)
        if plan is None:
            raise NotFound("That test plan does not exist.")
        return int(plan.import_id)


def view_of_plan(lab: Any, plan_id: int) -> dict:
    return view(lab, import_of(lab, plan_id), plan_id)


def view_of_assessment(lab: Any, assessment_id: int) -> dict:
    """The same map by the assessment: also before it has a file (nothing to draw, and the way to Import), and before
    its test plan was made (the file's claims, nothing checked)."""
    core = lab.assessment_core(assessment_id)
    if core.get("import_id") is None:
        return empty_view()
    return view(lab, int(core["import_id"]), core.get("plan_id"))


def panel_of_plan(lab: Any, plan_id: int, key: str) -> dict:
    return panel(lab, import_of(lab, plan_id), plan_id, key)


def place_of_plan(lab: Any, plan_id: int, key: str) -> dict:
    return place(lab, import_of(lab, plan_id), plan_id, key)


__all__ = [
    "empty_view",
    "import_of",
    "panel",
    "panel_of_plan",
    "place",
    "place_of_plan",
    "view",
    "view_of_assessment",
    "view_of_plan",
]

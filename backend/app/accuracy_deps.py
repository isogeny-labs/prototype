"""Accuracy check, fourth part (phase 4d): the dependency lists against demo/expected-dependencies.json.

Called by `python -m app.accuracy` (or alone with `--only dependencies`). It goes down the same path as the buttons,
on a scratch data folder: the Acme Pay demo file, Measure status in the Migration step, Add dependency list
(demo/dependencies-demo.cdx.json), "Part of" for acme-pay-server 1.0.0 (the demo server, localhost:8443), Measure
all in isolated mode, then the Migration step, the Fixes view and the evidence part again; each broken file of
demo/dependencies-broken/; the SPDX copy (it must give the same answers); and the real Syft file of the lab nginx
image with demo/lab-nginx.csv, graded by the key's rule.

In demo mode the lookups, ties, blockers and Fixes entries are graded, and every measurement must read Couldn't
check (needs isolated mode). In isolated mode the measurements are graded too. It only READS the answer key."""

from __future__ import annotations

import dataclasses
import json
import re
import tempfile
from pathlib import Path

from app.config import DEMO_DIR, Settings, load_settings
from app.importer.common import ImportFileError
from app.importer.sbom import READ
from app.knowledge.base import knowledge_base, purl_base
from app.knowledge.versions import at_least, read_version
from app.lab.hub import Lab

EXPECTED_DEPS_JSON = DEMO_DIR / "expected-dependencies.json"  # the answer key: read-only, never written by the app
CDX_FILE = DEMO_DIR / "dependencies-demo.cdx.json"
SPDX_FILE = DEMO_DIR / "dependencies-demo.spdx.json"
SYFT_FILE = DEMO_DIR / "dependencies-nginx-image.syft.cdx.json"
BROKEN_DIR = DEMO_DIR / "dependencies-broken"
LAB_NGINX_FILE = DEMO_DIR / "lab-nginx.csv"
WAIT_SECONDS = 900.0
QUESTIONS = ("ml_kem_768", "x25519mlkem768", "ml_dsa_65")
TRACK_KEYS = {"key_exchange": "kex", "authentication": "auth", "signatures": "signatures"}
PAY_TOP = "acme-pay-server 1.0.0"
OPENSSL_FIRST = "3.5.0"


def _flat(parts) -> str:
    if isinstance(parts, str):
        return parts
    if isinstance(parts, dict):
        return _flat(parts.get("text") or "")
    return "".join(str(p.get("v", "")) if isinstance(p, dict) else str(p) for p in (parts or []))


# ---------------------------------------------------------------- what the app shows, read the way a person reads it


def _snapshot(lab: Lab, pid: int) -> dict:
    """The Dependencies view, the evidence part (lookups as they were recorded), the Migration step and the Fixes view."""
    view = lab.dependencies_view(pid)
    with lab.db() as db:
        part = lab._dependencies_export(db, lab._plan(db, pid)) or {}
    lookups = {
        f"{r['name']} {r['version']}".strip() if r.get("version") else r["name"]: {
            q: a["lookup"] for q, a in r["answers"].items()
        }
        for r in part.get("rows") or []
    }
    rows = {}
    for g in view["groups"]:
        for r in g["rows"]:
            rows[r["label"]] = {
                "under": g["label"],
                "via": r["via_words"],
                "blocks": sorted((b["system"], b["track"]) for b in r["blocks"]),
                "cells": {
                    c["question"]: {k: c[k] for k in ("answer", "label", "state", "first_version", "agreement")}
                    for c in r["cells"]
                },
                "controls": (r["measurement"] or {}).get("controls"),
                "same_copy": r["same_copy_note"] is not None,
                "lookup": lookups.get(r["label"], {}),
            }
    tops = [
        {
            "label": g["label"],
            "system": g["system"],
            "tie_source": g["tie_source"],
            "rows": [r["label"] for r in g["rows"]],
        }
        for g in view["groups"]
    ]
    names = {o["key"]: o["name"].split(": ", 1)[-1] for g in view["groups"] for o in g["picker"]["options"] if o["key"]}
    systems = {
        s["name"]: {"key": s["key"], "without_answer": s["without_answer"], "blockers": s["blockers"]}
        for s in part.get("systems") or []
    }
    fixes = [f for f in lab.fixes_view(pid)["fixes"] if f["id"].startswith("dependency-")]
    fix_words = []
    for f in fixes:
        where = next((x["suggestion"]["where"] for x in f["sections"] if x.get("key") == "suggestion"), None) or {}
        fix_words.append(
            {
                "title": f["title"],
                "list_source": f["list_source"],
                "links": [row["code"] for row in where.get("rows") or []],
            }
        )
    migration = lab.migration_view(pid)
    tracks = {(s["name"], t["key"]): _flat(t["next"]) for s in migration["systems"] for t in s.get("tracks") or []}
    roadmap = {
        (row["name"], row["track"]): {"band": band["key"], "note": _flat(row["note"])}
        for band in migration["roadmap"]["bands"]
        for row in band["rows"]
    }
    return {
        "list": view["list_file"],
        "rows": rows,
        "tops": tops,
        "names": names,
        "systems": systems,
        "fixes": fix_words,
        "tracks": tracks,
        "roadmap": roadmap,
    }


def _tie_pay_server(lab: Lab, pid: int, address: str) -> None:
    """What the person does with "Part of": acme-pay-server 1.0.0 is the demo server."""
    view = lab.dependencies_view(pid)
    top = next(g["key"] for g in view["groups"] if g["label"] == PAY_TOP)
    lab.tie_dependency(pid, top, f"server:{address}")


def _measure(lab: Lab, pid: int) -> None:
    if lab.mode.name == "isolated":
        lab.measure_dependencies(pid)
        lab.wait_until_dependencies_measured(pid, WAIT_SECONDS)


def collect_dependencies(settings: Settings | None = None, say=None) -> dict:
    settings = settings or load_settings()
    progress = say or (lambda text: None)
    out: dict = {
        "mode": None,
        "mode_line": None,
        "notes": [],
        "stopped": None,
        "address": settings.demo_address,
        "before": {},
        "cdx": None,
        "spdx": None,
        "broken": {},
        "broken_list_kept": {},
        "syft": None,
    }
    with tempfile.TemporaryDirectory(prefix="evidence-lab-accuracy-") as scratch:
        lab = Lab(dataclasses.replace(settings, data_dir=Path(scratch) / "data"), allow_external_demo_server=True)
        lab.start()
        try:
            out["mode"], out["mode_line"] = lab.mode.name, lab.mode.line
            imp = lab.import_demo()
            for address in imp["addresses"]:
                lab.confirm_address(imp["id"], address["address"], True)
            pid = lab.ensure_plan(imp["id"])["id"]
            progress("  ... Measure status (Migration), before any dependency list")
            lab.measure_migration(pid)
            lab.wait_until_measured(pid, WAIT_SECONDS)
            out["before"] = {f"{k[0]}|{k[1]}": v for k, v in _snapshot_roadmap(lab, pid).items()}
            progress("  ... Add dependency list (CycloneDX), Part of, Measure all")
            lab.add_dependency_list(pid, CDX_FILE.name, CDX_FILE.read_bytes())
            _tie_pay_server(lab, pid, settings.demo_address)
            _measure(lab, pid)
            out["cdx"] = _snapshot(lab, pid)
            for path in sorted(BROKEN_DIR.glob("*.json")):
                try:
                    lab.add_dependency_list(pid, path.name, path.read_bytes())
                    out["broken"][path.name] = None
                except ImportFileError as exc:
                    out["broken"][path.name] = str(exc)
                out["broken_list_kept"][path.name] = lab.dependencies_view(pid)["list_file"] == out["cdx"]["list"]
            progress("  ... the SPDX copy")
            lab.add_dependency_list(pid, SPDX_FILE.name, SPDX_FILE.read_bytes())
            _tie_pay_server(lab, pid, settings.demo_address)
            _measure(lab, pid)
            out["spdx"] = _snapshot(lab, pid)
            progress("  ... the real Syft file of the lab nginx image")
            nginx = lab.import_file(LAB_NGINX_FILE.name, LAB_NGINX_FILE.read_bytes())
            n_pid = lab.ensure_plan(nginx["id"])["id"]
            view = lab.add_dependency_list(n_pid, SYFT_FILE.name, SYFT_FILE.read_bytes())
            with lab.db() as db:
                part = lab._dependencies_export(db, lab._plan(db, n_pid)) or {}
            out["syft"] = {
                "format": view["list_file"]["format"],
                "rows": [
                    {
                        "name": r["name"],
                        "version": r["version"],
                        "purl": r["purl"],
                        "answers": {
                            q: {k: a[k] for k in ("answer", "label", "first_version")} for q, a in r["answers"].items()
                        },
                    }
                    for r in part.get("rows") or []
                ],
            }
        except Exception as exc:  # shown, never hidden: every answer not reached counts as a mismatch
            out["stopped"] = f"The check stopped early: {str(exc) or exc.__class__.__name__}"
        finally:
            lab.stop()
    return out


def _snapshot_roadmap(lab: Lab, pid: int) -> dict:
    migration = lab.migration_view(pid)
    return {(row["name"], row["track"]): band["key"] for band in migration["roadmap"]["bands"] for row in band["rows"]}


# ---------------------------------------------------------------- comparing (pure: no app, no files)


def _library_matches(key_text: str, label: str) -> bool:
    """The key names a library as text: "openssl 3.0.x (Debian's build ...)", "boringssl <commit id>", "Go standard library devel"."""
    text = re.sub(r"\s*\(.*\)\s*$", "", key_text).strip()
    if "<" in text:
        name = text.split("<", 1)[0].strip()
        return label.startswith(name + " ") and re.fullmatch(r"[0-9a-f]{40}", label[len(name) + 1 :]) is not None
    name, _, version = text.rpartition(" ")
    if version.endswith(".x"):
        return label.startswith(f"{name} {version[:-1]}") and read_version(label[len(name) + 1 :]) is not None
    return label == text


def _all_three(value) -> dict:
    """{question: value} from the key's dict, or from "<value> on all three" / a single value."""
    if isinstance(value, dict):
        return dict(value)
    text = str(value).replace(" on all three", "").strip()
    return {q: text for q in QUESTIONS}


def _first_word(text: str) -> str:
    return str(text).split(" ", 1)[0]


def compare_dependencies(expected: dict, answers: dict) -> dict:
    lines: list[dict] = []
    mode = answers.get("mode") or "demo"
    isolated = mode == "isolated"

    def add(id_: str, what: str, want: object, got: object, match: bool, why: str = "") -> None:
        lines.append({"id": id_, "what": what, "expected": want, "actual": got, "match": bool(match), "why": why})

    cdx = answers.get("cdx") or {
        "rows": {},
        "tops": [],
        "systems": {},
        "fixes": [],
        "tracks": {},
        "roadmap": {},
        "names": {},
    }
    rows = cdx["rows"]
    ids: dict[str, str | None] = {}
    for spec in expected.get("rows") or []:
        ids[spec["id"]] = next((label for label in rows if _library_matches(spec["library"], label)), None)

    # ---- the top entries and their ties
    for n, top in enumerate((expected.get("demo_list") or {}).get("top_entries") or []):
        got = next((t for t in cdx["tops"] if t["label"] == top["name"]), None)
        add(f"T{n + 1}", f"top entry {top['name']}", "shown", "shown" if got else "missing", got is not None)
        if got is None:
            continue
        tie = top["tie"]
        if tie.startswith("tied by name and version"):
            ok, said = (
                got["tie_source"] == "name_version" and got["system"] is not None,
                f"{got['tie_source']} -> {got['system']}",
            )
        elif tie.startswith("untied"):
            ok, said = got["system"] is None, str(got["system"])
        else:
            want_address = tie.split(",", 1)[0]
            ok = (
                got["tie_source"] == "user"
                and cdx["names"].get(got["system"] or "") == answers.get("address") == want_address
            )
            said = f"{got['tie_source']} -> {cdx['names'].get(got['system'] or '')}"
        add(f"T{n + 1}", f"{top['name']}: Part of", tie, said, ok)
        want_rows = [ids.get(i) for i in top["libraries"]]
        add(f"T{n + 1}", f"{top['name']}: its libraries", top["libraries"], got["rows"], got["rows"] == want_rows)

    # ---- every row
    specs = {s["id"]: s for s in expected.get("rows") or []}
    for spec in expected.get("rows") or []:
        rid = spec["id"]
        if spec.get("same_as"):
            spec = {
                **specs[spec["same_as"]],
                "id": rid,
                "library": spec["library"],
                "under": spec.get("under"),
                "via": spec.get("via"),
            }
        label = ids.get(rid)
        row = rows.get(label or "")
        add(rid, f"{spec['library']}: in the list", "a row", label or "missing", row is not None)
        if row is None:
            continue
        if spec.get("under"):
            add(rid, f"{label}: under", spec["under"], row["under"], row["under"] == spec["under"])
        if spec.get("via"):
            add(rid, f"{label}: how it got there", spec["via"], row["via"], row["via"] == spec["via"])
        want_lookup = _all_three(spec["lookup"])
        for q in QUESTIONS:
            got_q = row["lookup"].get(q) or {}
            add(
                rid, f"{label}: lookup, {q}", want_lookup[q], got_q.get("answer"), got_q.get("answer") == want_lookup[q]
            )
            if want_lookup[q] in ("yes", "no"):
                add(
                    rid,
                    f"{label}: lookup label, {q}",
                    spec.get("lookup_label"),
                    got_q.get("label"),
                    got_q.get("label") == spec.get("lookup_label"),
                )
            if isinstance(spec.get("first_version"), dict):
                want = spec["first_version"][q]
                add(
                    rid,
                    f"{label}: lookup first version, {q}",
                    want,
                    got_q.get("first_version"),
                    got_q.get("first_version") == want,
                )
        cells = row["cells"]
        if spec.get("state_both_modes"):
            want = _all_three(spec["state_both_modes"])
            for q in QUESTIONS:
                add(rid, f"{label}: state, {q}", want[q], cells[q]["state"], cells[q]["state"] == want[q])
        if not isolated and spec.get("demo_mode"):
            want = _all_three(spec["demo_mode"]["state"])
            for q in QUESTIONS:
                add(rid, f"{label}: state in demo mode, {q}", want[q], cells[q]["state"], cells[q]["state"] == want[q])
        if not isolated and spec.get("demo_mode") or spec.get("state_both_modes"):
            for q in QUESTIONS:  # without a measurement the shown answer is the lookup's
                add(
                    rid,
                    f"{label}: shown answer, {q}",
                    want_lookup[q],
                    cells[q]["answer"],
                    cells[q]["answer"] == want_lookup[q],
                )
        if isolated and spec.get("isolated_mode"):
            iso = spec["isolated_mode"]
            want_answer = _all_three(iso["answer"])
            want_state = (
                _all_three(iso["state"].replace("measured on all three", "measured"))
                if isinstance(iso["state"], str)
                else iso["state"]
            )
            labels = iso["label"] if isinstance(iso["label"], dict) else {q: iso["label"] for q in QUESTIONS}
            for q in QUESTIONS:
                c = cells[q]
                add(rid, f"{label}: answer, {q}", want_answer[q], c["answer"], c["answer"] == want_answer[q])
                add(rid, f"{label}: state, {q}", want_state[q], c["state"], c["state"] == want_state[q])
                if want_answer[q] in ("yes", "no"):
                    add(rid, f"{label}: label, {q}", labels[q], c["label"], c["label"] == labels[q])
                if iso.get("first_version") and want_answer[q] == "no":
                    add(
                        rid,
                        f"{label}: first version, {q}",
                        iso["first_version"],
                        c["first_version"],
                        c["first_version"] == iso["first_version"],
                    )
            controls = str(iso.get("controls") or "")
            add(
                rid,
                f"{label}: controls",
                _first_word(controls),
                row["controls"],
                row["controls"] == _first_word(controls),
            )
            if "same copy" in controls:
                add(
                    rid,
                    f"{label}: says one control is this same copy",
                    True,
                    row["same_copy"],
                    row["same_copy"] is True,
                )
            agreement = iso.get("agreement")
            if isinstance(agreement, dict):
                for q, want in agreement.items():
                    add(rid, f"{label}: agreement, {q}", want, cells[q]["agreement"], cells[q]["agreement"] == want)
            elif agreement:
                add(
                    rid,
                    f"{label}: agreement",
                    "none",
                    [cells[q]["agreement"] for q in QUESTIONS],
                    all(cells[q]["agreement"] is None for q in QUESTIONS),
                )
        want_blocks = sorted((b["system"], TRACK_KEYS[b["track"]]) for b in spec.get("blocks") or [])
        add(rid, f"{label}: blocks", want_blocks, row["blocks"], row["blocks"] == want_blocks)

    # ---- the label rule
    used = {c["label"] for r in rows.values() for c in r["cells"].values()} | {
        b.get("answer_label") for s in cdx["systems"].values() for bs in s["blockers"].values() for b in bs
    }
    add(
        "L1",
        "the label 'your_environment' is never produced",
        "never",
        sorted(str(x) for x in used),
        "your_environment" not in used and not (used - {None, "release_notes", "public_copy"}),
    )

    # ---- per system
    want_label = "public_copy" if isolated else "release_notes"
    for n, s in enumerate(expected.get("per_system") or []):
        sid, name = f"P{n + 1}", s["system"]
        got = cdx["systems"].get(name)
        add(sid, f"{name}: tied to the list", "tied", "tied" if got else "not tied", got is not None)
        if got is None:
            continue
        for track_name, want in (s.get("dependency_blockers") or {}).items():
            track = TRACK_KEYS[track_name]
            found = got["blockers"].get(track, [])
            if not want:
                add(sid, f"{name}: {track_name} blockers from the list", [], [b["label"] for b in found], not found)
                continue
            if want == ["the same library"]:
                kex = got["blockers"].get("kex", [])
                ok = len(found) == 1 and bool(kex) and found[0]["row_key"] == kex[0]["row_key"]
                add(sid, f"{name}: {track_name} blocker", "the same library", [b["label"] for b in found], ok)
                continue
            text = want[0]
            lib = text.split(",", 1)[0]
            ok = (
                len(found) == 1
                and _library_matches(lib, found[0]["label"])
                and found[0]["via"] == [x.strip() for x in text.split(",")[1].replace("through", "").split(" then ")]
                and found[0]["answer_label"] == want_label
                and found[0]["first_version"] == OPENSSL_FIRST
            )
            got_text = [
                f"{b['label']}, via {b['via']}, {b['answer_label']}, {b['first_version']} or later" for b in found
            ]
            add(sid, f"{name}: {track_name} blocker", f"{lib}, {want_label}, {OPENSSL_FIRST} or later", got_text, ok)
        if "roadmap_band" in s:
            for track in ("Key exchange", "Authentication"):
                before = (answers.get("before") or {}).get(f"{name}|{track}")
                after = cdx["roadmap"].get((name, track)) or {}
                add(
                    sid,
                    f"{name}: roadmap band, {track}",
                    "unchanged (phase2)",
                    f"{before} -> {after.get('band')}",
                    before == after.get("band") == "phase2",
                )
                blocker = (got["blockers"].get("kex") or [{}])[0].get("label", "?")
                add(
                    sid,
                    f"{name}: roadmap note names the blocker, {track}",
                    blocker,
                    after.get("note"),
                    blocker in str(after.get("note")) and OPENSSL_FIRST in str(after.get("note")),
                )
        mine = [f for f in cdx["fixes"] if f["list_source"] == f"Dependencies: {name}"]
        if "fixes" in s:
            openssl_file = knowledge_base().files.get("openssl")
            urls = {c.source.url for c in openssl_file.claims} if openssl_file else set()
            want = [f"Update OpenSSL to {f['update_to']} or later" for f in s["fixes"]]
            add(
                sid,
                f"{name}: Fixes entries from the list",
                want,
                [f["title"] for f in mine],
                [f["title"] for f in mine] == want,
            )
            add(
                sid,
                f"{name}: the Fixes entry links the official source",
                "the OpenSSL release notes",
                [link for f in mine for link in f["links"]],
                bool(mine) and all(set(f["links"]) and set(f["links"]) <= urls for f in mine),
            )
        if "fixes_added" in s:
            add(sid, f"{name}: Fixes entries from the list", s["fixes_added"], len(mine), len(mine) == s["fixes_added"])
        if "libraries_without_answer" in s:
            add(
                sid,
                f"{name}: libraries without an answer",
                s["libraries_without_answer"],
                got["without_answer"],
                got["without_answer"] == s["libraries_without_answer"],
            )
        if "note" in s:  # its own blocker (it can't make post-quantum signatures) stays as today
            note = (cdx["roadmap"].get((name, "Signatures")) or {}).get("note", "")
            add(
                sid,
                f"{name}: its own blocker stays",
                "can't make post-quantum signatures",
                note,
                "can't make post-quantum signatures" in note,
            )

    # ---- the SPDX copy: the same answers for every row, tie, blocker and Fixes entry
    spdx = answers.get("spdx") or {"rows": {}, "tops": [], "systems": {}, "fixes": []}

    def project(snap: dict) -> dict:
        return {
            "rows": dict(snap["rows"]),
            "tops": [
                {k: v for k, v in t.items() if k != "system"} | {"system": snap.get("names", {}).get(t["system"] or "")}
                for t in snap["tops"]
            ],
            "blockers": {
                n: {
                    t: [(b["label"], b["answer_label"], b["first_version"]) for b in bs]
                    for t, bs in s["blockers"].items()
                }
                for n, s in snap["systems"].items()
            },
            "fixes": sorted((f["title"], f["list_source"], tuple(f["links"])) for f in snap["fixes"]),
        }

    a, b = project(cdx), project(spdx)
    for part in ("rows", "tops", "blockers", "fixes"):
        if isinstance(a[part], dict):
            differ = sorted(k for k in set(a[part]) | set(b[part]) if a[part].get(k) != b[part].get(k))
        else:
            differ = [b[part]]
        add(
            "S1",
            f"the SPDX copy gives the same {part}",
            "the same",
            "the same" if a[part] == b[part] else f"differs: {differ}",
            a[part] == b[part] and bool(a[part]),
        )

    # ---- the broken files
    for name, message in sorted((answers.get("broken") or {}).items()):
        one = (
            message is not None
            and message.endswith(READ)
            and message[: -len(READ)].strip().count(". ") == 0
            and "\n" not in message
        )
        add("B1", f"{name}: refused with one plain sentence", "refused", message, one)
        add(
            "B1",
            f"{name}: the earlier list stays",
            True,
            answers["broken_list_kept"].get(name),
            answers["broken_list_kept"].get(name) is True,
        )
    if not answers.get("broken"):
        add("B1", "the broken files", "each refused", "none was tried", False)

    # ---- the real Syft file, by rule
    syft = answers.get("syft")
    kb = knowledge_base()
    openssl = kb.files.get("openssl")
    openssl_purls = {p.purl.lower() for p in openssl.packages} if openssl else set()
    cross = None
    if not syft:
        add("R1", "the real Syft file", "read", "not read", False)
    else:
        add("R1", "the real Syft file: format", "CycloneDX 1.6", syft["format"], syft["format"] == "CycloneDX 1.6")
        n_ok = n_open = n_other = 0
        wrong = []
        for r in syft["rows"]:
            base = purl_base(r["purl"])
            is_openssl = base in openssl_purls or (r["name"] or "").lower() == "openssl"
            v = read_version(r["version"])
            if is_openssl:
                n_open += 1
                want = "yes" if v is not None and at_least(v, OPENSSL_FIRST) else "no"
                ok = all(
                    r["answers"][q]["answer"] == want
                    and r["answers"][q]["label"] == "release_notes"
                    and (r["answers"][q]["first_version"] == (OPENSSL_FIRST if want == "no" else None))
                    for q in QUESTIONS
                )
                if want == "no" and r["answers"]["x25519mlkem768"]["answer"] == "no":
                    cross = "disagree"
                elif cross is None:
                    cross = "agree"
            elif kb.find(r["purl"], r["name"]) is None:
                n_other += 1
                ok = all(r["answers"][q]["answer"] == "not_in_knowledge_base" for q in QUESTIONS)
            else:
                ok = True  # a recognised one on the seed list follows its own claims (reported, not graded)
            n_ok += ok
            if not ok:
                wrong.append(f"{r['name']} {r['version']}")
        add(
            "R1",
            "the real Syft file: every row follows the rule",
            f"{len(syft['rows'])} rows by rule",
            f"{n_ok} of {len(syft['rows'])} ({n_open} OpenSSL packages, {n_other} not in the knowledge base)"
            + (f"; wrong: {wrong[:5]}" if wrong else ""),
            n_ok == len(syft["rows"]) and n_open > 0,
        )
        add(
            "R2",
            "cross-check with phase 4b (lab nginx localhost:8461 completed a measured hybrid handshake)",
            "the list and the measurement agree, or the report says they disagree and the measurement wins",
            {
                "agree": "agree: the list's OpenSSL lookup says yes to X25519MLKEM768",
                "disagree": "DISAGREE: the list's OpenSSL lookup says no to X25519MLKEM768; the measurement wins",
            }.get(cross or "", "no OpenSSL package"),
            cross in ("agree", "disagree"),
        )
    return {
        "lines": lines,
        "matched": sum(1 for line in lines if line["match"]),
        "total": len(lines),
        "isolated": isolated,
        "cross_check": cross,
    }


def print_dependencies_report(settings: Settings | None, say=print) -> int:
    """The dependency lists against demo/expected-dependencies.json. Exit code 0 only if the key is there and all match."""
    say("")
    say(
        "Dependencies accuracy check against demo/expected-dependencies.json (lookups, measurements, ties, blockers, Fixes, "
        "the SPDX copy, the broken files, the real Syft file)"
    )
    answers = collect_dependencies(settings, say)
    if answers.get("mode_line"):
        say(f"  mode: {answers['mode_line']}")
    for note in answers["notes"]:
        say(f"  note: {note}")
    if answers["stopped"]:
        say(f"  PROBLEM  {answers['stopped']}")
    if not EXPECTED_DEPS_JSON.exists():
        say(
            "  NOT COMPARED  demo/expected-dependencies.json is not in this copy of the repository, so there is nothing to compare with."
        )
        say("Dependencies accuracy: not compared (answer key missing)")
        return 2
    try:
        expected = json.loads(EXPECTED_DEPS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        say(f"  PROBLEM  the answer key could not be read ({exc.__class__.__name__}).")
        return 1
    report = compare_dependencies(expected, answers)
    for line in report["lines"]:
        say(
            f"  {line['id']:<4} {'MATCH   ' if line['match'] else 'MISMATCH'}  expected {line['expected']!r}, app says {line['actual']!r}  -  {line['what']}"
        )
        if line["why"]:
            say(f"        {line['why']}")
    say(
        f"Dependencies accuracy ({'isolated' if report['isolated'] else 'demo'} mode): {report['matched']} of {report['total']} match"
    )
    return 0 if report["matched"] == report["total"] and not answers["stopped"] else 1


__all__ = ["collect_dependencies", "compare_dependencies", "print_dependencies_report", "EXPECTED_DEPS_JSON"]

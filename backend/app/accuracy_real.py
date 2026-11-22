"""Accuracy check, third half (phase 4c): the real libraries against demo/expected-real-libraries.json.

Called by `python -m app.accuracy` (or alone with `--only real`). It goes down the same path as the buttons, on a
scratch database: upload demo/real-libraries.csv, Verify claims, Run all, then Retest new version three times
(openjdk 17.0.3, python-ecdsa 0.13.3, elliptic 6.5.7), the Fixes view, Measure status in the Migration step, and
once more in demo mode to see that nothing of a real library runs there.

Real libraries run only in isolated mode. In isolated mode every answer of the key is graded. In demo mode only
the key's demo-mode answer (RD1) applies; the others are listed as not applicable, never as a match.

The key's "regression" counts come from the build's own trial runs. They are a consistency check: a change is
reported and makes the command exit with code 1, but it says only that something changed.
It only READS the answer key; it never writes it."""
from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path

from sqlalchemy import select

from app.config import DEMO_DIR, Settings, load_settings
from app.db import ReviewRow
from app.lab.hub import Lab

EXPECTED_REAL_JSON = DEMO_DIR / "expected-real-libraries.json"   # the answer key: read-only, never written by the app
REAL_FILE = DEMO_DIR / "real-libraries.csv"
WAIT_SECONDS = 1500.0
RETESTS = (("openjdk", "17.0.3"), ("python-ecdsa", "0.13.3"), ("elliptic", "6.5.7"))
KINDS = {"Independent exam (Wycheproof)": "official_vectors", "Attacker tricks": "bad_signatures",
         "Key exchange exam (ML-KEM-768)": "mlkem_vectors", "Signature exam (ML-DSA-65)": "mldsa_vectors"}
SPEED_ANSWERS = ("No slowdown beyond measured noise", "Slowdown found")
ENCODING_FLAGS = {"InvalidEncoding", "BerEncodedSignature", "MissingZero"}


def _flat(parts) -> str:
    """The text of a line the views send as parts ([{t, v}, ...]) or as plain text."""
    if isinstance(parts, str):
        return parts
    if isinstance(parts, dict):
        return _flat(parts.get("text") or "")
    return "".join(str(p.get("v", "")) if isinstance(p, dict) else str(p) for p in (parts or []))


def _result(lab: Lab, result: dict | None) -> dict | None:
    """What this check reads from one reviewed result: its label and words as shown, and the reviewer's own detail."""
    if not result:
        return None
    with lab.db() as db:
        review = db.scalars(select(ReviewRow).where(ReviewRow.run_id == result["run_id"])).first()
    stands = review is not None and review.code == result["code"]
    listed = " ".join(" ".join(row) for block in result.get("evidence") or [] if block.get("type") == "table" for row in block.get("rows") or [])
    return {"label": result["label"], "code": result["code"], "component": result.get("component"), "control": result["control"]["outcome"],
            "plain": result.get("plain"), "shows": list(result.get("shows") or []), "also_noticed": list(result.get("also_noticed") or []),
            "advisories": [a["id"] for a in (result.get("advisories") or {}).get("items") or []], "real": bool(result.get("real")),
            "listed": listed, "reason_code": review.reason_code if stands else None, "detail": dict(review.detail or {}) if stands else {}}


def _rows(lab: Lab, view: dict, side: str) -> dict:
    """{(the program's label in the file, kind of test): result} for one column of the Evidence Lab view."""
    label = {g["key"]: g["heading"].split(": ", 1)[-1] for g in view["groups"]}
    return {(label.get(row["group"], row["group"]), row["kind"]): _result(lab, row[side]) for row in view["rows"]}


def _fixes(lab: Lab, plan_id: int) -> list[dict]:
    out = []
    for fix in lab.fixes_view(plan_id)["fixes"]:
        intro = [text for section in fix.get("sections") or [] for text in ((section.get("suggestion") or {}).get("intro") or [])]
        out.append({"title": fix["title"], "kind": fix["kind"], "status": (fix.get("status") or {}).get("word"),
                    "pull_request": fix.get("pull_request"), "buttons": list((fix.get("actions") or {}).get("buttons") or []),
                    "advisory_links": [a.get("href") for a in (fix.get("advisories") or {}).get("items") or []],
                    "text": " ".join(str(t) for t in intro)})
    return out


def _migration(view: dict) -> dict:
    bands = {row["system_key"]: band["title"] for band in view["roadmap"]["bands"] for row in band["rows"]}
    out = {}
    for system in view["systems"]:
        track = (system.get("tracks") or [{}])[0]
        recommended = next((o for o in system.get("options") or [] if "Recommended" in (o.get("tags") or [])), None)
        # (an option with nothing to fix first still has one line under Blockers: "None measured." or "None: it is in place today.")
        blockers = [text for section in (recommended or {}).get("sections") or [] if section.get("title") == "Blockers"
                    for text in (_flat(line) for line in section.get("lines") or []) if not text.startswith("None")]
        out[system["name"]] = {"status": (system.get("status") or {}).get("label"), "today": _flat((system.get("today") or {}).get("sentence")),
                               "next": _flat(track.get("next")), "blockers": blockers, "band": bands.get(system["key"]),
                               "recommended": (recommended or {}).get("title")}
    return out


def _demo_mode(settings: Settings) -> dict:
    """The same file in demo mode (no container is ever started): what every real component reads."""
    with tempfile.TemporaryDirectory(prefix="evidence-lab-accuracy-") as scratch:
        lab = Lab(dataclasses.replace(settings, data_dir=Path(scratch) / "data", force_mode="demo"), allow_external_demo_server=True)
        lab.start()
        try:
            imp = lab.import_file(REAL_FILE.name, REAL_FILE.read_bytes())
            verify = [{"result": r["result"], "summary": r["summary"]} for r in lab.verify(imp["id"])["results"]]
            plan = lab.ensure_plan(imp["id"])
            lab.run_all(plan["id"])
            lab.wait_until_idle(plan["id"], 300.0)
            tests = [r for r in _rows(lab, lab.lab_view(plan["id"]), "result").values()]
            lab.measure_migration(plan["id"])
            lab.wait_until_measured(plan["id"], 300.0)
            return {"mode": lab.mode.name, "verify": verify, "tests": tests, "migration": _migration(lab.migration_view(plan["id"])),
                    "notices": list(imp.get("notices") or []), "is_demo": bool(imp.get("is_demo"))}
        finally:
            lab.stop()


def collect_real(settings: Settings | None = None, say=None) -> dict:
    """Run the real-libraries file once through the Lab service path and return the app's answers."""
    settings = settings or load_settings()
    out: dict = {"mode": None, "mode_line": None, "notes": [], "stopped": None, "verify": {}, "first": {}, "after": {}, "fixes_first": [],
                 "fixes_after": {}, "migration": {}, "demo_mode": None}
    progress = say or (lambda text: None)
    try:
        progress("  ... the same file in demo mode")
        out["demo_mode"] = _demo_mode(settings)
    except Exception as exc:
        out["stopped"] = f"The demo-mode pass stopped early: {str(exc) or exc.__class__.__name__}"
        return out
    with tempfile.TemporaryDirectory(prefix="evidence-lab-accuracy-") as scratch:
        lab = Lab(dataclasses.replace(settings, data_dir=Path(scratch) / "data"), allow_external_demo_server=True)
        lab.start()
        try:
            out["mode"], out["mode_line"] = lab.mode.name, lab.mode.line
            if lab.mode.name != "isolated":
                out["notes"].append("This run is in demo mode. Real libraries run only in isolated mode (Docker), so only the key's "
                                    "demo-mode answer applies here.")
                return out
            missing = [family for family in ("openssl", "java", "python-ecdsa", "elliptic") if not lab.mode.real_images.get(family)]
            if missing:
                out["notes"].append(f"Not prepared on this computer: the container image for {', '.join(missing)}. Run ./run-demo.sh "
                                    "(or python -m app.prepare) with internet once.")
            imp = lab.import_file(REAL_FILE.name, REAL_FILE.read_bytes())
            out["notes"] += list(imp.get("notices") or [])
            out["is_demo"] = bool(imp.get("is_demo"))
            for res in lab.verify(imp["id"])["results"]:
                out["verify"][(res["claim"]["location"], res["claim"]["claimed_value"])] = {"result": res["result"], "summary": res["summary"]}
            plan = lab.ensure_plan(imp["id"])
            pid = plan["id"]
            progress(f"  ... Run all ({len(plan['tests'])} tests)")
            lab.run_all(pid)
            lab.wait_until_idle(pid, WAIT_SECONDS)
            out["first"] = _rows(lab, lab.lab_view(pid), "result")
            out["fixes_first"] = _fixes(lab, pid)
            progress("  ... Measure status (Migration)")
            lab.measure_migration(pid)
            lab.wait_until_measured(pid, 600.0)
            out["migration"] = _migration(lab.migration_view(pid))
            for name, version in RETESTS:
                progress(f"  ... Retest new version: {name} {version}")
                lab.start_retest(pid, version, name)
                lab.wait_until_idle(pid, WAIT_SECONDS)
                out["after"][name] = _rows(lab, lab.lab_view(pid), "after")
                out["fixes_after"][name] = _fixes(lab, pid)
        except Exception as exc:  # shown, never hidden: every answer not reached counts as a mismatch
            out["stopped"] = f"The check stopped early: {str(exc) or exc.__class__.__name__}"
        finally:
            lab.stop()
    return out


# ---------------------------------------------------------------- comparing (pure: no app, no files)

def _find(rows: dict, component: str, kind: str) -> dict | None:
    """The result of one kind of test for a component as the key names it ("openssl 3.5.9"), whatever algorithm
    the file's label adds ("openssl 3.5.9 (ML-DSA-65)")."""
    for (label, k), result in rows.items():
        if k == kind and (label == component or label.startswith(component + " (")):
            return result
    return None


def _wrong(result: dict | None) -> list[dict]:
    return list(((result or {}).get("detail") or {}).get("wrong") or [])


def _ids(result: dict | None) -> list[str]:
    return [str(w.get("id")) for w in _wrong(result)]


def _must_include(entry_id: str, result: dict) -> tuple[bool, str]:
    """The key's "must_include" and "note" for the ECDSA entries, checked against the reviewer's own detail and the words shown."""
    wrong, ids = _wrong(result), _ids(result)
    accepted = [w for w in wrong if w.get("got") == "accept"]
    if entry_id == "RE1":
        return any(w["id"] == "168" for w in accepted), f"wrongly accepted: {', '.join(w['id'] for w in accepted)}"
    if entry_id == "RE2":
        return any(w["id"] == "r0-s0" for w in accepted), f"wrongly accepted: {', '.join(w['id'] for w in accepted)}"
    if entry_id == "RE3":
        said = bool(ids) and all(i in result["listed"].split() for i in ids)
        return "168" not in ids and said, f"still wrong: {', '.join(ids)}; each is listed in the result: {said}"
    if entry_id == "RE5":
        ok = bool(accepted) and all(set(w.get("flags") or []) & ENCODING_FLAGS for w in accepted) and "malformed encoding" in (result["plain"] or "")
        return ok, f"{len(accepted)} wrongly accepted, all flagged as encoding faults: {ok}"
    if entry_id == "RE7":
        crashes = (result.get("detail") or {}).get("general_errors") or []
        ok = (not crashes) or any("general program error" in note for note in result["also_noticed"])
        return ok, f"{len(crashes)} general errors; Also noticed says so: {ok}"
    if entry_id == "RE9":
        ok = any("MissingZero" in (w.get("flags") or []) for w in accepted)
        return ok, f"wrongly accepted: {', '.join(w['id'] for w in accepted)} (flagged MissingZero: {ok})"
    if entry_id == "RE10":
        ok = any("does not catch CVE-2024-42460" in line for line in result["shows"])
        return ok, f"the result says it does not catch CVE-2024-42460: {ok}"
    return True, ""


def compare_real(expected: dict, answers: dict) -> dict:
    lines: list[dict] = []
    isolated = answers.get("mode") == "isolated"

    def add(entry_id: str, what: str, want: str, got: str, match: bool, why: str = "") -> None:
        lines.append({"id": entry_id, "what": what, "expected": want, "actual": got, "match": bool(match), "why": why,
                      "applies": isolated or entry_id == "RD1"})

    first, after = answers.get("first") or {}, answers.get("after") or {}
    after_of = {"openjdk 17.0.3": ("openjdk", "openjdk 17.0.2"), "python-ecdsa 0.13.3": ("python-ecdsa", "python-ecdsa 0.13.2"),
                "elliptic 6.5.7": ("elliptic", "elliptic 6.5.6")}

    def result_for(component: str, kind: str) -> dict | None:
        if component in after_of:   # a fixed version: read from the retest that moved its library there
            name, label = after_of[component]
            return _find(after.get(name) or {}, label, kind)
        return _find(first, component, kind)

    for entry in expected.get("verify") or []:
        got = (answers.get("verify") or {}).get((entry["component"], entry["claim"]))
        add(entry["id"], f"Verify: {entry['component']} uses {entry['claim']}", entry["expected"], (got or {}).get("result", "(no answer)"),
            got is not None and got["result"] == entry["expected"], (got or {}).get("summary") or "")
    for entry in expected.get("ecdsa_tests") or []:
        got = result_for(entry["component"], KINDS[entry["test"]])
        # (the result must have run on exactly the version the key names, as its run record says)
        ok = got is not None and got["label"] == entry["expected"] and got["control"] == "as_expected" and got["component"] == entry["component"]
        why = ""
        if ok:
            ok, why = _must_include(entry["id"], got)
        add(entry["id"], f"{entry['test']} on {entry['component']}", entry["expected"] + (f" ({entry['must_include']})" if entry.get("must_include") else ""),
            (got or {}).get("label", "(no answer)") + (f" (ran on {got['component']})" if got and got["component"] != entry["component"] else ""),
            ok, why or (got or {}).get("plain") or "")
    exams = {}
    for entry in expected.get("post_quantum_tests") or []:
        if "component" not in entry:   # RP3: every post-quantum control
            parts = [p for got in exams.values() if got for p in (got.get("detail") or {}).get("parts") or []]
            ok = bool(parts) and all(got and got["control"] == "as_expected" for got in exams.values()) and \
                all((p.get("control") or {}).get("caught") == (p.get("control") or {}).get("of") and (p.get("control") or {}).get("of") for p in parts)
            add(entry["id"], entry["test"], "each broken copy fails for its stated reason",
                "; ".join(f"{p['title']}: caught on {(p.get('control') or {}).get('caught')} of {(p.get('control') or {}).get('of')}" for p in parts) or "(no answer)", ok)
            continue
        got = result_for(entry["component"], KINDS[entry["test"]])
        exams[entry["id"]] = got
        parts = ((got or {}).get("detail") or {}).get("parts") or []
        ok = got is not None and got["label"] == entry["expected"] and bool(parts) and all(p["right"] == p["cases"] for p in parts) \
            and got["component"] == entry["component"]
        if ok and entry.get("note"):   # the pre-hash cases are left out and the result says so
            ok = any("pre-hash" in line for line in got["shows"])
        add(entry["id"], f"{entry['test']} on {entry['component']}", entry["expected"], (got or {}).get("label", "(no answer)"), ok,
            ", ".join(f"{p['title'].lower()} {p['right']} of {p['cases']}" for p in parts))
    for entry in expected.get("before_and_after") or []:
        if entry["id"] == "RB4":
            speeds = {name: _find(after.get(name) or {}, label, "speed_size") for name, label in after_of.values()}
            ok = bool(speeds) and all(s is not None and s["label"] in SPEED_ANSWERS for s in speeds.values())
            add("RB4", "Speed and size on every retest", "either answer", "; ".join(f"{n}: {(s or {}).get('label', '(no answer)')}" for n, s in speeds.items()), ok)
            continue
        new = entry["change"].split(" -> ")[0].rsplit(" ", 1)[0] + " " + entry["change"].split(" -> ")[1]   # "openjdk 17.0.3"
        name, label = after_of[new]
        b_exam, a_exam = _find(first, label, "official_vectors"), _find(after.get(name) or {}, label, "official_vectors")
        b_tricks, a_tricks = _find(first, label, "bad_signatures"), _find(after.get(name) or {}, label, "bad_signatures")
        got = (f"Independent exam {(b_exam or {}).get('label')} ({len(_wrong(b_exam))} wrong) -> {(a_exam or {}).get('label')} ({len(_wrong(a_exam))} wrong); "
               f"Attacker tricks {(b_tricks or {}).get('label')} -> {(a_tricks or {}).get('label')}")
        if not all((b_exam, a_exam, b_tricks, a_tricks)):
            ok = False
        elif entry["id"] == "RB1":
            ok = (b_tricks["label"], a_tricks["label"]) == ("Failed", "Passed") and (b_exam["label"], a_exam["label"]) == ("Failed", "Failed") \
                and len(_wrong(a_exam)) < len(_wrong(b_exam)) and "168" in _ids(b_exam) and "168" not in _ids(a_exam)
        elif entry["id"] == "RB2":
            ok = (b_exam["label"], a_exam["label"], b_tricks["label"], a_tricks["label"]) == ("Failed", "Passed", "Failed", "Passed")
        else:
            ok = (b_exam["label"], a_exam["label"], b_tricks["label"], a_tricks["label"]) == ("Failed", "Passed", "Passed", "Passed")
        if ok:   # both tests of the after column ran on the new version, and both of the before column on the old one
            ok = a_exam["component"] == a_tricks["component"] == new and b_exam["component"] == b_tricks["component"] == label
        add(entry["id"], f"Retest {entry['change']}", entry["expected"], got, ok)
    fixes = answers.get("fixes_first") or []
    for entry in expected.get("fixes") or []:
        if entry["id"] == "RF1":
            wanted = ("openjdk", "python-ecdsa", "elliptic")
            found = {n: [f for f in fixes if f["title"].startswith(f"Update {n} to the fixed version")] for n in wanted}
            ok = all(found[n] and all(f["kind"] == "text" and f["advisory_links"] and all(str(h).startswith("https://") for h in f["advisory_links"])
                                      and f["pull_request"] is None and not f["buttons"] for f in found[n]) for n in wanted) \
                and all(f["kind"] != "code" and f["pull_request"] is None for f in fixes)
            add("RF1", "Fixes: each failing real library", "a text-only 'Update to the fixed version' entry with its advisory link; no patch or pull request",
                "; ".join(f"{f['title']} [{f['status']}, {len(f['advisory_links'])} advisory links]" for f in fixes) or "(no fix listed)", ok)
        else:
            later = (answers.get("fixes_after") or {}).get("openjdk") or []
            mine = [f for f in later if f["title"].startswith("openjdk 17.0.3")]
            ok = bool(mine) and all("no fixed version is known" in f["title"] and "No fixed version of openjdk is known to this app" in f["text"] for f in mine)
            add("RF2", "Fixes: openjdk 17.0.3 still failing", "says no fixed version is known to this app",
                "; ".join(f["title"] for f in mine) or "(no such entry)", ok)
    migration = answers.get("migration") or {}
    for entry in expected.get("migration") or []:
        names = [n.strip() for n in entry["component"].split(",")]
        got = {n: migration.get(n) for n in names}
        shown = "; ".join(f"{n}: {(g or {}).get('status')}, " + ("blocked" if (g or {}).get("blockers") else "not blocked") + f", {(g or {}).get('band')}" for n, g in got.items())
        if not all(got.values()):
            ok = False
        elif entry["id"] == "RM1":
            g = got[names[0]]
            ok = g["status"] == "Classical" and not g["blockers"] and "sign with both" in g["next"] and "Not blocked" in g["next"] and "can already make ML-DSA-65" in g["next"]
        elif entry["id"] == "RM2":
            g = got[names[0]]
            ok = g["status"] == "Post-quantum only" and g["band"] == "At the target"
        else:
            ok = all(g["status"] == "Classical" and any("can't make post-quantum signatures" in b for b in g["blockers"]) for g in got.values())
        add(entry["id"], f"Migration: {entry['component']}", entry["expected"], shown, ok)
    demo = answers.get("demo_mode") or {}
    entry = expected.get("demo_mode") or {}
    if entry:
        verify, tests, systems = demo.get("verify") or [], demo.get("tests") or [], demo.get("migration") or {}
        ok = demo.get("mode") == "demo" and len(verify) == 6 and all(v["result"] == "Couldn't check" and "isolated mode" in v["summary"] for v in verify) \
            and len(tests) == 15 and all(t and t["code"] == "couldnt_run" and t["reason_code"] == "needs_isolated_mode" for t in tests) \
            and bool(systems) and all(s["status"] == "Couldn't check" and "isolated mode" in s["today"] for s in systems.values())
        add(entry["id"], "Demo mode: every real component", "Couldn't check / Couldn't run, with 'needs isolated mode'",
            f"Verify: {sorted({v['result'] for v in verify})}; tests: {sorted({(t or {}).get('label', '(no answer)') for t in tests})}; "
            f"Migration: {sorted({s['status'] for s in systems.values()})}", ok)
    # The key's regression counts: a consistency check with the build's own trial runs.
    counts = {"openjdk 17.0.2 exam wrong": len(_wrong(_find(first, "openjdk 17.0.2", "official_vectors"))),
              "openjdk 17.0.3 exam wrong": len(_wrong(_find(after.get("openjdk") or {}, "openjdk 17.0.2", "official_vectors"))),
              "python-ecdsa 0.13.2 exam wrongly accepted": sum(1 for w in _wrong(_find(first, "python-ecdsa 0.13.2", "official_vectors")) if w.get("got") == "accept"),
              "elliptic 6.5.6 exam wrong": len(_wrong(_find(first, "elliptic 6.5.6", "official_vectors")))}
    for label, kind in (("openssl 3.5.9 ML-KEM-768 cases right", "mlkem_vectors"), ("openssl 3.5.9 ML-DSA-65 cases right", "mldsa_vectors")):
        detail = (_find(first, "openssl 3.5.9", kind) or {}).get("detail") or {}
        counts[label] = f"{detail.get('right')} of {detail.get('total')}"
    regression = [{"what": key, "expected": value, "actual": counts.get(key), "same": counts.get(key) == value}
                  for key, value in (expected.get("regression") or {}).items() if not key.startswith("_")]
    graded = [line for line in lines if line["applies"]]
    return {"lines": lines, "matched": sum(1 for line in graded if line["match"]), "total": len(graded), "isolated": isolated,
            "regression": regression if isolated else []}


def print_real_report(settings: Settings | None, say=print) -> int:
    """The real libraries against demo/expected-real-libraries.json. Exit code 0 only if the key is there and every answer
    that applies in this mode matches, and (isolated mode) no regression count changed."""
    say("")
    say("Real libraries accuracy check against demo/expected-real-libraries.json (Verify, the exams, before and after, Fixes, "
        "Migration, demo mode)")
    answers = collect_real(settings, say)
    if answers.get("mode_line"):
        say(f"  mode: {answers['mode_line']}")
    for note in answers["notes"]:
        say(f"  note: {note}")
    if answers["stopped"]:
        say(f"  PROBLEM  {answers['stopped']}")
    if not EXPECTED_REAL_JSON.exists():
        say("  NOT COMPARED  demo/expected-real-libraries.json is not in this copy of the repository, so there is nothing to compare with.")
        say("Real libraries accuracy: not compared (answer key missing)")
        return 2
    try:
        expected = json.loads(EXPECTED_REAL_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        say(f"  PROBLEM  the answer key could not be read ({exc.__class__.__name__}).")
        return 1
    report = compare_real(expected, answers)
    for line in report["lines"]:
        state = ("MATCH   " if line["match"] else "MISMATCH") if line["applies"] else "N/A     "
        say(f"  {line['id']}  {state}  expected {line['expected']!r}, app says {line['actual']!r}  -  {line['what']}")
        if line["why"] and line["applies"]:
            say(f"        {line['why']}")
    changed = [r for r in report["regression"] if not r["same"]]
    for r in report["regression"]:
        say(f"  count  {'SAME    ' if r['same'] else 'CHANGED '}  {r['what']}: the key's trial count {r['expected']!r}, this run {r['actual']!r}")
    if report["isolated"]:
        say(f"Real libraries accuracy: {report['matched']} of {report['total']} match; trial counts: "
            f"{len(report['regression']) - len(changed)} of {len(report['regression'])} unchanged")
    else:
        not_applicable = len(report["lines"]) - report["total"]
        say(f"Real libraries accuracy (demo mode): {report['matched']} of {report['total']} match; {not_applicable} answers need isolated mode "
            "and were not graded")
    return 0 if report["matched"] == report["total"] and not changed and not answers["stopped"] else 1

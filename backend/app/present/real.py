"""Words for real libraries (phase 4c): the two post-quantum exams, and what a result on a real library adds
to the usual words: the published advisories for that version (information, never a result), a note when the
library stopped with a general program error instead of its own "no", and the fix (update to the fixed
version). Nothing here decides a result."""
from __future__ import annotations

from app.engine import pq_vectors
from app import real_libraries

ADVISORY_TITLE = "Published advisories for this version"
ADVISORY_TAG = "from the advisory, not a result"
REAL_TAG = "real software"
TIMING_LINE = "It doesn't show how long any step takes: timing attacks (such as KyberSlash) are outside this test."
SUMMARY_TITLE = "Output summary"
SUMMARY_NOTE = "Summary written by the app from the stored run. The full raw output is in the downloaded evidence JSON."
EXPECT_WORDS = {"answer": "the published answer", "refuse": "refuse it", "accept": "accept it", "reject": "reject it"}
CONTROL_WORDS = {"wrong_answer": "changes one byte of every answer", "skip_key_check": "skips a required key check",
                 "accept_all": "accepts every signature"}


def _plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")


def _table(title, tag, columns, rows, note=None):
    cols = [{"label": c, "align": "left"} if isinstance(c, str) else c for c in columns]
    return {"type": "table", "title": title, "tag": tag, "columns": cols, "rows": [[str(x) for x in r] for r in rows], "meta": [], "note": note}


def is_real(component: dict | None) -> bool:
    return bool(component) and real_libraries.library(component.get("name"), component.get("version")) is not None


def code_words(name: str, version: str) -> str:
    """Which code a run on a real library ran on: the library's own files, in its own container image."""
    lib = real_libraries.LIBRARIES[name]
    build = lib["distribution"].get(version)
    return (f"{lib['label']} {version}" + (f" ({build})" if build else "") +
            ": the library's own files from its pinned source, in its own container image")


def _control_caught(part: dict) -> str:
    c = part.get("control") or {}
    if c.get("caught") is None:
        return "did not answer"
    if c.get("control") == "skip_key_check":
        return f"Accepted {c['caught']} bad {_plural(c['caught'], 'key')}, as it must"
    return f"Caught on all {c['of']}" if c["caught"] == c["of"] else f"Caught on {c['caught']} of {c['of']}"


def pq_exam(w, spec, run, review, ctx) -> None:
    """The Key exchange exam (ML-KEM-768) and the Signature exam (ML-DSA-65)."""
    d, raw = review["detail"], run["raw"]
    comp, total, wrong, parts = ctx["component"], d["total"], d["wrong"], d["parts"]
    algorithm, kem = spec["inputs"]["algorithm"], spec["kind"] == "mlkem_vectors"
    part_names = ", ".join(p["title"].lower() for p in parts[:-1]) + f" and {parts[-1]['title'].lower()}"
    rows = [[p["title"], f"{p['right']} of {p['cases']}", f"NIST {p['nist']} · Wycheproof {p['wycheproof']}", _control_caught(p)] for p in parts]
    w.evidence = [_table("The exam, part by part", "measured", ["Part", "Right", "Test sets", "Control"], rows)]
    if wrong:
        n = len(wrong)
        bad_parts = [p["title"].lower() for p in parts if p["right"] != p["cases"]]
        w.plain = (f"{comp} gave the wrong answer on {n} of the {total} official {algorithm} cases (in {' and '.join(bad_parts)}). "
                   "One wrong answer is enough to fail.")
        w.summary = f"{n} of {total} official {algorithm} cases wrong."
        w.short = w.summary
        w.what = [f"{comp} was put through {total} official cases for {algorithm}: {part_names}. It gave the wrong answer {n} {_plural(n, 'time')}."]
        w.shows = [f"It shows this version does not follow the published standard on these {n} {_plural(n, 'case')}.",
                   "It doesn't show whether anyone has used this, and the right answers don't rule out faults outside these cases.", TIMING_LINE]
        w.evidence.append(_table(f"The {min(n, 40)} {_plural(n, 'case')} it got wrong" + (" (first 40)" if n > 40 else ""), "measured",
                                 [{"label": "Case", "align": "left", "mono": True}, "Part", "What the case is", "It must", f"{comp} gave"],
                                 [[x["id"], x["part"], x["comment"] or ", ".join(x["flags"]) or "-", EXPECT_WORDS[x["expected"]], x["got"]] for x in wrong[:40]]))
        w.fix = f"Report these cases to the maintainers of {comp.split(' ')[0]}, or move to a version that gets them right, then run the same test again."
    else:
        refuse_words = ("and refused every bad key it must refuse" if kem else "accepted every genuine signature and rejected every forged one")
        w.plain = f"{comp} gave the published answer on all {total} official {algorithm} cases, {refuse_words}."
        w.summary = w.short = f"{total} of {total} official {algorithm} cases right."
        w.what = [f"{comp} was put through {total} official cases for {algorithm} from NIST and Project Wycheproof: {part_names}. "
                  "Every answer matched the published one.",
                  ("That includes the cases with a tampered ciphertext, where the standard fixes what the answer must be, and the bad keys that must be refused."
                   if kem else "That includes the signatures built to sit right on the edge of what the standard allows.")]
        w.shows = [f"It shows this version computes {algorithm} as the standard ({'FIPS 203' if kem else 'FIPS 204'}) says, on every one of these {total} published cases.",
                   "It doesn't rule out faults outside this set of cases.", TIMING_LINE]
        w.fix = "None needed. Every official case got the right answer."
    if d.get("left_out"):
        w.shows.append(f"{d['left_out']} NIST cases are left out for every library: they test the pre-hash variant (HashML-DSA), which the adapter does not cover.")
    w.command = f"{comp.split(' ')[0]} {' / '.join(p['id'] for p in parts)} (once per case, JSON in, JSON out), {total} official cases"
    lines = [f"cases run: {total}   right: {d['right']}   wrong: {len(wrong)}"]
    lines += [f"{p['title']}: {p['right']} of {p['cases']} right (NIST {p['nist']}, Wycheproof {p['wycheproof']}); control ({CONTROL_WORDS.get((p.get('control') or {}).get('control'), 'control')}): "
              f"{_control_caught(p).lower()}" for p in parts]
    lines += [f"{x['id']}  \"{x['comment']}\"  expected: {x['expected']}  got: {x['got']}  WRONG" for x in wrong[:40]]
    lines.append("answers are compared by SHA-256 fingerprint; no key or shared secret is stored")
    lines.append(f"harness: {raw['batch']['command']}")
    lines.append(SUMMARY_NOTE)
    w.outputs = [{"title": SUMMARY_TITLE, "text": "\n".join(lines)}]
    w.meta = [{"label": "Test sets", "value": f"NIST ACVP (commit {pq_vectors.ACVP_COMMIT[:7]}) and Project Wycheproof (commit "
               f"{pq_vectors.WYCHEPROOF_PQ_COMMIT[:7]}), each file pinned by SHA-256", "tag": "reference", "href": pq_vectors.ACVP_URL}]
    w.control_text = ("Every deliberately broken copy failed as it must: " + "; ".join(
        f"{p['title'].lower()}: the copy that {CONTROL_WORDS.get((p.get('control') or {}).get('control'), 'is broken')} was caught"
        for p in parts) + ". That tells us this exam can catch these faults, and the result above can be trusted.")


def advisories(component: dict | None, kind: str) -> dict | None:
    """The advisories block of a result on a real library (signature checks only). Information from the publisher."""
    if not is_real(component) or kind not in ("official_vectors", "bad_signatures"):
        return None
    found = real_libraries.advisories(component["name"], component["version"])
    if not found:
        return None
    return {"title": ADVISORY_TITLE, "tag": ADVISORY_TAG,
            "items": [{"id": a["id"], "text": a["text"], "link": a["link"], "href": a["url"], "covered": a["covered"]} for a in found]}


def extras(w, kind: str, component: dict | None, review: dict) -> None:
    """What a result on a real library adds to the usual words. Changes no result."""
    if not is_real(component):
        return
    name, version = component["name"], component["version"]
    label = f"{name} {version}"
    d = review.get("detail") or {}
    crashes = d.get("general_errors") or []
    if kind in ("official_vectors", "bad_signatures", "advisory_cases") and crashes:
        kinds = sorted({c["error"] for c in crashes})
        known = any(a["id"] == "CVE-2019-14853" for a in real_libraries.advisories(name, version))
        w.also_noticed.append(
            f"On {len(crashes)} of these cases {label} stopped with a general program error ({', '.join(kinds)}) instead of its own "
            "“bad signature” answer. It did not accept them, so they count as rejected here. A program that only expects the "
            "library's own error could stop on such input" + (" (this is what CVE-2019-14853 describes)." if known else "."))
    if kind in ("official_vectors", "bad_signatures") and review.get("code") in ("passed", "failed"):
        for a in real_libraries.advisories(name, version):
            if kind in a.get("missed_by", ()):
                w.shows.append(f"It does not catch {a['id']}, which is published for this version. {a['covered']}")
        if review["code"] == "failed":
            fixed = real_libraries.fixed_version(name, version)
            if fixed:
                w.fix = (f"Update {name} to {fixed} or later, the version in which its publisher fixed the fault the advisory describes. "
                         f"Then press \u201cRetest new version\u201d to rerun the same tests on {fixed} and see what, if anything, remains.")
            else:
                w.fix = (f"No fixed version of {name} is known to this app. The cases it still gets wrong are listed above: "
                         "check for a newer release, or report them to its maintainers.")

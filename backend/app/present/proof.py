"""How a test was proven, as one piece (sandbox research, a prototype). Words only: it words no result.

A test that was tried on sandbox copies comes with what stands behind it, in the signed test pack: the counts of each
part of its trial, when the trial was registered and what was frozen then, the code that asked the library its
questions (as text), the check that code had to pass first, and every public copy with where it came from and its
fingerprints. This module lays that out for the proposal's card and for the advisory's panel.

Every number here is the separate reviewer's count, read from the review of a run the research run made in a locked
container on this computer. Those runs are in Otto's research ledger, not in an assessment. Nothing here says Passed or
Failed about them: a result in an assessment comes only from the assessment's own run and its review.
"""
from __future__ import annotations

TITLE = "How this test was proven"
SANDBOX_LABEL = "Sandbox copy"
WRITTEN_LABEL = "Written by Otto"
REGISTRY_WORDS = {"pypi": "PyPI", "npm": "npm"}
NOT_SHOWN = ("What this does not show. It shows which published cases get a wrong answer on these public copies. It does not say how "
             "serious the weakness is, and it says nothing about any other system.")
REPLAYED = "Replayed in a separate step by a second author role of the same build, on this computer. Not by an outside party."
NOT_REPLAYED = "It was not replayed."
NUMBERS_NOTE = ("Each count is the separate reviewer's, from the review of a run in a locked container on this computer. The right "
                "answers are the publisher's (Project Wycheproof, pinned by SHA-256); they never reach the code that asks the library.")


def day(value: object) -> str:
    from app.present import otto        # (at call time: that module shows this one's block)
    return otto.day(str(value) if value else None)


def stamp(value: object) -> str:
    from app.present import otto
    return otto.stamp(str(value) if value else None)


def _plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")


def _counted(arm: dict) -> str:
    total, wrong = int(arm.get("total", 0)), int(arm.get("wrong", 0))
    if wrong == 0:
        return f"All {total} {_plural(total, 'case')} right"
    return f"{wrong} of {total} {_plural(total, 'case')} wrong"


def _moment(value: object) -> str:
    """A ledger time as a sentence shows it (the ledger writes "+00:00" where the app writes "Z")."""
    return stamp(str(value).replace("+00:00", "Z")) if value else "a time the pack does not give"


def _copy_line(library: str, version: dict, registry: str) -> dict:
    """One public copy: where its files came from, when, and that the fingerprint worked out here is the registry's own."""
    files = version["files"]
    main = next((f for f in files if f["package"] == version["says"]["name"] or f["version"] == version["version"]), files[0])
    same = main["registry_fingerprint"].split(":", 1)[-1] == main["sha256"] or main["registry_fingerprint"].startswith("sha512:")
    where = REGISTRY_WORDS.get(registry, registry)
    recorded = main.get("source") == "recorded"
    line = (f"{library} {version['version']}: {main['file']}, from {where}"
            + (" (read from recorded registry answers on this computer)" if recorded else "")
            + f", fetched on {day(main['fetched_at'])}. SHA-256 {main['sha256'][:16]}…"
            + (", the same as the registry's own." if same else "."))
    helpers = [str(h) for h in version.get("helpers") or []]
    return {"version": version["version"], "role": version["role"], "line": line, "published": day(version.get("published")) if version.get("published") else None,
            "helpers_line": ("Helper libraries, the same for every copy of this trial: " + ", ".join(helpers) + ".") if helpers else None,
            "sha256": main["sha256"], "url": main["url"]}


def block(advisory: dict) -> dict | None:
    """The proof of one pack advisory's test, or None when its test was not tried on sandbox copies."""
    test = advisory.get("test") or {}
    extra, trial = test.get("sandbox"), test.get("trial")
    if not extra or not trial:
        return None
    copies, arms, chosen = extra["set"], trial["arms"], extra["versions"]
    library, asking = copies["library"], copies["asking"]
    affected, fixed = chosen["affected"], chosen["fixed"]
    rows = [{"key": "reference", "label": "Our reference library, on the same cases", "count": _counted(arms["reference"]), "must": "Every case right (the baseline)"},
            {"key": "affected", "label": f"{library} {affected} (the version the advisory names as affected)", "count": _counted(arms["affected"]),
             "must": "At least one case wrong"},
            {"key": "fixed", "label": f"{library} {fixed} (the publisher's fixed version)", "count": _counted(arms["fixed"]),
             "must": "As many right as our reference library"},
            {"key": "control", "label": "The control, a signer that accepts everything", "count": _counted(arms["accept-all"]),
             "must": "Wrong on every case that must be refused"}]
    for n, version in enumerate(chosen["more_affected"], start=1):
        if f"more-affected-{n}" in arms:
            rows.append({"key": f"more-affected-{n}", "label": f"{library} {version} (a further version the advisory names as affected)",
                         "count": _counted(arms[f"more-affected-{n}"]), "must": "At least one case wrong"})
    for n, version in enumerate(chosen["more_fixed"], start=1):
        if f"more-fixed-{n}" in arms:
            rows.append({"key": f"more-fixed-{n}", "label": f"{library} {version} (a further version after the fix)",
                         "count": _counted(arms[f"more-fixed-{n}"]), "must": "As many right as our reference library"})
    second = extra.get("second")
    agree = None
    if second is not None and "affected-b" in arms and "fixed-b" in arms:
        a, f = arms["affected-b"], arms["fixed-b"]
        same = int(a.get("agree", -1)) == int(a.get("total", 0)) and int(f.get("agree", -1)) == int(f.get("total", 0))
        agree = ("Two versions of this code were written apart, by two authors that never saw each other's work. Asked the same cases, "
                 f"they gave the same answer on every case: {a.get('agree')} of {a.get('total')} on {library} {affected} and "
                 f"{f.get('agree')} of {f.get('total')} on {library} {fixed}." if same else
                 "Two versions of this code were written apart. They did not give the same answer on every case: "
                 f"{a.get('agree')} of {a.get('total')} the same on {library} {affected}, {f.get('agree')} of {f.get('total')} on {library} {fixed}.")
    written_code = asking["kind"] == "written"
    known = extra.get("known") or {}
    marks = (known.get("versions") or {}).get(fixed) or {}
    known_lines = []
    if known:
        total = int(known.get("valid", 0)) + int(known.get("spoiled", 0))
        known_lines.append(
            f"Before the trial was registered, the code was checked on {library} {fixed} with {total} fresh questions it had never seen: "
            f"{known.get('valid')} signatures our reference library made, and the same {known.get('spoiled')} with one byte of the message "
            f"changed. It had to hand back accept for the first and refuse for the second: {marks.get('accepted_valid')} of "
            f"{known.get('valid')} accepted, {marks.get('rejected_spoiled')} of {known.get('spoiled')} refused.")
        known_lines.append("The questions were made from a random number drawn after the code was fixed, so they could not be known in advance.")
        if known.get("controls_refused"):
            known_lines.append("Two dummy pieces of code of ours, one that always says yes and one that always says no, went through the "
                               "same check and were refused, as they must be.")
        if written_code:
            known_lines.append("A draft never ran on the affected copy and never saw a result of the trial before the code was fixed.")
    left_out = [f"{library} {item['version']} was left out before the trial was registered: {item['reason']}." for item in chosen.get("left_out") or []]
    registered = extra["registered"]
    entries = [e for e in advisory.get("ledger") or [] if isinstance(e, dict)]
    place = next((e["seq"] for e in entries if e.get("id") == registered.get("hypothesis")), None)
    first = min((e["seq"] for e in entries if e.get("kind") == "run" and place is not None and e["seq"] > place), default=None)
    order_words = (f" In the research ledger, a hash chain, the registration is entry {place} and the first run is entry {first}."
                   if place is not None and first is not None else "")
    in_set = {v["version"]: v for v in copies["versions"]}
    order = [affected, fixed, *chosen["more_affected"], *chosen["more_fixed"]]
    code = {"title": "The code that asked the library", "label": WRITTEN_LABEL if written_code else None,
            "author": asking["author"], "file": asking["file"], "lines": asking["lines"], "source": asking["source"], "sha256": asking["sha256"],
            "line": ((f"{asking['lines']} {_plural(asking['lines'], 'line')}, written for this library by Claude as Otto's code author. It holds "
                      "no cryptography and decides nothing: it passes one question to the library's own functions and hands the library's "
                      "own answer back. It was let through only after a screen by fixed rules and the check below.") if written_code else
                     (f"{asking['lines']} {_plural(asking['lines'], 'line')}: the app's own asking code for this library, the same that asks "
                      "its pinned copies.")),
            "show": "Show the code", "hide": "Hide the code",
            "second": ({"title": "The second author's version", "author": second["author"], "lines": second["lines"], "source": second["source"],
                        "sha256": second["sha256"]} if second is not None else None),
            "agree_line": agree, "known_lines": known_lines}
    return {
        "title": TITLE, "label": SANDBOX_LABEL,
        "summary": (f"Tried on public copies of {library} fetched from {REGISTRY_WORDS.get(copies['registry'], copies['registry'])}: "
                    f"{library} {affected} got {arms['affected'].get('wrong')} of {arms['affected'].get('total')} "
                    f"{_plural(int(arms['affected'].get('total', 0)), 'case')} wrong, {library} {fixed} got "
                    f"{'none' if not arms['fixed'].get('wrong') else arms['fixed'].get('wrong')} wrong, and the control that must fail did."),
        "table": {"columns": ["On public copies", "The reviewer's count", "What had to happen"], "rows": rows, "note": NUMBERS_NOTE},
        "registered": {"line": (f"Registered in Otto's harness on {_moment(registered.get('at'))}, before the first run: the cases, the "
                                "code, the copies, the images and what had to happen were frozen by fingerprint. A file that changes "
                                "after that stops the trial." + order_words),
                       "pins_title": "What was frozen, by SHA-256", "pins": [{"name": name, "sha256": digest} for name, digest in sorted(registered["pins"].items())]},
        "judged": (f"Otto's harness judged the trial against those frozen thresholds: {str(trial['outcome']).replace('_', ' ')}. "
                   "One run for each part; nothing was run again to get a better draw."),
        "code": code,
        "copies": {"title": "The public copies", "rows": [_copy_line(library, in_set[v], copies["registry"]) for v in order if v in in_set],
                   "left_out": left_out,
                   "image_line": (f"Built into one container image with no network ({copies['image']['tag']}). Nothing of a package ran while it "
                                  "was fetched or unpacked; a copy runs only in a locked container on this computer."),
                   "trust_line": "The first fetch of a version trusts the registry. A later fetch that differs is refused."},
        "replayed": REPLAYED if trial.get("replayed") else NOT_REPLAYED,
        "not_shown": NOT_SHOWN,
    }



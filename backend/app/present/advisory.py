"""Words for an advisory check (phase 5c): a test from a signed test pack that reruns the published cases matching
one advisory. The result was decided by the reviewer, by the same rule as the Independent exam. Here it is only put
into words; nothing in this file decides anything, and the advisory's own text is shown as its publisher's, never
as a result."""
from __future__ import annotations

from urllib.parse import urlsplit

from app.engine import vectors
from app.present import plain as plain_words

BOX_TITLE = "The advisory this check is for"
BOX_TAG = "quoted from the named source, not a result"
SUMMARY_TITLE = "Output summary"
SUMMARY_NOTE = "Summary written by the app from the stored run. The full raw output is in the downloaded evidence JSON."
# An advisory's link comes from a signed test pack. It is sent as a link only when it points at one of these
# publishers; anything else is shown as plain text.
LINK_HOSTS = ("openjdk.org", "www.oracle.com", "github.com", "nvd.nist.gov", "www.cve.org", "pypi.org", "www.npmjs.com",
              "raw.githubusercontent.com")
SHOWN_WRONG = 40


def _plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")


def _table(title, tag, columns, rows, note=None):
    cols = [{"label": c, "align": "left"} if isinstance(c, str) else c for c in columns]
    return {"type": "table", "title": title, "tag": tag, "columns": cols, "rows": [[str(x) for x in r] for r in rows], "meta": [], "note": note}


def _said(got: str) -> str:
    return "accepted" if got == "accept" else "rejected"


def safe_href(url: object) -> str:
    """The link as it may be sent to the screen: an https address of a known publisher, or nothing."""
    if not isinstance(url, str) or len(url) > 300:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    return url if parts.scheme == "https" and parts.hostname in LINK_HOSTS and not parts.username and parts.port is None else ""


def box(spec: dict) -> dict:
    """The advisory this check was made for, as its publisher words it. Information, never a result."""
    a = spec["inputs"]["advisory"]
    total = len(spec["inputs"]["cases"])
    source = a.get("source") or {}
    return {"title": BOX_TITLE, "tag": BOX_TAG,
            "items": [{"id": str(a["id"]), "text": plain_words.quoted(str(a["quote"])), "link": str(source.get("title") or ""),
                       "href": safe_href(source.get("url")),
                       "covered": (f"This check reruns the {total} published test {_plural(total, 'case')} that "
                                   f"{_plural(total, 'matches', 'match')} it, from test pack {a['pack']}. "
                                   "The words above are the publisher's; the result comes only from the test.")}]}


def fix_words(comp: str, fix: dict | None) -> str:
    """The Suggested fix line of a failed advisory check. `fix` is what the installed test pack says about a fix for
    this advisory (None when the app has not looked it up): {"state": "proven" | "not_proven" | "none", "kind",
    "library", "version", "reason"}. What a trial on public copies showed is said in the pack's own words (`reason`),
    never in a sentence of this app's that the pack might not bear out."""
    name = comp.split(" ")[0]
    if fix and fix.get("state") in ("proven", "not_proven") and fix.get("kind") == "update":
        # The same row as in Fixes, word for word. Whether it is proven on your system is said where the fix is.
        public = str(fix.get("public_line") or "").strip()
        return (f"Otto proposes: update {fix['library']} to {fix['version']}, the version its publisher names as fixed."
                + (f" {public}" if public else "") + " Fixes shows whether it is proven on your system: update the library, then press "
                "“Retest new version” to rerun the same locked tests on the updated version.")
    if fix and fix.get("state") == "own_code":
        return (f"Open Fixes: it shows what can be offered for {name}. A change Otto wrote is offered only when it can be proven on "
                "this computer. Where it can't be, the fix template is offered if it answers this failure; if not, Fixes lists the "
                "failure with a plain suggestion and offers no code change. A change is offered only after every locked test passes "
                "on the changed code.")
    return f"Correct the signature check in {name} so that these cases get the right answer, then run the same tests again."


def advisory_cases(w, spec, run, review, ctx) -> None:
    d, raw = review["detail"], run["raw"]
    a, comp = spec["inputs"]["advisory"], ctx["component"]
    total, wrong = d["total"], d["wrong"]
    advisory = f"advisory {a['id']}"
    what = (f"{comp} was shown the {total} published {_plural(total, 'signature')} that {_plural(total, 'matches', 'match')} {advisory} "
            f"({a['plain_name']}) and asked “is this one genuine?”.")
    if wrong:
        n = len(wrong)
        accepted = sum(1 for x in wrong if x["got"] == "accept")
        refused = n - accepted
        if accepted and not refused:
            did = f"it accepted {n} {_plural(n, 'signature')} that must be rejected"
        elif refused and not accepted:
            did = f"it rejected {n} genuine {_plural(n, 'signature')}"
        else:
            did = (f"it accepted {accepted} {_plural(accepted, 'signature')} that must be rejected and rejected {refused} genuine "
                   f"{_plural(refused, 'one')}")
        w.plain = (f"{comp} got {n} of the {total} published {_plural(total, 'case')} for {advisory} wrong: {did}. "
                   "One wrong answer is enough to fail.")
        head = wrong[0]
        w.summary = (f"{n} of {total} advisory {_plural(total, 'case')} wrong. First: case {head['id']}, "
                     f"{plain_words.case_words(head['comment'])} was {_said(head['got'])}.")
        ids = [x["id"] for x in wrong]
        w.short = f"{n} of {total} advisory {_plural(total, 'case')} wrong ({', '.join(ids[:8])}{' and others' if n > 8 else ''})."
        w.what = [f"{what} It gave the wrong answer {n} {_plural(n, 'time')}."]
        w.shows = [f"It shows this version gives the wrong answer on published cases of the kind {advisory} describes.",
                   "It doesn't show whether anyone has used this, or how your systems use this program.",
                   "The advisory's text is its publisher's. This result comes only from running these cases."]
        w.evidence = [_table(f"The {min(n, SHOWN_WRONG)} {_plural(n, 'case')} it got wrong" + (f" (first {SHOWN_WRONG})" if n > SHOWN_WRONG else ""),
                             "measured",
                             [{"label": "Official case", "align": "left", "mono": True}, "What the case is", "Right answer", f"{comp} said"],
                             [[x["id"], plain_words.case_words(x["comment"]), "reject" if x["expected"] == "invalid" else "accept", _said(x["got"])]
                              for x in wrong[:SHOWN_WRONG]])]
        w.fix = fix_words(comp, ctx.get("advisory_fix"))
    else:
        w.plain = f"{comp} got all {total} published {_plural(total, 'case')} for {advisory} right."
        w.summary = w.short = f"{total} of {total} advisory {_plural(total, 'case')} right."
        w.what = [f"{what} It gave the right answer every time."]
        w.shows = [f"It shows this version gives the right answer on every one of the {total} published {_plural(total, 'case')} chosen for {advisory}.",
                   "It doesn't rule out the same fault in a form these cases don't cover, or faults outside them.",
                   "The advisory's text is its publisher's. This result comes only from running these cases."]
        w.evidence = [_table("Advisory cases, by the right answer", "measured", ["Kind of case", "Cases", f"{comp} got right"],
                             [["Must be accepted", d["valid_total"], d["valid_total"]], ["Must be rejected", d["invalid_total"], d["invalid_total"]]])]
        w.fix = "None needed. Every case for this advisory got the right answer."
    file = spec["inputs"]["files"][0]
    w.command = f"{comp.split(' ')[0]} verify (once per case, JSON in, JSON out), {total} {_plural(total, 'case')} from {file['file']}"
    lines = [f"advisory: {a['id']}   test pack: {a['pack']}   design fingerprint: {a['design_sha256']}",
             f"cases run: {total}   right: {d['right']}   wrong: {len(wrong)}"]
    lines += [f"tcId {x['id']}  \"{x['comment']}\"  expected: {x['expected']}  got: {'valid' if x['got'] == 'accept' else 'invalid'}  WRONG"
              for x in wrong[:SHOWN_WRONG]]
    lines.append(f"control (broken signer): wrong on {d['control_wrong']} of {d['invalid_total']} invalid cases")
    ref = d["reference"]["ecdsa_p256"]
    lines.append(f"reference library: {ref['right']} of {ref['total']} right")
    lines.append(f"harness: {raw['batch']['command']}")
    lines.append(SUMMARY_NOTE)
    w.outputs = [{"title": SUMMARY_TITLE, "text": "\n".join(lines)}]
    w.meta = [{"label": "Vectors", "value": f"Project Wycheproof, C2SP/wycheproof commit {spec['inputs']['commit'][:7]}", "tag": "reference",
               "href": vectors.WYCHEPROOF_SOURCE_URL},
              {"label": "Test pack", "value": f"{a['pack']} (fingerprint {str(a['pack_fingerprint'])[:12]}...)", "tag": "reference"}]
    w.control_text = (f"The deliberately broken signer got all {d['control_wrong']} invalid {_plural(d['control_wrong'], 'case')} wrong, so it failed "
                      "as expected. That tells us this check can catch a faulty signer, and the result above can be trusted.")

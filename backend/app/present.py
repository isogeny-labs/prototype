"""Plain-language wording. Turns a locked test + its run record + its review into what the screens show.

Nothing here decides a result: the label, the control outcome and every count come from the Review (made
by reviewer.py from the raw outputs). This module only chooses words, and builds them from the actual
outcome (the real failing cases, the real timings)."""
from __future__ import annotations

import json

from . import vectors
from .guidance import OWN_LINKS
from .research import TITLES, join_and
from .reviewer import COULDNT_RUN_REASONS

DISCLAIMER = "Passing these tests doesn't prove a system secure. It shows these specific checks passed."
# For the tests whose output is too long to show whole, the box holds a summary the app wrote, and says so.
SUMMARY_TITLE = "Output summary"
SUMMARY_NOTE = "Summary written by the app from the stored run. The full raw output is in the downloaded evidence JSON."
SIZE_NOTE = ("A signature in this format is 70 to 72 bytes long depending on the individual signature, so a difference of "
             "1 or 2 bytes between runs, or from the reference library, is not a real difference.")
SHOWS_TITLE = "What this shows, and what it doesn't"
RECORD_CHANGED = "The stored record no longer matches its fingerprint."
LABELS = {"passed": ("Passed", "pass"), "failed": ("Failed", "fail"), "couldnt_trust": ("Couldn't trust this run", "warn"),
          "measured": ("Measured", "neutral"), "no_slowdown": ("No slowdown beyond measured noise", "pass"),
          "slowdown": ("Slowdown found", "fail"), "offered": ("Offered", "neutral"), "not_offered": ("Not offered", "neutral")}
NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
CONTROL_WHAT = {
    "tls_versions": ("a deliberately misconfigured test server", "failed this test"),
    "certificate": ("a deliberately weak test certificate", "failed this test"),
    "official_vectors": ("a deliberately broken signer", "failed this test"),
    "bad_signatures": ("a deliberately broken signer", "failed this test"),
    "speed_size": ("a deliberately slowed signer", "was flagged as slower"),
    "pq_readiness": ("a test server that does offer the new key exchange", "was detected as offering it"),
    "mldsa_compare": ("a deliberately altered signature", "was rejected"),
}
FAILING_CONTROLS = ("tls_versions", "certificate", "official_vectors", "bad_signatures")
MODE_WORDS = {"demo": "Demo mode, not isolated", "isolated": "Isolated mode: locked-down container, no network"}
RANGE_IDS = {"r0-s0", "r0", "s0", "r-equals-n", "s-equals-n", "s-plus-n", "r-plus-n"}
# A proof (Fixes) reruns the server tests too. Before any merge nothing has been updated, so its words differ from a retest's.
PROOF_SERVER_NOTE = "This change doesn't touch the server."


def number_word(n: int) -> str:
    return NUMBER_WORDS[n] if 0 <= n < len(NUMBER_WORDS) else str(n)


def badge(code: str, reason_code: str | None = None) -> dict:
    if code == "couldnt_run":
        return {"code": code, "label": f"Couldn't run ({COULDNT_RUN_REASONS.get(reason_code, COULDNT_RUN_REASONS['harness_error'])})", "tone": "warn"}
    label, tone = LABELS.get(code, LABELS["couldnt_trust"])
    return {"code": code if code in LABELS else "couldnt_trust", "label": label, "tone": tone}


def control_line(kind: str, outcome: str) -> str:
    what, did = CONTROL_WHAT[kind]
    if outcome == "as_expected":
        return f"Control: {what} {did}, as expected."
    if outcome == "not_run":
        return "Control: not run, because the test couldn't run."
    return f"Control: {what} did not behave as expected, so this run can't be trusted."


def both_control_line(kind: str, before: str, after: str) -> str:
    if before == after == "as_expected":
        return "Control failed as expected in both runs." if kind in FAILING_CONTROLS else "Control behaved as expected in both runs."
    if before == "as_expected" and after == "not_run":
        return "Control behaved as expected in the first run. It was not run in the retest, because the test couldn't run."
    if before != "as_expected" and after == "as_expected":
        return "Control behaved as expected in the retest, but not in the first run."
    if before == "as_expected":
        return "Control did not behave as expected in the retest."
    return "Control did not behave as expected in either run."


def ms(value: float) -> str:
    return f"{value:.2f} ms" if value < 1 else f"{value:.1f} ms"


def signed_percent(value: float) -> str:
    return "0.0%" if abs(value) < 0.05 else f"{value:+.1f}%"


def short_commit(commit: object) -> str:
    """A commit id as the screens show it: its first seven characters. The download has it in full."""
    return str(commit or "")[:7]


def code_words(code: dict) -> str:
    """Which code a run ran on (its run_code values), in words. It is always one of our own registered demo
    components; when the connected repository held exactly that code, the words say where."""
    component = f"{code['component_name']} {code['component_version']}"
    if code["source"] != "repository":
        return f"the bundled demo version of {component}"
    commit, same = short_commit(code["commit"]), f"the same byte for byte as our bundled {component}"
    if code["pull_request_number"] is not None:
        return f"the merged fix: branch {code['branch']}, commit {commit} (pull request #{code['pull_request_number']}), {same}"
    if code["change_id"] is not None:
        return f"the change on branch {code['branch']}, commit {commit}, {same}"
    return f"branch {code['branch']}, commit {commit}, {same}"


def _duration(ms_value: int) -> str:
    return f"{ms_value / 1000:.1f} s"


def _plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")


# ------------------------------------------------------------------ per test: the words

class _Words:
    """Everything one result needs, filled in by the function for its kind."""

    def __init__(self):
        self.summary = self.short = ""
        self.what: list[str] = []
        self.shows: list[str] = []
        self.evidence: list[dict] = []
        self.command = ""
        self.outputs: list[dict] = []
        self.meta: list[dict] = []
        self.control_text = ""
        self.fix: str | None = None


def _table(title: str, tag: str | None, columns: list, rows: list, meta: list | None = None, note: str | None = None) -> dict:
    cols = [{"label": c, "align": "left"} if isinstance(c, str) else c for c in columns]
    return {"type": "table", "title": title, "tag": tag, "columns": cols, "rows": [[str(x) for x in r] for r in rows],
            "meta": meta or [], "note": note}


def _text(title: str, tag: str | None, text: str) -> dict:
    return {"type": "text", "title": title, "tag": tag, "text": text}


def _evidence_text(items: list | None) -> str:
    parts = []
    for e in items or []:
        if isinstance(e, dict):
            parts.append(f"{e.get('title', '')}\n$ {e.get('command', '')}\n{e.get('output', '')}".strip())
    return "\n\n".join(parts) or "(nothing recorded)"


def _link(label: str, source: dict, tag: str = "reference") -> dict:
    item = {"label": label, "value": source["title"], "tag": tag}
    if source.get("url") in OWN_LINKS:  # only links from our own config are ever sent
        item["href"] = source["url"]
    return item


def _tls_versions(w: _Words, spec, run, review, ctx) -> None:
    d, raw = review["detail"], run["raw"]
    address, claimed = spec["target"]["address"], join_and(d["claimed"])
    outside = join_and(d["accepted_outside_claim"])
    states = raw["subject"]["versions"]
    accepted = [v for v in reversed(spec["inputs"]["probed"]) if states.get(v, {}).get("state") == "accepted"]
    if review["code"] == "failed":
        w.summary = f"The server accepted {outside}. The file claims {claimed} only."
        w.short = f"Server accepted {outside}."
        if ctx["phase"] == "retest":
            w.short = f"Server still accepts {outside}. The server is unchanged; only the signing component was updated."
        elif ctx["phase"] == "proof":
            w.short = f"Server still accepts {outside}. {PROOF_SERVER_NOTE}"
        w.what = [f"We tried one handshake for each TLS version, 1.0 to 1.3, against {address}, offering exactly that version each time.",
                  f"The server completed a handshake with {join_and(accepted)}. The file says it accepts {claimed} only, so {outside} should have been refused."]
        w.shows = [f"It shows the server is set up to accept {outside} today, which the file says it does not.",
                   f"It doesn't show that any client actually uses {outside}, and it says nothing about the rest of the server's setup."]
        w.fix = (f"Switch off {outside} on the server so that it accepts {claimed} only, or correct the file if {outside} is meant to stay on. "
                 "Then run this test again.")
    else:
        w.summary = f"The server refused every TLS version other than {claimed}, as the file claims."
        w.short = f"Refuses everything except {claimed}."
        w.what = [f"We tried one handshake for each TLS version, 1.0 to 1.3, against {address}, offering exactly that version each time.",
                  f"The server completed a handshake with {join_and(accepted)} and refused the others, which is what the file claims."]
        w.shows = [f"It shows the server refuses TLS versions other than {claimed} today.",
                   "It doesn't show anything about cipher suites, certificates or the rest of the server's setup."]
        w.fix = "None needed. The server refused every version the file says it should refuse."
    rows = [[v, "accept" if v in d["claimed"] else "refuse", states.get(v, {}).get("state", "unknown")] for v in reversed(spec["inputs"]["probed"])]
    w.evidence = [_table("What the server did with each TLS version", "measured",
                         ["TLS version", "The file says\n(from the file)", "The server\n(measured)"], rows)]
    w.command = f"One TLS handshake per version to {address} (connected to {raw['subject'].get('ip')}), offering exactly that version; handshake only"
    w.outputs = [{"title": "Raw output", "text": _evidence_text(raw["subject"].get("evidence"))},
                 {"title": "Raw output, control server", "text": _evidence_text((raw.get("control") or {}).get("evidence"))}]
    w.control_text = (f"The deliberately misconfigured test server accepts {spec['control']['accepts']}. This test caught it: the control "
                      "failed, as expected. That tells us this test can tell a server that accepts an older version from one that doesn't.")


def _certificate(w: _Words, spec, run, review, ctx) -> None:
    d, raw = review["detail"], run["raw"]
    address, claimed, guidance = spec["target"]["address"], spec["inputs"]["claimed_algorithm"], spec["inputs"]["guidance"]
    found, bits, reasons = d["found"], d["key_bits"], d["reasons"]
    cert = raw["subject"]["certificate"]
    minimum = guidance["minimum_bits"].get(cert.get("algorithm"))
    note = d["notes"][0] if d["notes"] else None
    short_name = found.split(" ", 1)[1] if found.startswith("ECDSA ") else found
    w.what = [f"We completed a handshake with {address} and read the certificate it sent."]
    if not reasons:
        w.summary = f"The certificate is {found}, {bits} bits, as claimed." + (f" Note, not a failure: NIST plans to retire {short_name}." if note else "")
        w.short = f"{found}, as claimed." + (" NIST retirement note." if note else "")
        w.what.append(f"Its key is {found}, {bits} bits. That matches the file" +
                      (f", and it is above the NIST minimum of {minimum} bits for this kind of key." if minimum else "."))
        w.shows = ["It shows the certificate's algorithm and key size match the file and meet NIST's current minimum.",
                   "It doesn't show who issued the certificate, whether browsers trust it or when it expires." +
                   (" The NIST note is about planned retirement, not a weakness today." if note else "")]
        w.fix = "None needed." + (f" To plan ahead: {note['text']}" if note else "")
    else:
        parts = []
        if "algorithm_mismatch" in reasons:
            parts.append(f"The certificate is {found}, {bits} bits. The file claims {claimed}.")
        if "below_minimum" in reasons:
            parts.append(f"Its key ({bits} bits) is below the NIST minimum of {minimum} bits.")
        w.summary = " ".join(parts)
        w.short = f"Certificate is {found}" + (", below the NIST minimum." if "below_minimum" in reasons else f", not {claimed}.")
        w.what.append(w.summary)
        w.shows = ["It shows the certificate the server sends today does not match the file or NIST's minimum key size.",
                   "It doesn't show who issued the certificate or whether anything has gone wrong because of it."]
        w.fix = f"Replace the certificate with one that matches the file ({claimed}) and meets the NIST minimum, or correct the file. Then run this test again."
    if note:
        w.what.append(f"Note, not a failure: {note['text']}")
    meta = [_link("Minimum key sizes", guidance["minimum_source"])]
    if note:
        meta.append(_link("Retirement plan", note["source"]))
    rows = [["Algorithm", claimed, found], ["Key size", f"at least {minimum} bits (NIST)" if minimum else "no minimum on file", f"{bits} bits"]]
    w.evidence = [_table("The certificate, next to the claim and NIST guidance", "measured",
                         ["What", "The file or guidance says\n(from the file, reference)", "The certificate\n(measured)"], rows, meta)]
    w.command = f"One TLS handshake to {address} (connected to {raw['subject'].get('ip')}); read the certificate the server sent"
    lines = "\n".join(f"{k}: {cert.get(k)}" for k in ("algorithm", "curve", "key_bits", "signature_algorithm", "sha256_fingerprint"))
    control_cert = (raw.get("control") or {}).get("certificate") or {}
    w.outputs = [{"title": "Raw output", "text": lines},
                 {"title": "Raw output, control server",
                  "text": "\n".join(f"{k}: {control_cert.get(k)}" for k in ("algorithm", "key_bits", "signature_algorithm"))
                          + f"\n=> {d.get('control_found')}: {', '.join(d.get('control_reasons') or []) or 'no reasons'}"}]
    w.control_text = (f"The deliberately weak test certificate ({d.get('control_found')}) was served, read, and failed this test for being "
                      "below the minimum key size, as expected. That tells us this test can catch a weak certificate.")


def _case_words(comment: str) -> str:
    text = comment.replace("Signature with special case values ", "")
    if text == "r=0 and s=0":
        return "r=0 and s=0 (a signature made of zeros)"
    if text == "r=0 and s=n":
        return "r=0 and s=n (zero, written a second way)"
    if text == "s is larger than n":
        return "s larger than n (a value outside the allowed range)"
    return text


def _range_cause_official(wrong: list[dict]) -> bool:
    known = ("r=0", "s=0", "larger than n", "=n", "r=n", "s=n")
    return bool(wrong) and all(x["expected"] == "invalid" and any(k in x["comment"] for k in known) for x in wrong)


def _said(got: str) -> str:
    return "accepted" if got == "accept" else "rejected"


def _official_vectors(w: _Words, spec, run, review, ctx) -> None:
    d, raw = review["detail"], run["raw"]
    comp, total, wrong = ctx["component"], d["total"], d["wrong"]
    ids = [x["id"] for x in wrong]
    ecdsa = spec["inputs"]["files"][0]
    ed = d["reference"].get("ed25519") or {}
    if wrong:
        n = len(wrong)
        head = next((x for x in wrong if x["id"] == "168"), wrong[0])
        one_cause = _range_cause_official(wrong)
        head_words = ("a signature made of zeros (r=0 and s=0)" if head["id"] == "168" else _case_words(head["comment"]))
        w.summary = f"{n} of {total} official cases wrong. Headline: case {head['id']}, {head_words} was {_said(head['got'])}."
        shown = join_and(ids) if n <= 8 else ", ".join(ids[:8]) + " and others"
        w.short = f"{n} of {total} official cases wrong ({', '.join(ids) if n <= 8 else shown})" + (", all from one missing range check." if one_cause else ".")
        yes = all(x["got"] == "accept" for x in wrong)
        w.what = [f"{comp} was shown {total} official signatures and asked \"is this one genuine?\". It gave the wrong answer {n} {_plural(n, 'time')}"
                  + (", and each time it said yes to a signature that is not genuine." if yes else ".")]
        if head["id"] == "168":
            w.what.append("The clearest is case 168: a signature made only of zeros. Anyone can write that signature without having the signing key.")
        if one_cause:
            w.what.append(f"All {number_word(n)} cases have one cause, not {number_word(n)}: this version never checks that the two numbers in a "
                          "signature (r and s) are inside the allowed range. Zero and \"larger than n\" are both outside it." if n > 1 else
                          "The cause: this version never checks that the two numbers in a signature (r and s) are inside the allowed range.")
        w.shows = ["It shows this version accepts specific forged signatures that a correct ECDSA P-256 checker rejects." if yes
                   else "It shows this version gives wrong answers on specific official cases.",
                   f"It doesn't show whether anyone has used this, and the {d['right']} right answers don't rule out other faults outside this set of cases."]
        w.evidence = [_table(f"The {n} {_plural(n, 'case')} it got wrong", "measured",
                             [{"label": "Official case", "align": "left", "mono": True}, "What the case is", "Right answer", f"{comp} said"],
                             [[x["id"], _case_words(x["comment"]), "reject" if x["expected"] == "invalid" else "accept", _said(x["got"])] for x in wrong])]
        if one_cause and ctx.get("fix_version"):
            w.fix = (f"Update the signing component to {ctx['fix_version']}, which checks that both parts of a signature are inside the allowed "
                     "range before accepting it. Then press \"Retest new version\" to rerun the same tests on it.")
        else:
            w.fix = f"Correct the signature check in {comp} so that these cases get the right answer, then run the same tests again."
    else:
        w.summary = w.short = f"{total} of {total} official cases right."
        w.what = [f"{comp} was shown {total} official signatures and asked \"is this one genuine?\". It gave the right answer every time.",
                  "That includes case 168, a signature made only of zeros (r=0 and s=0), which it rejected."]
        w.shows = [f"It shows this version gives the right answer on every one of these {total} published cases, including the zero and out-of-range ones.",
                   "It doesn't rule out faults outside this set of cases."]
        w.evidence = [_table("Official cases, by the right answer", "measured", ["Kind of case", "Cases", f"{comp} got right"],
                             [["Must be accepted", d["valid_total"], d["valid_total"]], ["Must be rejected", d["invalid_total"], d["invalid_total"]]])]
        w.fix = "None needed. Every official case got the right answer."
    w.command = f"{comp.split(' ')[0]} verify (once per case, JSON in, JSON out), {total} cases from {ecdsa['file']}"
    lines = [f"cases run: {total}   right: {d['right']}   wrong: {len(wrong)}"]
    lines += [f"tcId {x['id']}  \"{x['comment']}\"  expected: {x['expected']}  got: {'valid' if x['got'] == 'accept' else 'invalid'}  WRONG" for x in wrong]
    lines.append(f"control (broken signer): wrong on {d['control_wrong']} of {d['invalid_total']} invalid cases")
    ref = d["reference"]["ecdsa_p256"]
    counted = ed.get("valid", 0) + ed.get("invalid", 0)
    lines.append(f"reference library: {ref['right']} of {ref['total']} right; Ed25519 file: {counted - ed.get('wrong', 0)} of {counted} counted cases right")
    lines.append(f"harness: {raw['batch']['command']}")
    lines.append(SUMMARY_NOTE)
    w.outputs = [{"title": SUMMARY_TITLE, "text": "\n".join(lines)}]
    w.meta = [{"label": "Vectors", "value": f"Project Wycheproof, C2SP/wycheproof commit {spec['inputs']['commit'][:7]}", "tag": "reference",
               "href": vectors.WYCHEPROOF_SOURCE_URL}]
    w.control_text = (f"The deliberately broken signer got all {d['control_wrong']} invalid cases wrong, so it failed as expected. That tells us "
                      "this test can catch a faulty signer, and the result above can be trusted.")


def _bad_signatures(w: _Words, spec, run, review, ctx) -> None:
    d, raw = review["detail"], run["raw"]
    comp, wrong = ctx["component"], d["wrong"]
    ids = {x["id"] for x in wrong}
    reject_total = d["invalid_total"]
    answers = raw["subject"]["answers"]
    try:
        cases = vectors.load_bad_signatures().cases
    except vectors.VectorFileChanged:
        cases = ()
    zero = "r0-s0" in ids
    one_cause = bool(ids) and ids <= RANGE_IDS
    if wrong:
        accepted_bad = [x for x in wrong if x["expected"] == "invalid"]
        if zero:
            w.summary = f"{comp} accepts the signature r=0, s=0, which it must reject."
            w.short = "Accepts the signature r=0, s=0."
        else:
            first = wrong[0]
            w.summary = f"{comp} {_said(first['got'])} {first['comment']}, which it must {'reject' if first['expected'] == 'invalid' else 'accept'}."
            w.short = f"{len(wrong)} of {d['total']} signatures got the wrong answer."
        if one_cause:
            # Said from this test's own wrong cases only; it does not cite any other result.
            w.summary += " One cause: it never checks that the two signature numbers are inside the allowed range."
            w.short += " One cause: no range check."
        w.what = [f"{comp} was given {reject_total} signatures that must be rejected and {d['valid_total']} genuine ones. "
                  f"It accepted {len(accepted_bad)} of the {reject_total} bad ones."]
        if zero:
            w.what.append("The clearest is the signature r=0, s=0: two zeros. Anyone can write it without having the signing key, and this version says it is genuine.")
        if one_cause:
            w.what.append("Every signature it wrongly accepted has a number outside the allowed range (zero, or more than the curve order n). "
                          "It rejected the changed, cut-short and badly encoded ones correctly.")
        w.shows = ["It shows this version accepts forged signatures that it must reject.",
                   "It doesn't show whether anyone has used this, and the list is short: other bad signatures may also get through."]
        if one_cause and ctx.get("fix_version"):
            w.fix = (f"Update the signing component to {ctx['fix_version']}, which checks that both parts of a signature are inside the allowed "
                     "range before accepting it. Then press \"Retest new version\" to rerun the same tests on it.")
        else:
            w.fix = f"Correct the signature check in {comp} so that these signatures get the right answer, then run the same tests again."
    else:
        w.summary = w.short = "Rejects r=0, s=0 and every other bad signature tried."
        w.what = [f"{comp} was given {reject_total} signatures that must be rejected and {d['valid_total']} genuine ones. It rejected every bad one and accepted both genuine ones.",
                  "That includes r=0, s=0 and the values at or above the curve order n."]
        w.shows = [f"It shows this version rejects each of the {reject_total} bad signatures in this list.",
                   "It doesn't rule out other bad signatures that are not in the list."]
        w.fix = "None needed. Every bad signature was rejected."
    rows = []
    for c in cases:
        got = answers.get(c.id)
        right = "accept" if c.expected == "valid" else "reject"
        rows.append([c.id, c.comment, right, (_said(got) if got else "no answer") + ("" if got == right else "  (wrong)")])
    w.evidence = [_table("Every signature tried", "measured",
                         [{"label": "Case", "align": "left", "mono": True}, "What it is", "Right answer", f"{comp} said"], rows)]
    w.command = f"{comp.split(' ')[0]} verify (once per case, JSON in, JSON out), {d['total']} cases from {spec['inputs']['file']}"
    lines = [f"cases run: {d['total']}   right: {d['right']}   wrong: {len(wrong)}"]
    lines += [f"{x['id']}  \"{x['comment']}\"  expected: {x['expected']}  got: {'valid' if x['got'] == 'accept' else 'invalid'}  WRONG" for x in wrong]
    lines.append(f"control (broken signer): accepted {d['control_wrong']} of {d['invalid_total']} bad signatures")
    ref = d["reference"]["bad_signatures"]
    lines.append(f"reference library: {ref['right']} of {ref['total']} right")
    lines.append(f"harness: {raw['batch']['command']}")
    lines.append(SUMMARY_NOTE)
    w.outputs = [{"title": SUMMARY_TITLE, "text": "\n".join(lines)}]
    w.meta = [{"label": "Cases", "value": f"fixed list, SHA-256 {spec['inputs']['sha256'][:16]}...", "tag": "demo"}]
    w.control_text = (f"The deliberately broken signer accepted all {d['control_wrong']} bad signatures, so it failed as expected. That tells us "
                      "this test can catch a signer that accepts forgeries.")


def _version_label(summary: dict) -> str:
    key = str(summary.get("key") or "")
    name, _, version = key.rpartition("-")
    return f"{name} {version}" if name else key


def _bench_summary(label: str, pairs: int, s: dict) -> str:
    return json.dumps({"component": label, "repeats": pairs,
                       "sign_ms": {"median": s["sign"]["median_ms"], "slowest_1_in_100": s["sign"]["p99_ms"]},
                       "verify_ms": {"median": s["verify"]["median_ms"], "slowest_1_in_100": s["verify"]["p99_ms"]},
                       "signature_bytes": s["signature_bytes"], "public_key_bytes": s["public_key_bytes"]}, indent=1) + "\n" + SUMMARY_NOTE


def _bytes(n) -> str:
    return f"{n} bytes" if n is not None else "not reported"


def _speed_size(w: _Words, spec, run, review, ctx) -> None:
    d, code = review["detail"], review["code"]
    pairs, rounds = d["pairs"], spec["inputs"]["rounds"]
    band = d["noise_band_percent"]
    ref = d.get("reference")
    control = d["control"]
    retest = code in ("no_slowdown", "slowdown")
    new = d["new"] if retest else d["subject"]
    new_label = _version_label(new)
    ref_col = (lambda op, k: ms(ref[op][k])) if ref else (lambda op, k: "not measured")
    ref_note = ("The reference library is a heavily optimised production library. It is shown for scale only and is not part of the slowdown rule")
    if retest:
        old, cmp = d["old"], d["comparison"]
        old_label = _version_label(old)
        flagged = [op for op in ("sign", "verify") if cmp[op]["flagged"]]
        op_words = {"sign": "Signing", "verify": "Checking"}
        if flagged:
            w.summary = " ".join(f"{op_words[op]} is {cmp[op]['change_percent']:.0f}% slower on {new_label} than on {old_label}." for op in flagged) \
                        + f" Measured noise: ±{band}%."
            w.short = w.summary
            w.fix = f"Find out what changed in {new_label} that made {join_and([op_words[o].lower() for o in flagged])} slower before it goes into use, then retest."
        else:
            w.summary = (f"Sign {ms(new['sign']['median_ms'])}, verify {ms(new['verify']['median_ms'])} on {new_label}, against "
                         f"{ms(old['sign']['median_ms'])} and {ms(old['verify']['median_ms'])} on {old_label}, measured side by side (medians). Noise: ±{band}%.")
            w.short = f"Sign {ms(new['sign']['median_ms'])}, verify {ms(new['verify']['median_ms'])} (medians). Noise: ±{band}%."
        # The largest measured slowdown. Unflagged, it can still be above the noise band (the rule also needs 3%):
        # then the words say exactly that, and never call it noise.
        worst = max(cmp[op]["change_percent"] for op in cmp)
        in_gap = not flagged and worst > band
        if not flagged:
            w.fix = ("None needed under this test's rule. The small difference measured is below the level it calls a slowdown." if in_gap
                     else "None needed. No slowdown beyond measured noise was found.")
        if flagged:
            verdict = ", and a slowdown is only called when the difference is clearly outside the noise and more than 3%. That is the case here."
        elif in_gap:
            verdict = (f". The difference of {worst:.1f}% is larger than that, but a slowdown is only called when the difference is clearly "
                       "outside the noise and more than 3%, so this is not called a slowdown.")
        else:
            verdict = f", so a difference of {band}% or less is noise, not a slowdown."
        w.what = [f"Each version was asked to sign {pairs} times and check {pairs} times, and it timed itself while doing so. The two versions took turns, "
                  f"in {rounds} alternating rounds, with the same key and message, while no other test was running. The time it takes the program to start is not included.",
                  (f"The typical difference between matched timings is {signed_percent(cmp['sign']['change_percent'])} for signing and "
                   f"{signed_percent(cmp['verify']['change_percent'])} for checking. The measured noise in this run is ±{band}%"
                   + verdict)]
        w.shows = [(f"It shows {new_label} is slower than {old_label} on this computer by more than the measured noise." if flagged else
                    f"It shows {new_label} measured up to {worst:.1f}% slower than {old_label} on this computer, which is above the measured "
                    "noise but below the level this test calls a slowdown." if in_gap else
                    f"It shows the change in {new_label} did not make signing or checking noticeably slower on this computer."),
                   "It doesn't predict speed on your own servers or under load." + (" Sizes are unchanged." if
                    (old["signature_bytes"], old["public_key_bytes"]) == (new["signature_bytes"], new["public_key_bytes"]) else "")]

        def change(a: float, b: float) -> str:
            return signed_percent((b - a) / a * 100.0)

        def size_change(a, b) -> str:
            return "none" if a == b else f"{b - a:+d} bytes"
        rows = [["Sign, median", ms(old["sign"]["median_ms"]), ms(new["sign"]["median_ms"]), signed_percent(cmp["sign"]["change_percent"]), ref_col("sign", "median_ms")],
                ["Sign, slowest 1 in 100", ms(old["sign"]["p99_ms"]), ms(new["sign"]["p99_ms"]), change(old["sign"]["p99_ms"], new["sign"]["p99_ms"]), ref_col("sign", "p99_ms")],
                ["Verify, median", ms(old["verify"]["median_ms"]), ms(new["verify"]["median_ms"]), signed_percent(cmp["verify"]["change_percent"]), ref_col("verify", "median_ms")],
                ["Verify, slowest 1 in 100", ms(old["verify"]["p99_ms"]), ms(new["verify"]["p99_ms"]), change(old["verify"]["p99_ms"], new["verify"]["p99_ms"]), ref_col("verify", "p99_ms")],
                ["Signature size, this run", _bytes(old["signature_bytes"]), _bytes(new["signature_bytes"]), size_change(old["signature_bytes"], new["signature_bytes"]), _bytes(ref and ref["signature_bytes"])],
                ["Public key size", _bytes(old["public_key_bytes"]), _bytes(new["public_key_bytes"]), size_change(old["public_key_bytes"], new["public_key_bytes"]), _bytes(ref and ref["public_key_bytes"])]]
        columns = ["What was measured", {"label": f"{old_label}\nbefore", "align": "right"}, {"label": f"{new_label}\nafter", "align": "right"},
                   {"label": "Change", "align": "right"}, {"label": "Reference library\n(cryptography)", "align": "right"}]
        meta = [{"label": "Repeats", "value": f"{pairs} sign and {pairs} verify per version, in {rounds} alternating rounds", "tag": None},
                {"label": "Measured noise", "value": f"±{band}% (from the paired differences in this run)", "tag": None},
                {"label": None, "value": "acme-sign columns" if new_label.startswith("acme-sign") else "component columns", "tag": "measured"},
                {"label": None, "value": "last column", "tag": "reference"}]
        note = (f"{ref_note}, which compares {new_label} with {old_label}. Both versions were measured side by side in this run, in the same mode. "
                "The Change column for medians is the typical difference between matched timings. "
                "The slowest-1-in-100 figures move a lot from run to run and are not part of the rule. "
                "Both versions signed the same message with the same test key, so their sizes can be compared exactly. " + SIZE_NOTE)
        w.evidence = [_table("Timings and sizes, before and after", None, columns, rows, meta, note)]
        w.outputs = [{"title": f"{SUMMARY_TITLE}, {old_label}", "text": _bench_summary(old_label, pairs, old)},
                     {"title": f"{SUMMARY_TITLE}, {new_label}", "text": _bench_summary(new_label, pairs, new)}]
    else:
        w.summary = (f"Sign {ms(new['sign']['median_ms'])}, verify {ms(new['verify']['median_ms'])} (medians over {pairs} repeats). "
                     f"Signature {_bytes(new['signature_bytes'])} in this run, public key {_bytes(new['public_key_bytes'])}.")
        w.short = f"Sign {ms(new['sign']['median_ms'])}, verify {ms(new['verify']['median_ms'])} (medians)."
        w.what = [f"{new_label} was asked to sign {pairs} times and check {pairs} times, and it timed itself while doing so, while no other test was running. "
                  "The time it takes the program to start is not included.",
                  f"A typical signature takes {ms(new['sign']['median_ms'])} to make and {ms(new['verify']['median_ms'])} to check. "
                  f"The slowest 1 in 100 took {ms(new['sign']['p99_ms'])} and {ms(new['verify']['p99_ms'])}."]
        w.shows = ["It shows how long this version takes to sign and check on this computer, and how big its signatures and keys are. This is the baseline a retest compares against.",
                   "It doesn't say whether that is fast enough for you, and it doesn't predict speed on your own servers or under load. There is no pass or fail on a first run."]
        rows = [["Sign, median", ms(new["sign"]["median_ms"]), ref_col("sign", "median_ms")],
                ["Sign, slowest 1 in 100", ms(new["sign"]["p99_ms"]), ref_col("sign", "p99_ms")],
                ["Verify, median", ms(new["verify"]["median_ms"]), ref_col("verify", "median_ms")],
                ["Verify, slowest 1 in 100", ms(new["verify"]["p99_ms"]), ref_col("verify", "p99_ms")],
                ["Signature size, this run", _bytes(new["signature_bytes"]), _bytes(ref and ref["signature_bytes"])],
                ["Public key size", _bytes(new["public_key_bytes"]), _bytes(ref and ref["public_key_bytes"])]]
        columns = ["What was measured", {"label": new_label, "align": "right"}, {"label": "Reference library\n(cryptography)", "align": "right"}]
        meta = [{"label": "Repeats", "value": f"{pairs} sign and {pairs} verify, in {rounds} rounds", "tag": None},
                {"label": "Measured noise", "value": f"±{band}% (from the paired differences in this run)", "tag": None},
                {"label": None, "value": f"{new_label} column", "tag": "measured"}, {"label": None, "value": "last column", "tag": "reference"}]
        w.evidence = [_table("Timings and sizes", None, columns, rows, meta, f"{ref_note}. It is not a like-for-like comparison. {SIZE_NOTE}")]
        w.outputs = [{"title": f"{SUMMARY_TITLE}, {new_label}", "text": _bench_summary(new_label, pairs, new)}]
        w.fix = "None needed. The first run only reports numbers; a retest compares a new version against them side by side."
    w.command = f"{new_label.split(' ')[0]} bench (the program signs and verifies {pairs} times each, in {rounds} rounds of {spec['inputs']['repeats']}, and reports its own timing)"
    if "sign" in control:
        w.control_text = (f"The deliberately slowed signer ({control['delay_ms']} ms added to every operation) measured {control['sign']['change_percent']:.0f}% slower on signing and "
                          f"{control['verify']['change_percent']:.0f}% slower on checking, far outside the ±{band}% noise, and was flagged as slower by the same rule, as expected. "
                          "That tells us this test can catch a real slowdown.")


def _pq_readiness(w: _Words, spec, run, review, ctx) -> None:
    d, raw = review["detail"], run["raw"]
    address, group = spec["target"]["address"], d["group"]
    subject = raw["subject"]
    if review["code"] == "not_offered":
        w.summary = f"The server does not offer the quantum-resistant key exchange {group}."
        w.short = f"Server does not offer {group}."
        w.what = [f"We asked {address} for a TLS 1.3 handshake that uses only {group}. The server refused it (alert 40, handshake failure).",
                  "An ordinary handshake to the same server worked, so the refusal is about this key exchange, not about reaching the server."]
        w.shows = [f"It shows this server does not offer {group} today.",
                   "It doesn't show a weakness today: this is about readiness for the post-quantum move. Other quantum-resistant key exchanges were not tried."]
        w.fix = (f"Nothing is broken today. To get ready for the post-quantum move, plan to switch on {group} on the server; "
                 "it needs a TLS library that supports it, such as OpenSSL 3.5 or newer.")
    else:
        w.summary = f"The server offers the quantum-resistant key exchange {group}."
        w.short = f"Server offers {group}."
        w.what = [f"We asked {address} for a TLS 1.3 handshake that uses only {group}. The handshake completed, and the checker printed the group it agreed on."]
        w.shows = [f"It shows this server completes a handshake with {group} today.",
                   "It doesn't show that every client will use it, or anything about the rest of the server's setup."]
        w.fix = "None needed."
    if ctx["phase"] == "retest":
        w.short += " The server was tested again as it is; only the signing component was updated."
    elif ctx["phase"] == "proof":
        w.short += f" {PROOF_SERVER_NOTE}"
    w.evidence = [_text(f"What the checker printed when only {group} was offered", "measured", subject["pq_only"].get("output") or ""),
                  _text("What it printed for an ordinary handshake", "measured", (subject.get("normal") or {}).get("output") or "")]
    w.command = subject["pq_only"].get("command") or "openssl s_client"
    w.outputs = [{"title": "Raw output", "text": subject["pq_only"].get("output") or ""},
                 {"title": "Raw output, control server", "text": ((raw.get("control") or {}).get("pq_only") or {}).get("output") or ""}]
    checker = raw.get("checker") or {}
    w.meta = [{"label": "Checker", "value": f"{checker.get('version')} ({'on this computer' if checker.get('kind') == 'local' else 'our pinned OpenSSL container'})",
               "tag": "measured"}]
    w.control_text = (f"A test server on this computer that does offer {group} was checked the same way and was detected as offering it, as expected. "
                      "That tells us the checker can see this key exchange when it is there.")


def _mldsa_compare(w: _Words, spec, run, review, ctx) -> None:
    d = review["detail"]
    m, c, label = d["mldsa65"], d["component"], d["label"]
    w.summary = (f"ML-DSA-65 ({label}): sign {ms(m['sign']['median_ms'])}, verify {ms(m['verify']['median_ms'])} (medians over {d['repeats']} repeats); "
                 f"signature {m['signature_bytes']} bytes, public key {m['public_key_bytes']} bytes.")
    w.short = f"ML-DSA-65: signature {m['signature_bytes']} bytes, public key {m['public_key_bytes']} bytes ({label})."
    w.what = [f"We timed a post-quantum signature, ML-DSA-65, from the cryptography library: {d['repeats']} key generations, signs and checks. "
              "These are reference figures from the same reference library the speed test uses. They are not a measurement of any ML-DSA software of yours."]
    columns = ["What was measured", {"label": f"ML-DSA-65\n({label})", "align": "right"}]
    rows = [["Make a key, median", ms(m["keygen"]["median_ms"])], ["Sign, median", ms(m["sign"]["median_ms"])],
            ["Sign, slowest 1 in 100", ms(m["sign"]["p99_ms"])], ["Verify, median", ms(m["verify"]["median_ms"])],
            ["Verify, slowest 1 in 100", ms(m["verify"]["p99_ms"])], ["Signature size", _bytes(m["signature_bytes"])],
            ["Public key size", _bytes(m["public_key_bytes"])]]
    meta = [{"label": "Repeats", "value": f"{d['repeats']} of each operation for ML-DSA-65", "tag": None},
            {"label": None, "value": "ML-DSA-65 column", "tag": "reference"}]
    if c:
        comp = _version_label(c)
        w.summary += (f" {comp}: sign {ms(c['sign']['median_ms'])}, verify {ms(c['verify']['median_ms'])}; signature {_bytes(c['signature_bytes'])}, "
                      f"public key {_bytes(c['public_key_bytes'])}.")
        w.what.append(f"Next to it, {comp} was timed with its own bench command. An ML-DSA-65 signature is {m['signature_bytes']} bytes against "
                      f"{c['signature_bytes']}, and its public key {m['public_key_bytes']} bytes against {c['public_key_bytes']}.")
        columns.append({"label": comp, "align": "right"})
        extra = ["not measured", ms(c["sign"]["median_ms"]), ms(c["sign"]["p99_ms"]), ms(c["verify"]["median_ms"]), ms(c["verify"]["p99_ms"]),
                 _bytes(c["signature_bytes"]), _bytes(c["public_key_bytes"])]
        rows = [r + [e] for r, e in zip(rows, extra)]
        meta.append({"label": None, "value": f"{comp} column", "tag": "measured"})
    w.shows = ["It shows roughly what a post-quantum signature costs in size and time, using the reference library (cryptography) on this computer.",
               "It doesn't show how ML-DSA would perform in your own software or on production hardware. The two columns are different algorithms "
               "measured in different ways (a library call inside this app against the component's bench command), so the timings are for scale only."]
    w.evidence = [_table("ML-DSA-65 next to the signing component", None, columns, rows, meta,
                         f"ML-DSA-65 figures come from the reference library ({label}). They are for scale only.")]
    w.command = "cryptography (hazmat mldsa): generate a test key, sign, verify; each timed inside this app"
    w.outputs = [{"title": "Raw output", "text": json.dumps({"mldsa65": m, "component": c}, indent=1)}]
    w.fix = "None needed. This test only reports numbers."
    w.control_text = ("A genuine ML-DSA-65 signature was accepted, and the same signature with one byte changed was rejected, as expected. "
                      "That tells us the reference library was really checking signatures while it was timed.")


_WORDS = {"tls_versions": _tls_versions, "certificate": _certificate, "official_vectors": _official_vectors,
          "bad_signatures": _bad_signatures, "speed_size": _speed_size, "pq_readiness": _pq_readiness, "mldsa_compare": _mldsa_compare}


def _not_a_result(w: _Words, spec, run, review, ctx) -> None:
    raw = run.get("raw") if isinstance(run.get("raw"), dict) else {}
    problem = raw.get("problem") if isinstance(raw.get("problem"), dict) else {}
    if review["code"] == "couldnt_run":
        reason = review.get("reason") or COULDNT_RUN_REASONS["harness_error"]
        w.summary = f"This test could not run: {reason}."
        w.short = f"Could not run: {reason}."
        w.what = [w.summary, str(problem.get("text") or "No more detail was recorded.")]
        w.shows = ["It shows nothing about the system either way: the test did not run.", "It doesn't mean the system passed, and it doesn't mean it failed."]
        text = problem.get("text") or reason
        gate = _evidence_text(raw.get("gate")) if raw.get("gate") else ""
        w.evidence = [_text("Why it could not run", None, f"{text}\n\n{gate}".strip())]
        w.control_text = "The control was not run, because the test itself could not run."
    else:
        reason = review.get("reason") or "The control did not behave as it must, so this run can't be trusted."
        w.summary = reason
        w.short = "This run can't be relied on."
        w.what = [reason, "The test ran, but the check that tells us the test itself works did not come out as it must. So neither a pass nor a fail from this run would mean anything."]
        w.shows = ["It shows that this run can't be relied on.", "It doesn't mean the system passed, and it doesn't mean it failed. Run the test again."]
        control = review.get("control") or {}
        w.evidence = [_text("What the review found", None, f"control: {control.get('outcome')} ({control.get('reason')})\nreference library right on every case: {review.get('reference_ok')}")]
        w.control_text = f"The control did not behave as expected ({control.get('reason') or control.get('outcome')}), so this run can't be trusted."
    w.command = "(see the raw output)"
    w.outputs = [{"title": "Raw output", "text": json.dumps(problem or {"note": "no usable outcome"}, indent=1)}]
    w.fix = None


# ------------------------------------------------------------------ the views

def lab_result(*, spec: dict, spec_hash: str, locked_at: str, run_id: int, run: dict, review: dict, trusted: bool,
               mark: dict | None, research: dict | None, fix_version: str | None, code: dict | None = None) -> dict:
    """One reviewed run, worded. `review` is the stored Review (flat: code, reason_code, reason, control, detail, ...).
    `trusted` is False when the stored record no longer matches its fingerprint. `code` is which code the run
    ran on (its run_code values), or None for a run in which no component of ours ran."""
    kind = spec["kind"]
    component = f"{run['component']['name']} {run['component']['version']}" if (run.get("component") or {}).get("name") else None
    if not trusted:
        review = {**review, "code": "couldnt_trust", "reason_code": None, "reason": RECORD_CHANGED,
                  "control": {"outcome": review["control"]["outcome"], "reason": "the stored record was changed after the review"}}
    w = _Words()
    ctx = {"component": component or spec["target"].get("component") or "the component", "phase": run.get("phase"), "fix_version": fix_version}
    filler = _WORDS[kind] if review["code"] not in ("couldnt_run", "couldnt_trust") else _not_a_result
    try:
        filler(w, spec, run, review, ctx)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        w = _Words()
        _not_a_result(w, spec, run, {**review, "code": "couldnt_trust", "reason": "The stored result could not be read."}, ctx)
        review = {**review, "code": "couldnt_trust", "reason_code": None}
    outcome = review["control"]["outcome"]
    b = badge(review["code"], review.get("reason_code"))
    meta = [{"label": "Time", "value": "", "time": run["started_at"], "tag": None},
            {"label": "Duration", "value": _duration(run["duration_ms"]), "tag": "measured"}]
    if component:
        meta.append({"label": "Component", "value": component, "tag": "demo"})
    if code:
        meta.append({"label": "Code", "value": code_words(code), "tag": "demo"})
    if run.get("baseline_version") and component and kind == "speed_size":
        meta.append({"label": "Compared with", "value": f"{run['component']['name']} {run['baseline_version']}", "tag": "demo"})
    meta.append({"label": "Mode", "value": MODE_WORDS.get(run.get("mode"), str(run.get("mode"))), "tag": None})
    control_text = w.control_text if outcome == "as_expected" or review["code"] in ("couldnt_run", "couldnt_trust") else \
        f"The control did not behave as expected ({review['control'].get('reason')}), so this run can't be trusted."
    return {
        "run_id": run_id, "component": component, "mode": run.get("mode"), "finished_at": run["finished_at"], "duration_ms": run["duration_ms"],
        **b, "summary": w.summary, "short": w.short,
        "control": {"outcome": outcome, "line": control_line(kind, outcome), "text": control_text},
        "what_happened": w.what, "shows_title": SHOWS_TITLE, "shows": w.shows, "evidence": w.evidence,
        "run_record": {"title": "Run record", "command": w.command, "outputs": w.outputs, "meta": meta + w.meta},
        "locked_test": {
            "title": "Test details, locked before the run",
            "fields": [{"label": "Question", "lines": [spec["question"]]}, {"label": "Method", "lines": [spec["method"]]},
                       {"label": "Inputs", "lines": list(spec["inputs_text"])}, {"label": "Control", "lines": [spec["control"]["text"]]},
                       {"label": "Pass/fail rule", "lines": [spec["rule_text"]]}],
            "locked_at": locked_at, "locked_text": "before the run started",
            "fingerprint_label": "Fingerprint of these details (SHA-256)", "fingerprint": spec_hash,
            "note": "The details can't change after locking. The run record carries the same fingerprint, so anyone can confirm the test wasn't adjusted to fit the result."},
        "fix_title": "Suggested fix", "suggested_fix": w.fix,
        "reviewed": {"at": mark["at"], "text": "You marked this result as reviewed."} if mark else None,
        "research": research_view(research) if research else None,
    }


def research_view(r: dict) -> dict:
    return {"id": r["id"], "title": "Research request saved", "badge": "Queued", "status": r["status"],
            "status_line": f"Status: {r['status']}",
            "fields": [{"label": "Finding", "value": r["finding"]}, {"label": "Question", "value": r["question"]},
                       {"label": "Evidence attached", "value": "The run record and locked test details above"}],
            "saved_at": r["created_at"],
            "note": "No answer yet. The research engine isn't connected in this version, so nothing has been looked into and this result is unchanged."}


def status_view(status: str, progress_text: str | None = None, percent: int | None = None, max_parallel: int = 4) -> dict:
    if status == "waiting":
        return {"status": "waiting", "status_text": "Waiting",
                "progress": {"text": f"{max_parallel} tests run at once; starts when one finishes", "percent": None}}
    if status == "running":
        return {"status": "running", "status_text": "Running",
                "progress": {"text": progress_text or "starting", "percent": percent}}
    return {"status": "not_run", "status_text": "Not run yet", "progress": None}


def card_description(spec: dict) -> tuple[str, str]:
    return spec["card"]["description"], spec["card"]["why"]


def intro(filename: str, suggested_now: int, added_now: int, suggested_at_first: int, changed: bool) -> str:
    tail = "Drag to change the order, remove any you don't want, then run them."
    if not changed:
        n = suggested_at_first
        return f"{number_word(n).capitalize()} {_plural(n, 'test')} suggested from the claims in {filename}. {tail}"
    total = suggested_now + added_now
    return (f"{number_word(total).capitalize()} {_plural(total, 'test')} in the plan: {number_word(suggested_now)} suggested from the claims, "
            f"{number_word(added_now)} added by you. {tail}")


__all__ = ["DISCLAIMER", "TITLES", "badge", "control_line", "both_control_line", "lab_result", "research_view", "status_view",
           "card_description", "intro", "number_word", "RECORD_CHANGED", "code_words", "short_commit"]

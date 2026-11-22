"""The research engine socket. Everything that thinks about tests goes through one interface:

    propose_tests(claims)  -> the suggested tests, each written down in full before anything runs
    design_test(request)   -> one test from the catalog (used by "+ Add test")
    review(result)         -> the review of a run (never done by the engine that proposed the test)
    dig_deeper(finding)    -> a research request, saved as "waiting for research engine"
    propose_change(request) -> a code change for failed results, from a fix template, or nothing

This file holds the rule-based engine shipped in this version. It proposes and designs tests, files
research requests and proposes a code change from a fix template. No AI model writes anything here.
It holds NO verdict logic: results are decided only in reviewer.py, from raw outputs, and so is whether a
proposed change may be offered. The code it is shown is text: it is never run here.
A locked test never names a component version, a mode or a time, so the same test (same fingerprint) is
rerun unchanged on a new version."""
from __future__ import annotations

from typing import Protocol

from app.engine import pq_vectors
from app import real_libraries
from app.engine import vectors
from app.engine.guidance import NIST_GUIDANCE
from app.engine.reviewer import ReviewNotAllowed  # the one shared name; the reviewer imports nothing from here

SPEC_SCHEMA = "isogeny.test-spec/1"
TLS_VERSIONS = ["TLS 1.0", "TLS 1.1", "TLS 1.2", "TLS 1.3"]
SUGGESTED_KINDS = ("tls_versions", "certificate", "official_vectors", "bad_signatures", "speed_size")
CATALOG = ("pq_readiness", "mldsa_compare")
# Phase 4c: the two post-quantum exams. Suggested by themselves for a program that claims ML-KEM-768 or ML-DSA-65.
PQ_EXAM_KINDS = ("mlkem_vectors", "mldsa_vectors")
ALL_KINDS = SUGGESTED_KINDS + PQ_EXAM_KINDS + CATALOG
SERVER_KINDS = ("tls_versions", "certificate", "pq_readiness")
# Phase 4a: the Migration step's own measurements. They are locked, run and reviewed like tests, but are not in
# the Tests step's plan or catalog.
MIGRATION_KINDS = ("pq_status", "signing_status")
PQ_FAMILIES = {"hybrid": ["X25519MLKEM768", "SecP256r1MLKEM768", "SecP384r1MLKEM1024"],
               "pure": ["MLKEM768", "MLKEM1024", "MLKEM512"], "classical": ["X25519", "P-256", "P-384"]}
PQ_CONTROL = {"kind": "pq_control_servers",
              "text": ("The same check against two test servers started on this computer for this run: one that offers hybrid key "
                       "exchange, which must be read as Hybrid, and one that is classical only, which must be read as Classical."),
              "must": {"hybrid_server": "hybrid", "classical_server": "classical"}}
# Phase 4b: two tracks. The same control, plus the "both keys at once" hello, which our hybrid test server must answer
# with hybrid and our classical one with classical.
PQ_CONTROL_TRACKS = {**PQ_CONTROL, "text": PQ_CONTROL["text"] + (" Both are also sent one hello with a hybrid and a classical key at "
                                                                  "once: the hybrid one must take hybrid, the classical one classical."),
                     "must": {**PQ_CONTROL["must"], "both_keys": {"hybrid_server": "hybrid", "classical_server": "classical"}}}
PQ_TRACKS_RULE_TEXT = ("Authentication (a second track): Classical when the certificate key and the handshake signature are both classical, "
                       "Post-quantum when both are ML-DSA, anything else couldn't check. Whether hybrid is chosen by default, and whether a "
                       "classical-only client still connects, are recorded as facts, not as a pass or a fail.")
PQ_METHOD = ("Send three first messages (TLS 1.3 hellos) with no key attached: one offering only hybrid key exchanges, one only "
             "ML-KEM by itself, one only classical ones. A server that supports one of them asks for a key for it; one that "
             "supports none refuses. Then make one full handshake offering only hybrids and one as a classical-only client. "
             "Handshakes only; no data is sent.")
PQ_RULE_TEXT = ("Hybrid only on positive proof: the server asks for a hybrid key, or completes a full hybrid handshake. "
                "Post-quantum only if it accepts ML-KEM by itself and refuses both the hybrid and the classical hello. "
                "Classical only if it refuses every post-quantum hello and the full hybrid handshake with a TLS refusal and "
                "accepts a classical key exchange. In every case both control servers must have been read correctly. "
                "Anything else: couldn't check.")
PQ_GROUP = "X25519MLKEM768"
PQ_LINE = "Negotiated TLS1.3 group: X25519MLKEM768"
SPEED_MESSAGE = "45766964656e6365204c61622073706565642074657374206d6573736167652e"  # 32 fixed bytes of text
CONTROL_DELAY_MS = 6
MLDSA_LABEL = "reference, not production"
RESEARCH_STATUS = "waiting for research engine"
CHANGE_LABEL = "From a fix template"   # how every proposed change is labelled: none is written by an AI model

# The screen titles. The ids stay as they were (the answer key uses them); since phase 3a-fixes the two signing
# tests are titled so the difference is plain: an outside exam of many cases, and our own short list of forgeries.
TITLES = {
    "tls_versions": "Old TLS versions", "certificate": "Certificate strength", "official_vectors": "Independent exam (Wycheproof)",
    "bad_signatures": "Attacker tricks (our short list)", "speed_size": "Speed and size", "pq_readiness": "Post-quantum readiness",
    "mldsa_compare": "ML-DSA-65 comparison", "pq_status": "Post-quantum status", "signing_status": "Post-quantum status",
    "capability": "Post-quantum capability",
    "mlkem_vectors": "Key exchange exam (ML-KEM-768)", "mldsa_vectors": "Signature exam (ML-DSA-65)",
}
# Phase 5c: an advisory check. A test that comes from a signed test pack (app/otto), built from one published
# advisory: the published cases that match its weakness, with the same control and pass rule as the exam they come
# from. It is never suggested by this engine and is not in the catalog: a person adds it from the Advisories page.
ADVISORY_KIND = "advisory_cases"
TITLES[ADVISORY_KIND] = "Advisory check"
SOFTWARE_TEST_KINDS = ("official_vectors", "bad_signatures", "speed_size", "mldsa_compare") + PQ_EXAM_KINDS + (ADVISORY_KIND,)
PQ_SIGNATURE, PQ_KEY_EXCHANGE = "ML-DSA-65", "ML-KEM-768"
CATALOG_DESCRIPTIONS = {
    "pq_readiness": "Checks whether the server offers a quantum-resistant key exchange (such as X25519MLKEM768).",
    "mldsa_compare": "Shows the speed and sizes of a post-quantum signature (ML-DSA-65) from a reference implementation, next to {component}'s.",
}


class CannotDesign(Exception):
    """This catalog test does not fit the imported claims (for example: no server address in the file)."""


class ResearchEngine(Protocol):
    engine_id: str

    def propose_tests(self, claims: list[dict]) -> dict: ...
    def design_test(self, request: dict) -> dict: ...
    def review(self, result: dict) -> dict: ...
    def dig_deeper(self, finding: dict) -> dict: ...
    def propose_change(self, request: dict) -> dict | None: ...


def title_of(kind: object, spec: dict | None = None) -> str:
    """The screen title of a test. An advisory check carries its own (it names its advisory); every other test has
    the title of its kind."""
    if kind == ADVISORY_KIND and isinstance(spec, dict) and spec.get("title"):
        return str(spec["title"])
    return TITLES.get(str(kind), str(kind))


def join_and(items: list[str]) -> str:
    items = list(items)
    return "".join(items) if len(items) <= 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _first(claims: list[dict], location_kind: str, kind: str, need: str, location: str | None = None) -> dict | None:
    for c in claims:
        if c.get("location_kind") == location_kind and c.get("kind") == kind and (c.get("detail") or {}).get(need) \
                and (location is None or str(c.get("location")) == location):
            return c
    return None


def servers(claims: list[dict]) -> list[str]:
    """Every server address in the file, once each, in the order the file names them."""
    return list(dict.fromkeys(str(c["location"]) for c in claims if c.get("location_kind") == "server" and c.get("location")))


def programs(claims: list[dict]) -> list[dict]:
    """Every program the file names that this app can test: a signing program (a signature_algorithm claim on a
    software component) or, since phase 4c, a key exchange program (a key_exchange claim for ML-KEM-768). Once per
    name, version and algorithm, in file order: {"ref", "component", "version", "algorithm", "label", "role"}.
    The claim's ref is how a test remembers which one it is for: two versions of the same program (acme-sign 1.4.2
    and acme-sign 9.9) are two programs, and so are two algorithms of one library (openssl 3.5.9 with ECDSA P-256
    and with ML-DSA-65); then the label names the algorithm too."""
    out, seen = [], set()
    for c in claims:
        d = c.get("detail") or {}
        if c.get("location_kind") != "software" or not d.get("component"):
            continue
        algorithm = str(d.get("algorithm") or c.get("claimed_value") or "")
        if c.get("kind") == "signature_algorithm":
            role = "signing"
        elif c.get("kind") == "key_exchange" and algorithm == PQ_KEY_EXCHANGE:
            role = "key_exchange"
        else:
            continue
        version = str(d["version"]) if d.get("version") else None
        key = (str(d["component"]), version) if role == "signing" and not _many_algorithms(claims, d) else (str(d["component"]), version, algorithm)
        if key in seen:
            continue
        seen.add(key)
        out.append({"ref": str(c.get("ref")), "component": str(d["component"]), "version": version, "algorithm": algorithm,
                    "label": f"{d['component']} {version}" if version else str(d["component"]), "role": role})
    out.sort(key=lambda p: p["role"] != "signing")   # signing programs first, then key exchange; file order within each
    for p in out:  # one library named with more than one algorithm: say which
        if sum(1 for q in out if (q["component"], q["version"]) == (p["component"], p["version"])) > 1:
            p["label"] = f"{p['label']} ({p['algorithm']})"
    return out


def _many_algorithms(claims: list[dict], detail: dict) -> bool:
    """Does the file name this component and version with more than one algorithm this app can test?"""
    found = set()
    for c in claims:
        d = c.get("detail") or {}
        if c.get("location_kind") == "software" and (d.get("component"), d.get("version")) == (detail.get("component"), detail.get("version")):
            algorithm = str(d.get("algorithm") or c.get("claimed_value") or "")
            if c.get("kind") == "signature_algorithm" or (c.get("kind") == "key_exchange" and algorithm == PQ_KEY_EXCHANGE):
                found.add((c.get("kind"), algorithm))
    return len(found) > 1


def program_kinds(program: dict) -> tuple[str, ...]:
    """The tests suggested for one program, by what the file says it does."""
    if program.get("role") == "key_exchange":
        return ("mlkem_vectors",)
    if program.get("algorithm") == PQ_SIGNATURE:
        return ("mldsa_vectors", "speed_size")
    if str(program.get("algorithm", "")).startswith(("ML-DSA", "ML-KEM")):
        return ()
    # Sandbox research (prototype): a public copy whose asking code only checks signatures can't be timed signing, so
    # Speed and size is left out for it. (None with the switch off: the pinned libraries and our own programs sign.)
    found = real_libraries.library(program.get("component"), program.get("version"))
    if found is not None and found.get("checks_only"):
        return ("official_vectors", "bad_signatures")
    return ("official_vectors", "bad_signatures", "speed_size")


def _server_address(claims: list[dict]) -> str | None:
    found = servers(claims)
    return found[0] if found else None


def _software(claims: list[dict], ref: str | None = None) -> dict | None:
    """The signing program a software test is for: the one whose claim has this ref, or the first one."""
    found = [p for p in programs(claims) if ref is None or p["ref"] == ref]
    if not found:
        return None
    return {"component": found[0]["component"], "algorithm": found[0]["algorithm"], "claim": found[0]["ref"]}


def _program(claims: list[dict], ref: str | None) -> dict | None:
    found = [p for p in programs(claims) if ref is None or p["ref"] == ref]
    return found[0] if found else None


def target_key(kind: str, target: dict) -> str | None:
    """Which target a test is for, as one string: the server address, or the ref of the program's claim
    (None for a test written before phase 3a-fixes, which named no claim: it is for the first program)."""
    if (target or {}).get("kind") == "server":
        return str(target.get("address"))
    return str(target["claim"]) if (target or {}).get("claim") else None


# ---------------------------------------------------------------- the fix template (the only one)
# Only this template knows about acme-sign 1.4.2, 1.4.3 and the range check. Each edit swaps exact lines for
# exact lines; the screen shows `context` unchanged lines before and after it.

RANGE_CHECK = {
    "id": "ecdsa-range-check",
    "component": "acme-sign",
    "file": "acme_sign.py",
    "title": "Reject signatures whose r or s is out of range",
    "branch": "fix/ecdsa-range-check",
    "edits": [
        {"title": "The check: reject a signature whose numbers are out of range",
         "why": "acme_sign.py, in the verify command. r and s must each be at least 1 and below n, a fixed upper limit set by the P-256 standard.",
         "find": ["    try:",
                  '        r, s = der_decode(bytes.fromhex(req["signature"]))',
                  "    except ValueError:",
                  '        return {"valid": False}'],
         "put": ["    try:",
                 '        r, s = der_decode(bytes.fromhex(req["signature"]))',
                 "    except ValueError:",
                 '        return {"valid": False}',
                 "    if not (1 <= r < N and 1 <= s < N):",
                 '        return {"valid": False}'],
         "context": (4, 1)},
        {"title": "The version number",
         "why": "So the changed program reports itself as 1.4.3 and can be told apart from 1.4.2.",
         "find": ['VERSION = "1.4.2"'],
         "put": ['VERSION = "1.4.3"'],
         "context": (1, 1)},
    ],
}
TEMPLATE_IDS = frozenset({RANGE_CHECK["id"]})  # every fix template this engine has, by id

# A failed signing test is answered by the range check when every case it got wrong is a signature with a
# number outside the allowed range. present.py words the same test as "One cause: ..."; a test keeps the two in step.
_RANGE_COMMENTS = ("r=0", "s=0", "larger than n", "=n", "r=n", "s=n")
_RANGE_CASE_IDS = frozenset({"r0-s0", "r0", "s0", "r-equals-n", "s-equals-n", "s-plus-n", "r-plus-n"})


def out_of_range_cause(kind: object, detail: object) -> bool:
    """True when a failed signing test's wrong answers all come from values outside the allowed range."""
    wrong = detail.get("wrong") if isinstance(detail, dict) else None
    if not isinstance(wrong, list) or not wrong or not all(isinstance(x, dict) for x in wrong):
        return False
    if kind in ("official_vectors", ADVISORY_KIND):   # an advisory check reruns cases of the same official file
        return all(x.get("expected") == "invalid" and any(k in str(x.get("comment")) for k in _RANGE_COMMENTS) for x in wrong)
    if kind == "bad_signatures":
        return {x.get("id") for x in wrong} <= _RANGE_CASE_IDS
    return False


def _place(lines: list[str], wanted: list[str]) -> int | None:
    """Where the wanted lines stand in the text, if they stand there exactly once (else None)."""
    hits = [i for i in range(len(lines) - len(wanted) + 1) if lines[i:i + len(wanted)] == wanted]
    return hits[0] if len(hits) == 1 else None


def _apply_edits(text: str, edits: list[dict]) -> tuple[str, list[dict]] | None:
    """Apply every edit to the text, or None unless each one's lines are found exactly once and no two overlap.
    Also says where each edit landed: the changed lines in the old and in the new text, counted from 0 with
    the end not included (the same way gitrepo.Spot counts)."""
    lines = text.split("\n")  # at line feeds only, as git does; a last line break leaves one empty piece at the end
    places = [_place(lines, edit["find"]) for edit in edits]
    if None in places:
        return None
    order = sorted(range(len(edits)), key=lambda n: places[n])
    if any(places[a] + len(edits[a]["find"]) > places[b] for a, b in zip(order, order[1:])):  # noqa: B905
        return None
    spots: list[dict] = [{} for _ in edits]
    shift = 0  # how far the edits above have moved the lines below them
    for n in order:
        at, find, put = places[n], edits[n]["find"], edits[n]["put"]
        kept = 0  # lines the edit keeps at its start (what it was found by), so only what changes is marked
        while kept < min(len(find), len(put)) and find[kept] == put[kept]:
            kept += 1
        spots[n] = {"old_start": at + kept, "old_end": at + len(find),
                    "new_start": at + kept + shift, "new_end": at + len(put) + shift}
        shift += len(put) - len(find)
    for n in reversed(order):  # from the bottom up, so the places found above stay right
        lines[places[n]:places[n] + len(edits[n]["find"])] = edits[n]["put"]
    return "\n".join(lines), spots


class RuleEngine:
    engine_id = "isogeny.rule-engine/1"

    def __init__(self, speed_rounds: int = 40, speed_repeats: int = 5):
        self.speed_rounds, self.speed_repeats = int(speed_rounds), int(speed_repeats)

    # ---------------------------------------------------------------- the interface

    def propose_tests(self, claims: list[dict]) -> dict:
        """Every server in the file gets each server test that applies, and every signing program each signing
        test that applies: servers first, in file order, then programs. `not_suggested` says, per target, which
        suggested test it does not get and why; `notes` says the same in one line each."""
        tests, notes, skipped = [], [], []
        targets = [("server", a) for a in servers(claims)] + [("software", p["ref"]) for p in programs(claims)]
        kinds_of = {p["ref"]: program_kinds(p) for p in programs(claims)}
        pq_claimed = {str(c.get("location")) for c in claims if c.get("location_kind") == "server" and c.get("kind") == "post_quantum"}
        for side, key in targets:
            for kind in (SUGGESTED_KINDS if side == "server" else kinds_of[key]):
                if (kind in SERVER_KINDS) != (side == "server"):
                    continue
                try:
                    tests.append(self._design(kind, claims, key))
                except CannotDesign as exc:
                    skipped.append({"kind": kind, "target_kind": side, "target": key, "reason": str(exc)})
                    notes.append(f"{TITLES[kind]} for {key}: not suggested. {exc}")
            if side == "server" and key in pq_claimed:
                # Phase 4b: a post-quantum claim suggests the Post-quantum readiness test for that server.
                tests.append(self._design("pq_readiness", claims, key))
        for side, kinds, why in (("server", ("tls_versions", "certificate"), "The file names no server."),
                                 ("software", ("official_vectors", "bad_signatures", "speed_size"), "The file names no signing component.")):
            if not any(s == side for s, _ in targets):
                notes += [f"{TITLES[kind]}: not suggested. {why}" for kind in kinds]
        return {"tests": tests, "notes": notes, "not_suggested": skipped}

    def design_test(self, request: dict) -> dict:
        """One catalog test for one target: request["target"] is a server address or a program's claim ref
        (the first one that fits when it is not given)."""
        kind = request.get("catalog_id")
        if kind not in ALL_KINDS:
            raise CannotDesign("That test is not in the catalog.")
        target = request.get("target")
        return self._design(kind, list(request.get("claims") or []), str(target) if target is not None else None)

    def design_capability(self, request: dict) -> dict:
        """Phase 4d: the post-quantum capability check of one library version, written down in full before it runs.
        request: {"name", "version", "label", "target_kind" ("public_copy"), "tls": bool (the hybrid handshake is
        measured on this target), "capable": label, "incapable": label}. Which questions run, and the two control copies,
        are in the spec; where the library came from is only its target kind, which the reviewer never reads."""
        name, version = str(request["name"]), str(request["version"])
        questions = ["ml_kem_768"] + (["x25519mlkem768"] if request.get("tls") else []) + ["ml_dsa_65"]
        target = {"kind": "library", "target_kind": str(request.get("target_kind", "public_copy")), "name": name, "version": version,
                  "label": str(request.get("label") or f"{name} {version}")}
        inputs = {"questions": questions,
                  "algorithms": {"ml_kem_768": "ML-KEM-768", "x25519mlkem768": "X25519MLKEM768", "ml_dsa_65": "ML-DSA-65"},
                  "lab_server": "the app's own test server on 127.0.0.1 that accepts only X25519MLKEM768, started for the run",
                  "confirmed_by": "cryptography (pyca), the app's reference library"}
        inputs_text = [f"The pinned public copy of {target['label']}, run in its own locked-down container.",
                       "ML-KEM-768: make a key pair, encapsulate, decapsulate; the reference library decapsulates a second message from it.",
                       "ML-DSA-65: make a key pair, sign, verify; the reference library checks the same signature."]
        if request.get("tls"):
            inputs_text.append("X25519MLKEM768: a TLS 1.3 handshake offering only that group, with the app's own test server on this computer; "
                               "and one classical handshake by the same client.")
        control = {"kind": "capability_copies", "capable": str(request["capable"]), "incapable": str(request["incapable"]),
                   "text": f"Every question is also asked of {request['capable']}, which must be able to do it, and of "
                           f"{request['incapable']}, which must refuse it in its own words (and still complete a classical handshake).",
                   "must": {"capable": "yes on every question", "incapable": "refused by the library itself on every question"}}
        rule = {"type": "capability", "yes": "every step worked and the reference library agreed",
                "no": "the library itself refused the algorithm", "otherwise": "couldnt_check, with the reason"}
        return self._spec("capability", "Can this library do post-quantum key exchange and signatures?",
                          "A library that can't do them blocks the migration of every system that relies on it.",
                          f"Can {target['label']} do ML-KEM-768 key exchange{', X25519MLKEM768 hybrid TLS' if request.get('tls') else ''} "
                          "and ML-DSA-65 signatures today?",
                          "Ask the library for each algorithm and, where it has it, run one round trip that the reference library confirms.",
                          target, inputs, inputs_text, control, rule,
                          "Yes only when every step worked and the reference library agreed; No only when the library itself refused; "
                          "anything else is Couldn't check. If a control copy does not behave, the run can't be trusted.")

    def design_measurement(self, request: dict) -> dict:
        """One Migration measurement (phase 4a), written down in full like a test: request["kind"] is "pq_status"
        (target: a server address) or "signing_status" (target: a program's claim ref)."""
        kind = request.get("kind")
        if kind not in MIGRATION_KINDS:
            raise CannotDesign("That measurement is not known.")
        return self._design(kind, list(request.get("claims") or []), str(request.get("target")))

    def review(self, result: dict) -> dict:
        raise ReviewNotAllowed("The engine that proposes tests does not review results.")

    def dig_deeper(self, finding: dict) -> dict:
        """Write down the research request. Nothing is looked into and no answer is made up."""
        view, spec, review = finding.get("view") or {}, finding.get("spec") or {}, finding.get("review") or {}
        title = spec.get("title", "This test")
        component = view.get("component")
        on = f" on {component}" if component else ""
        short = str(view.get("short") or view.get("summary") or "").rstrip(".")
        label = view.get("label", "")
        wrong = [w.get("id") for w in (review.get("detail") or {}).get("wrong", [])]
        kind = spec.get("kind")
        if kind == "official_vectors" and wrong:
            text = f"{title}: {label}, {len(wrong)} of {(review.get('detail') or {}).get('total')} cases wrong{on}"
            question = (f"Why does this version accept {'case' if len(wrong) == 1 else 'cases'} {join_and(wrong)}, "
                        "and are there related cases the official set doesn't cover?")
        elif kind == "bad_signatures" and wrong:
            text = f"{title}: {label}, {len(wrong)} of {(review.get('detail') or {}).get('total')} cases wrong{on}"
            question = "Which other out-of-range or malformed signatures does this version accept, beyond the ones tried here?"
        elif view.get("tone") == "warn":  # the test gave no result that can be relied on
            text = f"{title}: {label}{on}"
            question = "What stopped this test from giving a result that can be relied on, and what would let it run?"
        else:
            text = f"{title}: {label}{on}" + (f". {short}" if short else "")
            question = {
                "tls_versions": "Which clients still need the older TLS version, and what would break if it were switched off?",
                "certificate": "When does this certificate need to move to a post-quantum algorithm, and what depends on it?",
                "speed_size": "How do these timings change under load and on production hardware?",
                "pq_readiness": "What would it take for this server to offer the quantum-resistant key exchange?",
                "mldsa_compare": "What would moving this component to ML-DSA-65 cost in time, size and code changes?",
            }.get(kind, "What else should be checked around this result?")
        return {"finding": text[:500], "question": question,
                "evidence": {"run_id": finding.get("run_id"), "spec_hash": review.get("spec_hash"), "review_id": review.get("id")},
                "status": RESEARCH_STATUS}

    def propose_change(self, request: dict) -> dict | None:
        """A code change for failed results, or None when no fix template fits. Everything in the request is
        data: {"component": {"name", "version"}, "failed": [{"kind", "reason_code", "detail"}], "files": {name: text}}.
        `answers` in the reply lists the places in `failed` this change answers. Whether the change may be
        offered is not decided here: it is proved first, and the separate reviewer decides."""
        template = RANGE_CHECK
        component, files = request.get("component") or {}, request.get("files") or {}
        if component.get("name") != template["component"]:
            return None
        answers = [i for i, result in enumerate(request.get("failed") or [])
                   if isinstance(result, dict) and out_of_range_cause(result.get("kind"), result.get("detail"))]
        text = files.get(template["file"])
        if not answers or not isinstance(text, str):
            return None
        applied = _apply_edits(text, template["edits"])
        if applied is None:
            return None  # the code does not have exactly the lines this template expects
        new_text, spots = applied
        return {"template_id": template["id"], "title": template["title"], "branch": template["branch"], "label": CHANGE_LABEL,
                "answers": answers, "files": {**files, template["file"]: new_text},
                "edits": [{"file": template["file"], "title": edit["title"], "why": edit["why"],
                           "context_before": edit["context"][0], "context_after": edit["context"][1], **spot}
                          for edit, spot in zip(template["edits"], spots)]}  # noqa: B905

    # ---------------------------------------------------------------- the tests, written down in full

    def _design(self, kind: str, claims: list[dict], target: str | None = None) -> dict:
        return getattr(self, "_" + kind)(claims, target)

    @staticmethod
    def _spec(kind: str, description: str, why: str, question: str, method: str, target: dict, inputs: dict,
              inputs_text: list[str], control: dict, rule: dict, rule_text: str) -> dict:
        return {"schema": SPEC_SCHEMA, "kind": kind, "title": TITLES[kind], "card": {"description": description, "why": why},
                "question": question, "method": method, "target": target, "inputs": inputs, "inputs_text": inputs_text,
                "control": control, "rule": rule, "rule_text": rule_text}

    def _tls_versions(self, claims: list[dict], target: str | None = None) -> dict:
        claim = _first(claims, "server", "protocol_versions", "versions", target)
        if claim is None:
            raise CannotDesign("The file makes no claim about TLS versions for a server." if target is None else
                               "The file makes no claim about which TLS versions this server accepts.")
        claimed = [v for v in TLS_VERSIONS if v in claim["detail"]["versions"]]
        outside = [v for v in TLS_VERSIONS if v not in claimed]
        if not claimed or not outside:
            raise CannotDesign("The claim leaves no TLS version that the server should refuse.")
        older = [v for v in outside if TLS_VERSIONS.index(v) < TLS_VERSIONS.index(claimed[0])]
        accepts = older[-1] if older else outside[-1]
        address = str(claim["location"])
        claimed_words = join_and(claimed)
        return self._spec(
            "tls_versions",
            f"Checks whether the server at {address} accepts any TLS version older than the file claims ({claimed_words} only).",
            "Why it matters: older versions have known weaknesses and are easy to leave switched on.",
            f"Does the server at {address} accept any TLS version other than {claimed_words}?",
            "Make one handshake per TLS version (1.0, 1.1, 1.2 and 1.3), offering exactly that version, and note whether the server completes it. Handshakes only; no data is sent.",
            {"kind": "server", "address": address},
            {"claimed": claimed, "probed": list(TLS_VERSIONS)},
            [f"The claim from the file: {claimed_words} only.", "TLS versions tried: 1.0, 1.1, 1.2 and 1.3."],
            {"kind": "tls_server_accepting_older", "accepts": accepts,
             "text": f"The same handshakes against a deliberately misconfigured test server on this computer that accepts {accepts}, which must fail this test.",
             "must": {"verdict": "failed", "accepted": accepts}},
            {"type": "no_accepted_version_outside_claim"},
            f"Failed if the server completes a handshake with any version other than {claimed_words}. Passed only if it refuses every other version and accepts a claimed one.")

    def _certificate(self, claims: list[dict], target: str | None = None) -> dict:
        claim = _first(claims, "server", "certificate", "algorithm", target)
        if claim is None:
            raise CannotDesign("The file makes no claim about a server certificate's algorithm." if target is None else
                               "The file makes no claim about this server's certificate.")
        address, algorithm = str(claim["location"]), str(claim["detail"]["algorithm"])
        g = NIST_GUIDANCE
        return self._spec(
            "certificate",
            "Checks that the server's certificate uses the algorithm and key size the file claims, and compares them with current NIST guidance.",
            "Why it matters: a weak or outdated certificate undermines every connection.",
            f"Does the certificate served by {address} use {algorithm}, as claimed, and does its key meet current NIST minimum sizes?",
            "Complete one handshake, read the certificate the server sends, and compare its key type and size with the claim and with the guidance below.",
            {"kind": "server", "address": address},
            {"claimed_algorithm": algorithm, "guidance": g},
            [f"The claim from the file: {algorithm}.",
             f"Guidance: {g['minimum_source']['title']} (minimum key sizes: RSA {g['minimum_bits']['RSA']} bits, elliptic curve {g['minimum_bits']['EC']} bits) and {g['notes'][0]['source']['title']}."],
            {"kind": "weak_certificate_server", "certificate": "RSA 1024",
             "text": "The same check against a test server on this computer with a deliberately weak test certificate (RSA, 1024 bits), which must fail this test for being below the minimum size.",
             "must": {"verdict": "failed", "reason": "below_minimum"}},
            {"type": "certificate_matches_claim_and_minimum"},
            "Passed only if the certificate's algorithm matches the claim and its key is at least the NIST minimum size. Retirement plans are shown as a note, not a failure.")

    def _signing_target(self, claims: list[dict], target: str | None = None, kind: str | None = None) -> dict:
        software = _software(claims, target)
        if software is None:
            raise CannotDesign("The file names no signing component.")
        program = _program(claims, target)
        if kind is not None and kind not in program_kinds(program) and not (kind == "mldsa_compare" and program_kinds(program)[:1] == ("official_vectors",)):
            raise CannotDesign(f"This test does not fit {program['label']}: the file says it does {program['algorithm']}.")
        return {"kind": "software", **software}

    def _pq_exam(self, kind: str, claims: list[dict], ref: str | None) -> dict:
        """One of the two post-quantum exams (phase 4c): official cases with published right answers, in parts, each
        part with its own deliberately broken control."""
        target = self._signing_target(claims, ref, kind)
        name, exam = target["component"], pq_vectors.EXAMS[kind]
        algorithm, kem = exam["algorithm"], kind == "mlkem_vectors"
        parts = [{"id": part, "title": title, "cases": cases} for part, title, cases in exam["parts"]]
        total = sum(p["cases"] for p in parts)
        files = pq_vectors.file_pins(kind)
        nist = sum(1 for f in files if f["source"] == pq_vectors.NIST)
        inputs_text = [f"{nist} NIST ACVP files (usnistgov/ACVP-Server, commit {pq_vectors.ACVP_COMMIT[:7]}) and {len(files) - nist} Project Wycheproof "
                       f"files (C2SP/wycheproof, commit {pq_vectors.WYCHEPROOF_PQ_COMMIT[:7]}), each stored whole and pinned by SHA-256.",
                       f"{total} cases: " + ", ".join(f"{p['title'].lower()} {p['cases']}" for p in parts) + "."]
        if exam["left_out"]:
            inputs_text.append(f"Left out for every library: {exam['left_out']} NIST cases for the pre-hash variant (HashML-DSA), which the adapter does not cover.")
        if kem:
            must = {"keygen": {"control": "wrong_answer", "wrong_on": "every case"},
                    "encaps": {"control": "skip_key_check", "accepts_flag": pq_vectors.KEY_OUT_OF_RANGE, "count": 117},
                    "decaps": {"control": "skip_key_check", "accepts_flag": pq_vectors.KEY_HASH_WRONG, "count": 6}}
            control_text = ("Three deliberately broken copies run the same cases. One changes a byte of every key it makes, and must be caught on every "
                            "key generation case. One skips the two key checks the standard requires: it must wrongly accept all 117 public keys "
                            "holding a number that is too large, and all 6 private keys whose fingerprint is wrong.")
            question = f"Does {name} make the published keys, ciphertexts and shared secrets for ML-KEM-768, and refuse every key it must refuse?"
            why = ("Why it matters: both sides of a key exchange must compute exactly the same thing, and a library that skips a required "
                   "key check can be handed a bad key. This shows the new post-quantum code is built to the standard (FIPS 203).")
        else:
            must = {"keygen": {"control": "wrong_answer", "wrong_on": "every case"},
                    "sign": {"control": "wrong_answer", "wrong_on": "every published signature"},
                    "verify": {"control": "accept_all", "wrong_on": "every signature that must be rejected"}}
            control_text = ("Deliberately broken copies run the same cases. One changes a byte of every key and signature it makes, and must be caught on "
                            "every key generation and every signing case. One accepts every signature, and must be wrong on every signature "
                            "that has to be rejected.")
            question = f"Does {name} make the published keys and signatures for ML-DSA-65, accept every genuine signature and reject every forged one?"
            why = ("Why it matters: a post-quantum signature is only worth moving to if it is built to the standard (FIPS 204). This checks "
                   "the new code against official cases instead of taking it on trust.")
        return self._spec(
            kind,
            f"Puts {name}'s {algorithm} through {total} official cases from NIST and Project Wycheproof, each with a published right answer: "
            + ", ".join(p["title"].lower() for p in parts[:-1]) + f" and {parts[-1]['title'].lower()}.",
            why, question,
            "Run one adapter command per case with the published inputs, and compare the SHA-256 of the answer with the SHA-256 of the "
            "published answer. Where the case holds a key or an input that must be refused, note whether the library refused it.",
            target,
            {"algorithm": algorithm, "files": files, "parts": parts, "cases": total, "left_out": exam["left_out"],
             "sources": {"nist": pq_vectors.ACVP_URL, "wycheproof": pq_vectors.WYCHEPROOF_PQ_URL}},
            inputs_text,
            {"kind": "pq_broken_copies", "text": control_text, "must": must},
            {"type": "pq_known_answers", "answer": "the published answer, by fingerprint", "refuse": "refused", "accept": "not refused",
             "reject": "said not genuine"},
            f"Passed only if all {total} answers are right: the published answer where there is one, a refusal where the input must be refused. "
            "Any wrong answer means Failed. Timing is not looked at: this test says nothing about timing attacks.")

    def _mlkem_vectors(self, claims: list[dict], ref: str | None = None) -> dict:
        return self._pq_exam("mlkem_vectors", claims, ref)

    def _mldsa_vectors(self, claims: list[dict], ref: str | None = None) -> dict:
        return self._pq_exam("mldsa_vectors", claims, ref)

    def _official_vectors(self, claims: list[dict], ref: str | None = None) -> dict:
        target = self._signing_target(claims, ref, "official_vectors")
        name = target["component"]
        ecdsa, ed = vectors.WYCHEPROOF["ecdsa_p256"], vectors.WYCHEPROOF["ed25519"]
        short = vectors.WYCHEPROOF_COMMIT[:7]
        return self._spec(
            "official_vectors",
            f"Puts {name} through an outside exam: the {ecdsa['cases']} ECDSA P-256 cases of Project Wycheproof, each with a published right answer, and counts any it gets wrong.",
            f"Why it matters: an outside exam we didn't write. {ecdsa['cases']} cases from Project Wycheproof, started by Google's security team, built to catch known mistakes in signing software.",
            f"Does {name} give the right answer on every official ECDSA P-256 test case?",
            "Run the verify command once per case and compare its answer with the published one.",
            target,
            {"files": [{"set": "ecdsa_p256", "file": ecdsa["file"], "sha256": ecdsa["sha256"], "cases": ecdsa["cases"], "used_on": "component"},
                       {"set": "ed25519", "file": ed["file"], "sha256": ed["sha256"], "cases": ed["cases"], "used_on": "reference"}],
             "commit": vectors.WYCHEPROOF_COMMIT, "source_url": vectors.WYCHEPROOF_SOURCE_URL},
            [f"Wycheproof testvectors_v1/{ecdsa['file']} ({ecdsa['cases']} cases), pinned to commit {short}.",
             (f"The second official file, {ed['file']}, is not used on this component: this test checks its ECDSA P-256 signatures. It is run on the reference library."
              if real_libraries.known(name) is not None else   # a real library may offer more than ECDSA P-256 (phase 4c)
              f"The second official file, {ed['file']}, is not used on this component: {name} only does ECDSA P-256. It is run on the reference library.")],
            {"kind": "accept_all_verifier",
             "text": "The same cases run against a deliberately broken signer, which must get every invalid case wrong.",
             "must": {"wrong_on": "every invalid case"}},
            {"type": "all_cases_match", "valid": "accept", "invalid": "reject", "acceptable": "not counted"},
            f"Passed only if all {ecdsa['cases']} answers are right. Any wrong answer means Failed.")

    def _bad_signatures(self, claims: list[dict], ref: str | None = None) -> dict:
        target = self._signing_target(claims, ref, "bad_signatures")
        name = target["component"]
        pin = vectors.BAD_SIGNATURES
        total, accept = pin["cases"], 2
        return self._spec(
            "bad_signatures",
            f"Tries our own short list of {total - accept} forged signatures on {name} (zeros, out-of-range numbers, changed, cut-short and badly encoded ones), plus {accept} genuine ones it must accept.",
            f"Why it matters: our own short list of the {total - accept} forgeries an attacker would try first, such as a signature made of zeros. Accepting even one lets someone fake a signature.",
            f"Does {name} reject every signature it must reject, and still accept genuine ones?",
            "Run the verify command once per case. The cases are a fixed list made once from a test key: genuine signatures, and the same signatures or messages changed in ways that must be rejected.",
            target,
            {"file": pin["file"], "sha256": pin["sha256"], "cases": total, "must_reject": total - accept, "must_accept": accept},
            [f"A fixed list of {total} cases ({pin['file']}): {total - accept} signatures that must be rejected and {accept} genuine ones that must be accepted.",
             "The list was built once from a test key that was thrown away; only the public key is kept."],
            {"kind": "accept_all_verifier",
             "text": "The same cases run against a deliberately broken signer, which must accept every bad signature.",
             "must": {"wrong_on": "every invalid case"}},
            {"type": "all_cases_match", "valid": "accept", "invalid": "reject", "acceptable": "not counted"},
            f"Passed only if all {total - accept} bad signatures are rejected and both genuine ones are accepted. Any wrong answer means Failed.")

    def _speed_size(self, claims: list[dict], ref: str | None = None) -> dict:
        target = self._signing_target(claims, ref, "speed_size")
        rounds, repeats = self.speed_rounds, self.speed_repeats
        pairs = rounds * repeats
        return self._spec(
            "speed_size",
            f"Times signing and checking inside the program ({pairs} repeats each) and records key and signature sizes. Reports numbers; no pass or fail on the first run.",
            "Why it matters: gives a baseline, so a later version that slows down gets noticed.",
            "How long do signing and checking take, how big are keys and signatures, and is a new version slower?",
            f"Run the component's bench command in {rounds} rounds of {repeats}: {pairs} signs and {pairs} verifies, timed inside the program, so start-up is not counted. On a retest the old and the new version are measured side by side in alternating rounds, with the same key and message, while no other test is running.",
            target,
            {"message": SPEED_MESSAGE, "rounds": rounds, "repeats": repeats, "pairs": pairs, "warmups": 2,
             "control_delay_ms": CONTROL_DELAY_MS, "exclusive": True, "reference": "cryptography, in-process, for scale only"},
            ["One fixed 32-byte test message and a test key made for this run.",
             "The reference library (cryptography) is timed in the same way, for scale only."],
            {"kind": "slowed_signer", "delay_ms": CONTROL_DELAY_MS,
             "text": f"A deliberately slowed copy of the signer ({CONTROL_DELAY_MS} ms added to every sign and every verify), which must be flagged as slower by the same rule.",
             "must": {"flagged": ["sign", "verify"]}},
            {"type": "paired_slowdown", "first_run": "report_only", "ops": ["sign", "verify"], "noise_factor_milli": 1858,
             "sigma": 4, "floor_percent": 3},
            "First run: report numbers only. Retest: for each matched pair of timings take new minus old; flag a slowdown only if the median difference, less 4 times its measured noise, is more than 3% of the old version's median. Otherwise: No slowdown beyond measured noise.")

    def _pq_readiness(self, claims: list[dict], target: str | None = None) -> dict:
        """Since phase 4a this test makes the same measurement as the Migration step and is judged by the same rule,
        so the two never disagree. (A test locked before that keeps its own rule, "pq_group_offered".)"""
        address = target if target is not None and target in servers(claims) else _server_address(claims) if target is None else None
        if address is None:
            raise CannotDesign("The file names no server address to check.")
        return self._spec(
            "pq_readiness",
            f"Checks whether the server at {address} offers a quantum-resistant key exchange (such as {PQ_GROUP}).",
            "Why it matters: shows how far the server is from the post-quantum move.",
            f"Does the server at {address} offer a quantum-resistant key exchange (hybrid, such as {PQ_GROUP}, or ML-KEM by itself)?",
            PQ_METHOD,
            {"kind": "server", "address": address},
            {"group": PQ_GROUP, "families": PQ_FAMILIES, "costs": False,
             "checker": "hand-built hellos, and the OpenSSL inside the cryptography library"},
            [f"Key exchanges asked for: hybrid ({', '.join(PQ_FAMILIES['hybrid'])}), ML-KEM by itself and classical.",
             "No OpenSSL program or Docker is needed: the hellos are built by this app."],
            PQ_CONTROL,
            {"type": "pq_status_offered"},
            "Offered only on positive proof: the server asks for a hybrid or ML-KEM key, or completes a full hybrid handshake. "
            "Not offered only if it refuses every post-quantum hello and the full hybrid handshake with a TLS refusal, accepts a "
            "classical key exchange, and both control servers were read correctly. Anything else: Couldn't run.")

    def _pq_status(self, claims: list[dict], target: str | None = None) -> dict:
        """The Migration step's measurement of one server (phase 4a). Not a pass-or-fail test: it reports a status."""
        if target is None or target not in servers(claims):
            raise CannotDesign("The file names no such server.")
        g = NIST_GUIDANCE
        return self._spec(
            "pq_status",
            f"Measures where the server at {target} stands on post-quantum key exchange, and what going there would cost.",
            "Why it matters: a migration plan needs to start from what each system does today, measured.",
            f"Is the key exchange of the server at {target} classical, hybrid or post-quantum only, and what does each cost in size and time?",
            PQ_METHOD + " For the cost table: 10 classical and 10 hybrid handshakes taken in turn, on this server when it offers "
            "hybrid, otherwise on our own hybrid test server.",
            {"kind": "server", "address": target},
            {"families": PQ_FAMILIES, "costs": True, "timing_rounds": 10, "guidance": {"minimum_bits": g["minimum_bits"]}, "tracks": True},
            ["Key exchanges asked for: hybrid, ML-KEM by itself and classical; and one hello with a hybrid and a classical key at once, "
             "in both orders.", f"Certificate minimum sizes: {g['minimum_source']['title']}."],
            PQ_CONTROL_TRACKS, {"type": "pq_status_tracks"}, PQ_RULE_TEXT + " " + PQ_TRACKS_RULE_TEXT)

    def _signing_status(self, claims: list[dict], ref: str | None = None) -> dict:
        """The Migration step's measurement of one signing program (phase 4a): what it signs with today, confirmed by
        an independent library, and its speed and sizes next to ML-DSA-65 on the reference library."""
        target = self._signing_target(claims, ref)
        name, algorithm = target["component"], target["algorithm"]
        if real_libraries.known(name) is not None and not algorithm.startswith("ML-"):
            return self._real_signing_status(target)
        return self._spec(
            "signing_status",
            f"Measures what {name} signs with today, and what a post-quantum signature would cost next to it.",
            "Why it matters: a migration plan needs to start from what each system does today, measured.",
            f"Does {name} sign with a classical or a post-quantum algorithm, and what would ML-DSA-65 cost in time and size?",
            "Ask the program what it signs with, have it sign one test message, and check that signature with an independent "
            "library. Then time its bench command next to ML-DSA-65 on the reference library.",
            target,
            {"claimed_algorithm": algorithm,
             "mldsa": {"algorithm": "ML-DSA-65", "implementation": "cryptography (hazmat mldsa)", "repeats": 200,
                       "component_repeats": 100, "message": SPEED_MESSAGE, "label": MLDSA_LABEL}},
            [f"The claim from the file: {algorithm}.",
             "ML-DSA-65 from the reference library (cryptography): reference figures, not a measurement of production software of yours."],
            {"kind": "independent_library",
             "text": "An independent library must confirm the program's key and signature, and must reject an ML-DSA-65 signature with one byte changed.",
             "must": {"confirmed": True}},
            {"type": "signing_status"},
            "Classical or post-quantum by the family of the algorithm the program reports, and only once the independent library "
            "has confirmed its signature. Anything else: couldn't check.")

    def _real_signing_status(self, target: dict) -> dict:
        """Phase 4c: the same measurement for a real library that signs with a classical algorithm, plus one more
        question that is measured, not looked up: can this library make a post-quantum signature today?"""
        name, algorithm = target["component"], target["algorithm"]
        return self._spec(
            "signing_status",
            f"Measures what {name} signs with today, whether it can already make a post-quantum signature, and what one would cost next to it.",
            "Why it matters: a migration plan needs to start from what each system does today, measured.",
            f"Does {name} sign with a classical or a post-quantum algorithm, can it make an ML-DSA-65 signature today, and what would that cost in time and size?",
            "Ask the library what it signs with, have it sign one test message, and check that signature with an independent "
            "library. Then ask it to make one ML-DSA-65 signature, checked the same way. Then time its bench command next to ML-DSA-65 "
            "on the reference library.",
            target,
            {"claimed_algorithm": algorithm, "capability": {"algorithm": PQ_SIGNATURE},
             "mldsa": {"algorithm": "ML-DSA-65", "implementation": "cryptography (hazmat mldsa)", "repeats": 200,
                       "component_repeats": 100, "message": SPEED_MESSAGE, "label": MLDSA_LABEL}},
            [f"The claim from the file: {algorithm}.",
             "ML-DSA-65 from the reference library (cryptography): reference figures, not a measurement of production software of yours."],
            {"kind": "independent_library",
             "text": "An independent library must confirm the library's key and signature, and must reject an ML-DSA-65 signature with one byte changed.",
             "must": {"confirmed": True}},
            {"type": "signing_status"},
            "Classical or post-quantum by the family of the algorithm the library reports, and only once the independent library "
            "has confirmed its signature. It can make post-quantum signatures only if it made an ML-DSA-65 signature that the "
            "independent library confirmed. Anything else: couldn't check.")

    def _mldsa_compare(self, claims: list[dict], ref: str | None = None) -> dict:
        if _software(claims, ref) is not None:
            self._signing_target(claims, ref, "mldsa_compare")   # it compares a classical signer with ML-DSA-65: not for a post-quantum program
        software = _software(claims, ref)
        name = software["component"] if software else "the signing component"
        target = {"kind": "software", **software} if software else {"kind": "reference"}
        return self._spec(
            "mldsa_compare",
            CATALOG_DESCRIPTIONS["mldsa_compare"].format(component=name),
            "Why it matters: shows what moving to a post-quantum signature would cost in time and size.",
            "How fast is a post-quantum signature (ML-DSA-65), and how big are its keys and signatures, next to the signing component's?",
            "Time key generation, signing and checking 200 times each with the cryptography library's ML-DSA-65, and record the public key and signature sizes. Time the signing component's bench command for comparison.",
            target,
            {"algorithm": "ML-DSA-65", "implementation": "cryptography (hazmat mldsa)", "repeats": 200, "component_repeats": 100,
             "message": SPEED_MESSAGE, "label": MLDSA_LABEL},
            ["ML-DSA-65 from the reference library (cryptography): reference figures, not a measurement of production software of yours.",
             "One fixed 32-byte test message and test keys made for this run."],
            {"kind": "altered_signature",
             "text": "A genuine ML-DSA-65 signature must be accepted, and the same signature with one byte changed must be rejected.",
             "must": {"rejected": True}},
            {"type": "report_only"},
            "Reports numbers only (Measured). No pass or fail.")

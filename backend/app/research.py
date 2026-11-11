"""The research engine socket. Everything that thinks about tests goes through one interface:

    propose_tests(claims)  -> the suggested tests, each written down in full before anything runs
    design_test(request)   -> one test from the catalog (used by "+ Add test")
    review(result)         -> the review of a run (never done by the engine that proposed the test)
    dig_deeper(finding)    -> a research request, saved as "waiting for research engine"

This file holds the rule-based engine shipped in this version. It proposes and designs tests and files
research requests. It holds NO verdict logic: results are decided only in reviewer.py, from raw outputs.
A locked test never names a component version, a mode or a time, so the same test (same fingerprint) is
rerun unchanged on a new version."""
from __future__ import annotations

from typing import Protocol

from . import vectors
from .guidance import NIST_GUIDANCE
from .reviewer import ReviewNotAllowed  # the one shared name; the reviewer imports nothing from here

SPEC_SCHEMA = "isogeny.test-spec/1"
TLS_VERSIONS = ["TLS 1.0", "TLS 1.1", "TLS 1.2", "TLS 1.3"]
SUGGESTED_KINDS = ("tls_versions", "certificate", "official_vectors", "bad_signatures", "speed_size")
CATALOG = ("pq_readiness", "mldsa_compare")
ALL_KINDS = SUGGESTED_KINDS + CATALOG
SERVER_KINDS = ("tls_versions", "certificate", "pq_readiness")
PQ_GROUP = "X25519MLKEM768"
PQ_LINE = "Negotiated TLS1.3 group: X25519MLKEM768"
SPEED_MESSAGE = "45766964656e6365204c61622073706565642074657374206d6573736167652e"  # 32 fixed bytes of text
CONTROL_DELAY_MS = 6
MLDSA_LABEL = "reference, not production"
RESEARCH_STATUS = "waiting for research engine"

TITLES = {
    "tls_versions": "Old TLS versions", "certificate": "Certificate strength", "official_vectors": "Official test vectors",
    "bad_signatures": "Bad signatures", "speed_size": "Speed and size", "pq_readiness": "Post-quantum readiness",
    "mldsa_compare": "ML-DSA-65 comparison",
}
CATALOG_DESCRIPTIONS = {
    "pq_readiness": "Checks whether the server offers the newer quantum-resistant key exchange (X25519MLKEM768).",
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


def join_and(items: list[str]) -> str:
    items = list(items)
    return "".join(items) if len(items) <= 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _first(claims: list[dict], location_kind: str, kind: str, need: str) -> dict | None:
    for c in claims:
        if c.get("location_kind") == location_kind and c.get("kind") == kind and (c.get("detail") or {}).get(need):
            return c
    return None


def _server_address(claims: list[dict]) -> str | None:
    for c in claims:
        if c.get("location_kind") == "server" and c.get("location"):
            return str(c["location"])
    return None


def _software(claims: list[dict]) -> dict | None:
    c = _first(claims, "software", "signature_algorithm", "component")
    if c is None:
        return None
    d = c["detail"]
    return {"component": str(d["component"]), "algorithm": str(d.get("algorithm") or c.get("claimed_value") or "")}


class RuleEngine:
    engine_id = "isogeny.rule-engine/1"

    def __init__(self, speed_rounds: int = 40, speed_repeats: int = 5):
        self.speed_rounds, self.speed_repeats = int(speed_rounds), int(speed_repeats)

    # ---------------------------------------------------------------- the interface

    def propose_tests(self, claims: list[dict]) -> dict:
        tests, notes = [], []
        for kind in SUGGESTED_KINDS:
            try:
                tests.append(self._design(kind, claims))
            except CannotDesign as exc:
                notes.append(f"{TITLES[kind]}: not suggested. {exc}")
        return {"tests": tests, "notes": notes}

    def design_test(self, request: dict) -> dict:
        kind = request.get("catalog_id")
        if kind not in ALL_KINDS:
            raise CannotDesign("That test is not in the catalog.")
        return self._design(kind, list(request.get("claims") or []))

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

    # ---------------------------------------------------------------- the tests, written down in full

    def _design(self, kind: str, claims: list[dict]) -> dict:
        return getattr(self, "_" + kind)(claims)

    @staticmethod
    def _spec(kind: str, description: str, why: str, question: str, method: str, target: dict, inputs: dict,
              inputs_text: list[str], control: dict, rule: dict, rule_text: str) -> dict:
        return {"schema": SPEC_SCHEMA, "kind": kind, "title": TITLES[kind], "card": {"description": description, "why": why},
                "question": question, "method": method, "target": target, "inputs": inputs, "inputs_text": inputs_text,
                "control": control, "rule": rule, "rule_text": rule_text}

    def _tls_versions(self, claims: list[dict]) -> dict:
        claim = _first(claims, "server", "protocol_versions", "versions")
        if claim is None:
            raise CannotDesign("The file makes no claim about TLS versions for a server.")
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

    def _certificate(self, claims: list[dict]) -> dict:
        claim = _first(claims, "server", "certificate", "algorithm")
        if claim is None:
            raise CannotDesign("The file makes no claim about a server certificate's algorithm.")
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

    def _signing_target(self, claims: list[dict]) -> dict:
        software = _software(claims)
        if software is None:
            raise CannotDesign("The file names no signing component.")
        return {"kind": "software", **software}

    def _official_vectors(self, claims: list[dict]) -> dict:
        target = self._signing_target(claims)
        name = target["component"]
        ecdsa, ed = vectors.WYCHEPROOF["ecdsa_p256"], vectors.WYCHEPROOF["ed25519"]
        short = vectors.WYCHEPROOF_COMMIT[:7]
        return self._spec(
            "official_vectors",
            f"Gives {name} {ecdsa['cases']} published signature cases with known right answers (Project Wycheproof, ECDSA P-256) and counts any it gets wrong.",
            "Why it matters: these cases were written to catch real, known mistakes.",
            f"Does {name} give the right answer on every official ECDSA P-256 test case?",
            "Run the verify command once per case and compare its answer with the published one.",
            target,
            {"files": [{"set": "ecdsa_p256", "file": ecdsa["file"], "sha256": ecdsa["sha256"], "cases": ecdsa["cases"], "used_on": "component"},
                       {"set": "ed25519", "file": ed["file"], "sha256": ed["sha256"], "cases": ed["cases"], "used_on": "reference"}],
             "commit": vectors.WYCHEPROOF_COMMIT, "source_url": vectors.WYCHEPROOF_SOURCE_URL},
            [f"Wycheproof testvectors_v1/{ecdsa['file']} ({ecdsa['cases']} cases), pinned to commit {short}.",
             f"The second official file, {ed['file']}, is not used on this component: {name} only does ECDSA P-256. It is run on the reference library."],
            {"kind": "accept_all_verifier",
             "text": "The same cases run against a deliberately broken signer, which must get every invalid case wrong.",
             "must": {"wrong_on": "every invalid case"}},
            {"type": "all_cases_match", "valid": "accept", "invalid": "reject", "acceptable": "not counted"},
            f"Passed only if all {ecdsa['cases']} answers are right. Any wrong answer means Failed.")

    def _bad_signatures(self, claims: list[dict]) -> dict:
        target = self._signing_target(claims)
        name = target["component"]
        pin = vectors.BAD_SIGNATURES
        total, accept = pin["cases"], 2
        return self._spec(
            "bad_signatures",
            f"Feeds {name} signatures it must reject: changed messages, changed signatures, wrong lengths, zeros and out-of-range values.",
            "Why it matters: accepting one forged signature defeats the point of signing.",
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

    def _speed_size(self, claims: list[dict]) -> dict:
        target = self._signing_target(claims)
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

    def _pq_readiness(self, claims: list[dict]) -> dict:
        address = _server_address(claims)
        if address is None:
            raise CannotDesign("The file names no server address to check.")
        return self._spec(
            "pq_readiness",
            f"Checks whether the server at {address} offers the newer quantum-resistant key exchange ({PQ_GROUP}).",
            "Why it matters: shows how far the server is from the post-quantum move.",
            f"Does the server at {address} offer the quantum-resistant key exchange {PQ_GROUP}?",
            f"Make one TLS 1.3 handshake that offers only {PQ_GROUP}, with OpenSSL's own client (openssl s_client), and one ordinary handshake to the same server. Handshakes only.",
            {"kind": "server", "address": address},
            {"group": PQ_GROUP, "checker": "openssl s_client, OpenSSL 3.5 or newer"},
            [f"Key exchange asked for: {PQ_GROUP}.", "Checker: openssl s_client from OpenSSL 3.5 or newer (older versions cannot offer this key exchange)."],
            {"kind": "pq_server",
             "text": f"A test server on this computer that does offer {PQ_GROUP}, which must be detected as offering it.",
             "must": {"detected": "offered"}},
            {"type": "pq_group_offered", "offered_line": PQ_LINE,
             "not_offered_needs": ["alert_40_from_pq_only_hello", "normal_handshake_ok", "control_offered"]},
            f"Offered only if the checker prints the line \"{PQ_LINE}\". Not offered only if the server refuses that handshake (alert 40), an ordinary handshake to it succeeds, and the control server is detected as offering it. Anything else: Couldn't run.")

    def _mldsa_compare(self, claims: list[dict]) -> dict:
        software = _software(claims)
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

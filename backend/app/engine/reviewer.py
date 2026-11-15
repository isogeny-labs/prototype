"""The separate review step. This is the ONLY module that decides a result.

It is given the locked test, its fingerprint, who proposed it, and one run record. It recomputes the
fingerprint, works out from the RAW outputs whether the control behaved as it must, checks the reference
library's answers where the test needs them, and only then applies the test's pass/fail rule.
Order of decisions, the same for every test:
  1. the locked test does not match its fingerprint      -> Couldn't trust this run
  2. the run reported a problem (it could not run)       -> Couldn't run (reason)
  3. the control did not behave exactly as it must       -> Couldn't trust this run
  4. the reference library got a case wrong              -> Couldn't trust this run
  5. the rule, applied to the raw outcome                -> the result

It also decides, in review_proof, whether a proposed code change may be offered: from the proof record only
(the reviewed results of every test rerun on the changed code, next to the first results), never from a file.

It never reviews a test or a change it proposed itself. It imports nothing from the engine that proposes
them, the code that runs tests or the code that words results for the screen (a test checks this)."""
from __future__ import annotations

import math
import re
from statistics import median

from app.engine import pq_vectors
from app.engine import vectors
from app.canonical import sha256_hex

REVIEW_SCHEMA = "isogeny.review/1"
PROOF_SCHEMA = "isogeny.proof/1"
PROOF_REVIEW_SCHEMA = "isogeny.proof-review/1"
# What "passed on the changed code" means for each kind of test that runs it. A test whose code here is
# "measured" only reports numbers: it has no pass or fail, so in a proof it only has to run, and by itself it
# shows nothing about a change.
PROOF_PASS_CODES = {"official_vectors": "passed", "bad_signatures": "passed", "speed_size": "no_slowdown", "mldsa_compare": "measured"}
REPORT_ONLY_CODE = "measured"
SPEED_KIND = "speed_size"  # the test that makes the speed comparison a proof must hold

# Why a test could not run, in plain words (the text inside "Couldn't run (...)").
COULDNT_RUN_REASONS = {
    "checker_too_old": "needs OpenSSL 3.5 or newer",
    "checker_cannot_reach": "the checker could not reach the server",
    "address_not_confirmed": "address not confirmed",
    "server_unreachable": "the server did not answer",
    "not_a_demo_component": "only our demo components can be run in this version",
    "component_no_answer": "the component did not answer",
    "timeout": "it took too long",
    "vector_file_changed": "the official test file on disk has changed",
    "spec_changed": "the locked test no longer matches its fingerprint",
    "isolated_unavailable": "isolated mode is not available",
    "unreadable_answer": "the server's answer could not be read",
    "harness_error": "the test could not be run",
    # phase 4a: the post-quantum status measurement
    "pq_engine_unavailable": "this computer's crypto library can't run post-quantum TLS",
    "unclear_answer": "the server gave no clear answer",
    "claim_not_confirmed": "the file's claim about what it signs with was not confirmed",
    "unknown_algorithm": "the algorithm is not one this version knows",
    # phase 4b: a run on a test copy
    "copy_unavailable": "the test copy could not be started",
    # phase 4c: real libraries
    "needs_isolated_mode": "needs isolated mode",
    "real_image_missing": "this library's container image is not prepared",
}
# Phase 4a. The key-exchange groups by family, and the signature algorithms by family (spelled as in the app).
HYBRID_GROUPS = ("X25519MLKEM768", "SecP256r1MLKEM768", "SecP384r1MLKEM1024")
PURE_GROUPS = ("MLKEM768", "MLKEM1024", "MLKEM512")
OLD_TLS = ("TLS 1.2", "TLS 1.1", "TLS 1.0")   # no post-quantum key exchange exists in these
CLASSICAL_SIGNATURES = ("ECDSA", "RSA", "ED25519", "ED448", "DSA")
POST_QUANTUM_SIGNATURES = ("ML-DSA", "MLDSA", "SLH-DSA", "SLHDSA")


def _median_or_none(values: list) -> float | None:
    good = [float(v) for v in values if isinstance(v, (int, float))]
    return round(median(good), 3) if good else None


def _timing_summary(timing: object) -> dict | None:
    """Medians of the handshakes that were timed: the classical ones, and when hybrid ones were taken in turn with
    them, the difference between matched pairs and how much it moved (its middle half), so a difference can be
    called real or not."""
    if not isinstance(timing, dict):
        return None
    classical = [c for c in timing.get("classical_ms") or [] if isinstance(c, (int, float))]
    pairs = [(c, h) for c, h in zip(timing.get("classical_ms") or [], timing.get("hybrid_ms") or [])  # noqa: B905
             if isinstance(c, (int, float)) and isinstance(h, (int, float))]
    out = {"handshakes": len(classical), "classical_median_ms": _median_or_none(classical) if len(classical) >= 4 else None,
           "pairs": len(pairs), "hybrid_median_ms": None, "difference_ms": None, "difference_low_ms": None,
           "difference_high_ms": None, "beyond_noise": None}
    if len(pairs) >= 4:
        diffs = sorted(h - c for c, h in pairs)
        low, high = diffs[len(diffs) // 4], diffs[(3 * len(diffs)) // 4 - (1 if len(diffs) % 4 == 0 else 0)]
        out.update(hybrid_median_ms=_median_or_none([h for _, h in pairs]), difference_ms=round(median(diffs), 3),
                   difference_low_ms=round(low, 3), difference_high_ms=round(high, 3), beyond_noise=bool(low > 0 or high < 0))
    return out if out["classical_median_ms"] is not None or out["pairs"] >= 4 else None


def _sizes(handshake: object) -> dict | None:
    if not isinstance(handshake, dict) or handshake.get("outcome") != "completed":
        return None
    return {k: handshake.get(k) for k in ("group", "tls_version", "client_hello_bytes", "client_share_bytes", "server_share_bytes",
                                          "certificate_message_bytes", "signature_bytes")}


def _certificate_facts(cert: object, minimum_bits: object) -> dict | None:
    if not isinstance(cert, dict):
        return None
    family = str(cert.get("algorithm"))
    post_quantum = family.upper().startswith(("MLDSA", "ML-DSA", "SLHDSA", "SLH-DSA"))
    name = str(cert.get("signature_algorithm") or family) if post_quantum else certificate_name(cert)
    minimum = minimum_bits.get(family) if isinstance(minimum_bits, dict) else None
    bits = cert.get("key_bits")
    return {"name": name, "key_bits": bits, "post_quantum": post_quantum, "minimum_bits": minimum,
            "weak": bool(minimum is not None and isinstance(bits, int) and bits < int(minimum)),
            "public_key_bytes": cert.get("public_key_bytes"), "der_bytes": cert.get("der_bytes")}


def _auth_track(subject: dict, certificate: dict | None) -> dict:
    """The authentication track of a server (phase 4b): its certificate key and the algorithm it signs the handshake
    with. Classical when both are classical, Post-quantum when both are post-quantum, otherwise couldn't check."""
    from app.checks.tls_names import SIGNATURE_SCHEMES, scheme_family
    scheme = next((h.get("signature_scheme") for h in (subject.get("classical_client"), subject.get("hybrid_handshake"),
                                                       subject.get("pure_handshake"))
                   if isinstance(h, dict) and h.get("outcome") == "completed" and h.get("signature_scheme") is not None), None)
    family = scheme_family(scheme)
    out = {"certificate": (certificate or {}).get("name"), "signature": SIGNATURE_SCHEMES.get(scheme), "signature_scheme": scheme,
           "status": "couldnt_check", "why": None}
    if not certificate:
        out["why"] = "no_certificate"
    elif family is None:
        out["why"] = "no_signature"
    elif certificate.get("post_quantum") and family == "post_quantum":
        out["status"] = "post_quantum"
    elif not certificate.get("post_quantum") and family == "classical":
        out["status"] = "classical"
    else:
        out["why"] = "mixed"
    return out


def _picked(handshake: object) -> str | None:
    """Which family a "both keys at once" handshake ended with: hybrid, classical, or None when it didn't complete."""
    if not isinstance(handshake, dict) or handshake.get("outcome") != "completed":
        return None
    return "hybrid" if handshake.get("group") in HYBRID_GROUPS else "pure" if handshake.get("group") in PURE_GROUPS else "classical"


def pq_status_of(raw: dict, minimum_bits: object = None, tracks: bool = False) -> dict:
    """The post-quantum status of one server, from the raw measurement alone (phase 4a). Returns
    {"control": {...}, "code", "reason_code", "detail"}; code is hybrid, pq_only, classical or couldnt_run.

    Hybrid            - positive proof only: the server asked for a hybrid group, or a full hybrid handshake completed.
    Post-quantum only - it accepted ML-KEM by itself and refused the hybrid and the classical hello (and no classical
                        handshake completed).
    Classical         - the hybrid and the ML-KEM hello and the full hybrid handshake each got a TLS refusal, and a
                        classical key exchange was accepted.
    Anything else     - couldn't check. Silence is never read as a status."""
    def state(probes: object, family: str) -> str | None:
        probe = probes.get(family) if isinstance(probes, dict) else None
        return probe.get("state") if isinstance(probe, dict) else None

    def group(probes: object, family: str) -> str | None:
        probe = probes.get(family) if isinstance(probes, dict) else None
        return probe.get("group") if isinstance(probe, dict) and probe.get("state") == "offered" else None

    control = raw.get("control")
    if not isinstance(control, dict) or not isinstance(control.get("hybrid"), dict) or not isinstance(control.get("classical"), dict):
        why = control.get("error") if isinstance(control, dict) else None
        control_out = {"outcome": "errored", "reason": str(why or "the control servers could not be started or read")}
    else:
        hp, cp = control["hybrid"].get("probes"), control["classical"].get("probes")
        read_right = (group(hp, "hybrid") in HYBRID_GROUPS and state(hp, "classical") == "offered"
                      and state(cp, "hybrid") == "refused" and state(cp, "pure") == "refused" and state(cp, "classical") == "offered")
        control_out = ({"outcome": "as_expected", "reason": "control_servers_read_correctly"} if read_right
                       else {"outcome": "not_as_expected", "reason": "a_control_server_was_misread"})

    subject = raw["subject"]
    probes = subject["probes"]
    h, p, c = state(probes, "hybrid"), state(probes, "pure"), state(probes, "classical")
    full_hybrid, full_pure = subject.get("hybrid_handshake") or {}, subject.get("pure_handshake") or {}
    client = subject.get("classical_client") or {}
    container = subject.get("container") if isinstance(subject.get("container"), dict) else {}
    versions = subject.get("versions") or {}
    accepted = [v for v in ("TLS 1.3", *OLD_TLS) if (versions.get(v) or {}).get("state") == "accepted"]
    old_accepted = any(v in OLD_TLS for v in accepted)

    hybrid_proof = [name for name, seen in (
        ("probe", group(probes, "hybrid") in HYBRID_GROUPS),
        ("handshake", full_hybrid.get("outcome") == "completed" and full_hybrid.get("group") in HYBRID_GROUPS),
        ("container", bool(container.get("ran") and container.get("negotiated_line")))) if seen]
    hybrid_groups = [g for g in dict.fromkeys([
        group(probes, "hybrid") if group(probes, "hybrid") in HYBRID_GROUPS else None,
        full_hybrid.get("group") if full_hybrid.get("outcome") == "completed" and full_hybrid.get("group") in HYBRID_GROUPS else None,
        "X25519MLKEM768" if container.get("ran") and container.get("negotiated_line") else None]) if g]
    pure_group = group(probes, "pure") or (full_pure.get("group") if full_pure.get("outcome") == "completed"
                                           and full_pure.get("group") in PURE_GROUPS else None)
    client_classical = client.get("outcome") == "completed" and client.get("group") not in HYBRID_GROUPS + PURE_GROUPS
    # "Accepted" means a classical handshake COMPLETED: by the classical-only client, or in TLS 1.2 or older (where no
    # post-quantum key exchange exists). A server that only asks for a classical key and then goes quiet has not.
    classical_accepted = client_classical or old_accepted
    if client_classical or old_accepted:
        classical_client = "connects"
    elif client.get("outcome") == "refused" and c == "refused":
        classical_client = "cannot"
    else:
        classical_client = "unknown"
    tls13_seen = (any(s == "offered" for s in (h, p, c)) or "TLS 1.3" in accepted
                  or any(x.get("outcome") == "completed" and x.get("tls_version") == "TLS 1.3" for x in (client, full_hybrid, full_pure)))
    tls13 = "on" if tls13_seen else "off" if c == "refused" else "unknown"
    witnesses = {"builtin": full_hybrid.get("outcome") or "not_run",
                 "container": ("not_run" if not container.get("ran") else "completed" if container.get("negotiated_line")
                               else "refused" if container.get("alert") == 40 else "unclear")}

    unclear = [name for name, value in (("the hybrid hello", h), ("the ML-KEM hello", p), ("the classical hello", c)) if value not in ("offered", "refused")]
    if hybrid_groups:
        code, reason_code = "hybrid", None
    elif pure_group and h == "refused" and c == "refused" and classical_client != "connects":
        code, reason_code = "pq_only", None
    elif (not pure_group and h == "refused" and p == "refused" and full_hybrid.get("outcome") == "refused" and classical_accepted):
        code, reason_code = "classical", None
    else:
        code, reason_code = "couldnt_run", "unclear_answer"
        if h == "refused" and p == "refused" and full_hybrid.get("outcome") != "refused":
            unclear.append("the full hybrid handshake")
        if not classical_accepted:
            unclear.append("a full classical handshake")
    reference = control.get("reference") if isinstance(control, dict) and isinstance(control.get("reference"), dict) else {}
    detail = {"status": code, "hybrid_groups": hybrid_groups, "hybrid_proof": hybrid_proof, "pure_group": pure_group,
              "classical_group": group(probes, "classical") or (client.get("group") if client_classical else None),
              "classical_accepted": bool(classical_accepted), "classical_client": classical_client, "tls13": tls13,
              "tls_versions": accepted, "certificate": _certificate_facts(subject.get("certificate"), minimum_bits),
              "witnesses": witnesses, "unclear": unclear if code == "couldnt_run" else [],
              "sizes": {"classical": _sizes(client), "hybrid": _sizes(full_hybrid), "pure": _sizes(full_pure),
                        "reference_classical": _sizes(reference.get("classical")), "reference_hybrid": _sizes(reference.get("hybrid"))},
              "timing": _timing_summary(subject.get("timing")), "reference_timing": _timing_summary(reference.get("timing")),
              "reference_classical_client": (reference.get("classical") or {}).get("outcome") if reference else None}
    if tracks:
        # Phase 4b. The controls must also read right on both "both keys at once" hellos: our hybrid server takes hybrid
        # when hybrid is listed first and classical when classical is (it follows the client's order), and our classical
        # one takes classical both times. Otherwise the run is not trusted, whatever the server did.
        if control_out["outcome"] == "as_expected":
            hc = (control.get("hybrid") or {}).get("default_choice") if isinstance(control, dict) else None
            cc = (control.get("classical") or {}).get("default_choice") if isinstance(control, dict) else None
            hc, cc = (hc if isinstance(hc, dict) else {}), (cc if isinstance(cc, dict) else {})
            read = (_picked(hc.get("hybrid_first")), _picked(hc.get("classical_first")),
                    _picked(cc.get("hybrid_first")), _picked(cc.get("classical_first")))
            if read != ("hybrid", "classical", "classical", "classical"):
                control_out = {"outcome": "not_as_expected", "reason": "a_control_server_was_misread"}
        choice = subject.get("default_choice") if isinstance(subject.get("default_choice"), dict) else None
        detail["auth"] = _auth_track(subject, detail["certificate"])
        detail["default_choice"] = ({"hybrid_first": _picked(choice.get("hybrid_first")), "classical_first": _picked(choice.get("classical_first")),
                                     "hybrid_first_group": (choice.get("hybrid_first") or {}).get("group"),
                                     "classical_first_group": (choice.get("classical_first") or {}).get("group")} if choice else None)
        noticed = []
        old = [v for v in ("TLS 1.0", "TLS 1.1") if (versions.get(v) or {}).get("state") == "accepted"]
        if old:
            noticed.append({"code": "old_tls", "versions": old})
        if pure_group and (hybrid_groups or classical_accepted):
            noticed.append({"code": "pure_too", "group": pure_group})
        detail["also_noticed"] = noticed
        sizes = detail["sizes"]
        sizes["default_hybrid_first"] = _sizes(choice.get("hybrid_first")) if choice else None
    return {"control": control_out, "code": code, "reason_code": reason_code, "detail": detail}


def signature_family(algorithm: object) -> str | None:
    name = str(algorithm or "").upper().replace(" ", "")
    if name.startswith(POST_QUANTUM_SIGNATURES):
        return "pq_only"
    return "classical" if name.startswith(CLASSICAL_SIGNATURES) else None


class ReviewNotAllowed(Exception):
    """The engine that proposed a test never reviews its own result."""


class _CouldntRun(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _ControlErrored(Exception):
    pass


# ------------------------------------------------------------------ small helpers

def _stats(values: list[float]) -> dict:
    ordered = sorted(values)
    return {"median_ms": round(median(ordered), 4), "p99_ms": round(ordered[math.ceil(0.99 * len(ordered)) - 1], 4)}


def paired_comparison(old: list[float], new: list[float], rule: dict) -> dict:
    """The slowdown rule for one operation. Pairs are matched by position (same round, same index)."""
    if len(old) != len(new) or not old:
        raise ValueError("timings are not paired")
    d = [n - o for o, n in zip(old, new)]  # noqa: B905
    centre = median(d)
    mad = median([abs(x - centre) for x in d])
    noise = (rule["noise_factor_milli"] / 1000.0) * mad / math.sqrt(len(d))
    base = median(old)
    floor = rule["floor_percent"] / 100.0 * base
    return {"D_ms": round(centre, 4), "noise_ms": round(noise, 4), "floor_ms": round(floor, 4),
            "change_percent": round(centre / base * 100.0, 2),
            "band_percent": rule["sigma"] * noise / base * 100.0,
            "flagged": bool(centre - rule["sigma"] * noise > floor)}


def _band(comparison: dict) -> float:
    return math.ceil(max(c["band_percent"] for c in comparison.values()) * 10 - 1e-9) / 10


def _public(comparison: dict) -> dict:
    return {op: {k: v for k, v in c.items() if k != "band_percent"} for op, c in comparison.items()}


_CURVES = {"secp256r1": "P-256", "secp384r1": "P-384", "secp521r1": "P-521"}


def certificate_name(cert: dict) -> str:
    """'ECDSA P-256', 'RSA 1024', 'Ed25519', worked out here from the key type, curve and size that were read."""
    family = cert.get("algorithm")
    if family == "EC":
        return f"ECDSA {_CURVES.get(cert.get('curve'), cert.get('curve'))}"
    if family == "RSA":
        return f"RSA {cert.get('key_bits')}"
    return str(family)


def read_s_client(output: object, offered_line: str) -> dict:
    """What an `openssl s_client -brief` transcript literally says."""
    text = output if isinstance(output, str) else ""
    lines = [line.strip() for line in text.splitlines()]
    alert = re.search(r"SSL alert number (\d+)", text)
    return {"negotiated_line": offered_line in lines, "established": "CONNECTION ESTABLISHED" in lines,
            "alert": int(alert.group(1)) if alert else None}


# ------------------------------------------------------------------ the reviewer

class RuleReviewer:
    engine_id = "isogeny.rule-reviewer/1"

    def propose_tests(self, claims: list[dict]) -> dict:
        raise NotImplementedError("The reviewer does not propose tests.")

    def design_test(self, request: dict) -> dict:
        raise NotImplementedError("The reviewer does not design tests.")

    def dig_deeper(self, finding: dict) -> dict:
        raise NotImplementedError("The reviewer does not file research requests.")

    def propose_change(self, request: dict) -> dict | None:
        raise NotImplementedError("The reviewer does not propose changes.")

    def review(self, result: dict) -> dict:
        spec, spec_hash, proposed_by, run = result["spec"], result["spec_hash"], result["proposed_by"], result["run"]
        if proposed_by == self.engine_id:
            raise ReviewNotAllowed("The reviewer never reviews a test it proposed itself.")
        try:
            recomputed = sha256_hex(spec)
        except (TypeError, ValueError):
            recomputed = None
        spec_hash_ok = recomputed == spec_hash and isinstance(run, dict) and run.get("spec_hash") == spec_hash
        review = {"schema": REVIEW_SCHEMA, "reviewer": self.engine_id, "proposed_by": proposed_by, "spec_hash": spec_hash,
                  "spec_hash_ok": bool(spec_hash_ok), "run_sha256": sha256_hex(run),
                  "control": {"outcome": "not_run", "reason": None}, "reference_ok": None,
                  "verdict": {"code": "couldnt_trust", "reason_code": None, "reason": None}, "detail": {}}

        def finish(code: str, reason_code: str | None = None, reason: str | None = None) -> dict:
            if code == "couldnt_run":
                reason_code = reason_code if reason_code in COULDNT_RUN_REASONS else "harness_error"
                reason = COULDNT_RUN_REASONS[reason_code]
            review["verdict"] = {"code": code, "reason_code": reason_code, "reason": reason}
            return review

        if not spec_hash_ok:                                                    # 1
            return finish("couldnt_trust", None, "The locked test no longer matches its fingerprint.")
        raw = run.get("raw")
        if not isinstance(raw, dict):
            return finish("couldnt_trust", None, "The run record holds no raw outcome.")
        problem = raw.get("problem")
        if problem:                                                             # 2
            code = problem.get("code") if isinstance(problem, dict) else None
            return finish("couldnt_run", code)
        judge = getattr(self, "_" + str(spec.get("kind")), None)
        if judge is None:
            return finish("couldnt_trust", None, "This kind of test has no review rule.")
        subject: tuple[str, str | None] | None = None
        try:
            subject = judge(spec, raw, run, review)
        except _CouldntRun as exc:
            subject = ("couldnt_run", exc.code)
        except _ControlErrored:
            review["control"] = {"outcome": "errored", "reason": "the control did not produce a readable outcome"}
        except (KeyError, TypeError, ValueError, IndexError, AttributeError, ZeroDivisionError):
            review["control"] = {"outcome": "errored", "reason": "the raw outcome could not be read"}
        if subject is not None and subject[0] == "couldnt_run" and review["control"]["outcome"] == "not_run":
            return finish("couldnt_run", subject[1])                            # 2 (found while reading the raw outcome)
        if review["control"]["outcome"] != "as_expected":                       # 3
            return finish("couldnt_trust", None, "The control did not behave as it must, so this run can't be trusted.")
        if review["reference_ok"] is False:                                     # 4
            return finish("couldnt_trust", None, "The reference library did not get every case right, so this run can't be trusted.")
        return finish(*subject)                                                 # 5

    # Each rule below fills review["control"], review["reference_ok"] and review["detail"], and returns the
    # subject's own outcome as (code, reason_code).

    # ---------------------------------------------------------------- T1

    def _tls_versions(self, spec, raw, run, review):
        claimed, probed = spec["inputs"]["claimed"], spec["inputs"]["probed"]
        must = spec["control"]["must"]
        outside = [v for v in probed if v not in claimed]

        def judge(versions: dict) -> tuple[str, list[str]]:
            states = {v: (versions.get(v) or {}).get("state") for v in probed}
            accepted_outside = [v for v in outside if states[v] == "accepted"]
            if accepted_outside:
                return "failed", accepted_outside
            if all(states[v] == "refused" for v in outside) and any(states[v] == "accepted" for v in claimed):
                return "passed", []
            return "unreadable", []

        control = raw.get("control")
        control_accepted: list[str] = []
        if not isinstance(control, dict) or not isinstance(control.get("versions"), dict):
            review["control"] = {"outcome": "errored", "reason": "the control server could not be started or read"}
        else:
            verdict, control_accepted = judge(control["versions"])
            if verdict == must["verdict"] and must["accepted"] in control_accepted:
                review["control"] = {"outcome": "as_expected", "reason": "accepted_older_version"}
            elif verdict == "unreadable":
                review["control"] = {"outcome": "errored", "reason": "the control server's answers could not be read"}
            else:
                review["control"] = {"outcome": "not_as_expected", "reason": "did_not_accept_the_older_version"}
        verdict, accepted_outside = judge(raw["subject"]["versions"])
        review["detail"] = {"accepted_outside_claim": accepted_outside, "claimed": list(claimed), "control_accepted": control_accepted}
        return ("couldnt_run", "unreadable_answer") if verdict == "unreadable" else (verdict, None)

    # ---------------------------------------------------------------- T2

    def _certificate(self, spec, raw, run, review):
        claimed, guidance = spec["inputs"]["claimed_algorithm"], spec["inputs"]["guidance"]
        must = spec["control"]["must"]

        def judge(cert: dict) -> tuple[str, list[str]]:
            found = certificate_name(cert)
            reasons = []
            if found != claimed and not (" " not in claimed and found.split(" ")[0] == claimed):
                reasons.append("algorithm_mismatch")
            minimum = guidance["minimum_bits"].get(cert.get("algorithm"))
            if minimum is not None and int(cert["key_bits"]) < int(minimum):
                reasons.append("below_minimum")
            return found, reasons

        control = raw.get("control")
        control_found, control_reasons = None, []
        if not isinstance(control, dict) or not isinstance(control.get("certificate"), dict):
            review["control"] = {"outcome": "errored", "reason": "the control certificate could not be served or read"}
        else:
            control_found, control_reasons = judge(control["certificate"])
            verdict = "failed" if control_reasons else "passed"
            if verdict == must["verdict"] and must["reason"] in control_reasons:
                review["control"] = {"outcome": "as_expected", "reason": "below_minimum"}
            else:
                review["control"] = {"outcome": "not_as_expected", "reason": "not_failed_for_being_below_the_minimum"}
        cert = (raw.get("subject") or {}).get("certificate")
        if not isinstance(cert, dict):
            review["detail"] = {"control_found": control_found, "control_reasons": control_reasons}
            raise _CouldntRun("unreadable_answer")
        found, reasons = judge(cert)
        notes = [{"text": n["text"], "source": n["source"]} for n in guidance.get("notes", [])
                 if found in n["applies_to"] or found.split(" ")[0] in n["applies_to"]]
        review["detail"] = {"found": found, "key_bits": cert["key_bits"], "reasons": reasons, "notes": notes,
                            "control_found": control_found, "control_reasons": control_reasons}
        return ("failed" if reasons else "passed"), None

    # ---------------------------------------------------------------- T3 and T4

    @staticmethod
    def _score(cases, answers: dict, no_answer: dict | None = None) -> dict:
        wrong, missing, right = [], [], 0
        for c in cases:
            if c.expected == "acceptable":
                continue
            got = answers.get(c.id) if isinstance(answers, dict) else None
            if got not in ("accept", "reject"):
                missing.append(c.id)
            elif got == ("accept" if c.expected == "valid" else "reject"):
                right += 1
            else:
                wrong.append({"id": c.id, "comment": c.comment, "flags": list(c.flags), "expected": c.expected, "got": got})
        return {"total": right + len(wrong) + len(missing), "right": right, "wrong": wrong, "missing": missing}

    def _signing(self, spec, raw, review, subject_set: str, extra_reference: str | None):
        try:
            cases = vectors.load_bad_signatures().cases if subject_set == "bad_signatures" else vectors.load_wycheproof(subject_set).cases
            extra = vectors.load_wycheproof(extra_reference).cases if extra_reference else ()
        except vectors.VectorFileChanged:
            raise _CouldntRun("vector_file_changed") from None
        pins = ({f["file"]: f["sha256"] for f in spec["inputs"]["files"]} if "files" in spec["inputs"]
                else {spec["inputs"]["file"]: spec["inputs"]["sha256"]})
        if raw.get("files") != pins:
            raise _CouldntRun("vector_file_changed")
        invalid = [c for c in cases if c.expected == "invalid"]
        control_answers = (raw.get("control") or {}).get("answers")
        control = self._score(cases, control_answers or {})
        control_wrong_invalid = sum(1 for w in control["wrong"] if w["expected"] == "invalid")
        if not isinstance(control_answers, dict) or control["missing"]:
            review["control"] = {"outcome": "errored", "reason": "the broken signer did not answer every case"}
        elif control_wrong_invalid == len(invalid) and invalid:
            review["control"] = {"outcome": "as_expected", "reason": "accepted_every_invalid_case"}
        else:
            review["control"] = {"outcome": "not_as_expected", "reason": "rejected_some_invalid_cases"}
        reference = raw.get("reference") or {}
        ref_main = self._score(cases, (reference.get(subject_set) or {}).get("answers") or {})
        ref_detail = {subject_set: {"total": ref_main["total"], "right": ref_main["right"]}}
        ok = not ref_main["wrong"] and not ref_main["missing"]
        if extra_reference:
            ref_extra = self._score(extra, (reference.get(extra_reference) or {}).get("answers") or {})
            ok = ok and not ref_extra["wrong"] and not ref_extra["missing"]
            ref_detail[extra_reference] = {"valid": sum(1 for c in extra if c.expected == "valid"),
                                           "invalid": sum(1 for c in extra if c.expected == "invalid"),
                                           "acceptable": sum(1 for c in extra if c.expected == "acceptable"),
                                           "wrong": len(ref_extra["wrong"]) + len(ref_extra["missing"])}
        review["reference_ok"] = bool(ok)
        subject = raw.get("subject") or {}
        scored = self._score(cases, subject.get("answers") or {})
        review["detail"] = {"total": scored["total"], "right": scored["right"], "wrong": scored["wrong"],
                            "no_answer": len(scored["missing"]), "control_wrong": control_wrong_invalid,
                            "invalid_total": len(invalid), "valid_total": sum(1 for c in cases if c.expected == "valid"),
                            "reference": ref_detail}
        crashes = subject.get("general_errors")
        if isinstance(crashes, dict) and crashes:
            # Phase 4c (Kevin's decision 1): an error raised by the library is "not accepted", so these cases are scored
            # above like any other answer. They are listed here as a note, never as a result. (Only written when there
            # are any, so the review of an older run stays exactly what it was.)
            by_id = {c.id: c for c in cases}
            review["detail"]["general_errors"] = [
                {"id": str(case_id), "error": str(error)[:60], "comment": by_id[case_id].comment, "expected": by_id[case_id].expected}
                for case_id, error in crashes.items() if case_id in by_id]
        if scored["missing"] or subject.get("no_answer"):
            return "couldnt_run", "component_no_answer"
        return ("failed" if scored["wrong"] else "passed"), None

    # ---------------------------------------------------------------- phase 4c: the two post-quantum exams

    @staticmethod
    def _pq_right(case, got: dict) -> tuple[bool, str]:
        """(is this the right answer?, what the library did, in a few words)"""
        refused, valid = got.get("refused") is True, got.get("valid")
        if case.command == "verify":
            did = "accepted" if valid is True else "rejected"
            return (valid is True) == (case.expect == "accept"), did
        if refused:
            return case.expect == "refuse", "refused"
        if case.expect == "answer":
            same = got.get("sha256") == case.answer_sha256
            return same, "the published answer" if same else "a different answer"
        return case.expect == "accept", "not refused"

    def _pq_exam(self, spec, raw, run, review):
        exam = spec["kind"]
        try:
            cases = pq_vectors.load(exam)
        except vectors.VectorFileChanged:
            raise _CouldntRun("vector_file_changed") from None
        if raw.get("files") != {f["file"]: f["sha256"] for f in spec["inputs"]["files"]}:
            raise _CouldntRun("vector_file_changed")
        # The controls first: each part's broken copy must have failed for its stated reason.
        controls, outcomes = {}, []
        for part, must in spec["control"]["must"].items():
            ran = (raw.get("controls") or {}).get(part)
            mine = [c for c in cases if c.part == part]
            if not isinstance(ran, dict) or not isinstance(ran.get("answers"), dict) or ran.get("problem") or ran.get("no_answer"):
                outcomes.append("errored")
                controls[part] = {"control": must["control"], "caught": None, "of": None}
                continue
            answers = ran["answers"]
            if must["control"] == "skip_key_check":
                judged = [c for c in mine if must["accepts_flag"] in c.flags]
                ok_count = len(judged) == must["count"]
            else:
                judged = [c for c in mine if (c.expect == "answer" if must["control"] == "wrong_answer" else c.expect == "reject")]
                ok_count = bool(judged)
            missing = [c.id for c in judged if not isinstance(answers.get(c.id), dict)]
            caught = sum(1 for c in judged if isinstance(answers.get(c.id), dict) and not self._pq_right(c, answers[c.id])[0])
            controls[part] = {"control": must["control"], "caught": caught, "of": len(judged)}
            outcomes.append("errored" if missing else "as_expected" if ok_count and caught == len(judged) else "not_as_expected")
        if "errored" in outcomes or not outcomes:
            review["control"] = {"outcome": "errored", "reason": "a broken copy did not answer every case"}
        elif all(o == "as_expected" for o in outcomes):
            review["control"] = {"outcome": "as_expected", "reason": "every_broken_copy_failed_as_it_must"}
        else:
            review["control"] = {"outcome": "not_as_expected", "reason": "a_broken_copy_was_not_caught"}
        # The library's own answers, part by part.
        answers = (raw.get("subject") or {}).get("answers") or {}
        wrong, missing, parts = [], [], []
        for part in spec["inputs"]["parts"]:
            mine = [c for c in cases if c.part == part["id"]]
            right = 0
            for c in mine:
                got = answers.get(c.id)
                if not isinstance(got, dict):
                    missing.append(c.id)
                    continue
                ok, did = self._pq_right(c, got)
                if ok:
                    right += 1
                else:
                    wrong.append({"id": c.id, "part": c.part, "source": c.source, "comment": c.comment, "flags": list(c.flags),
                                  "expected": c.expect, "got": did})
            parts.append({"id": part["id"], "title": part["title"], "cases": len(mine), "right": right,
                          "nist": sum(1 for c in mine if c.source == pq_vectors.NIST),
                          "wycheproof": sum(1 for c in mine if c.source == pq_vectors.WYCHEPROOF),
                          "control": controls.get(part["id"])})
        review["detail"] = {"total": len(cases), "right": sum(p["right"] for p in parts), "wrong": wrong, "no_answer": len(missing),
                            "parts": parts, "left_out": spec["inputs"].get("left_out", 0)}
        if missing or (raw.get("subject") or {}).get("no_answer"):
            return "couldnt_run", "component_no_answer"
        return ("failed" if wrong else "passed"), None

    def _mlkem_vectors(self, spec, raw, run, review):
        return self._pq_exam(spec, raw, run, review)

    def _mldsa_vectors(self, spec, raw, run, review):
        return self._pq_exam(spec, raw, run, review)

    def _official_vectors(self, spec, raw, run, review):
        return self._signing(spec, raw, review, "ecdsa_p256", "ed25519")

    def _bad_signatures(self, spec, raw, run, review):
        return self._signing(spec, raw, review, "bad_signatures", None)

    # ---------------------------------------------------------------- T5

    @staticmethod
    def _series(benches: list, role: str, rounds: int, repeats: int) -> dict | None:
        """All timings of one role in round order, or None if any round is missing or not usable."""
        mine = sorted((b for b in benches if isinstance(b, dict) and b.get("role") == role), key=lambda b: b.get("round", -1))
        if [b.get("round") for b in mine] != list(range(rounds)):
            return None
        sign, verify = [], []
        for b in mine:
            s, v = b.get("sign_ms"), b.get("verify_ms")
            if b.get("all_verified") is not True or not isinstance(s, list) or not isinstance(v, list) \
                    or len(s) != repeats or len(v) != repeats \
                    or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 for x in s + v):
                return None
            sign += s
            verify += v
        return {"key": mine[0].get("subject"), "sign": sign, "verify": verify,
                "signature_bytes": mine[0].get("signature_bytes"), "public_key_bytes": mine[0].get("public_key_bytes")}

    @staticmethod
    def _summary(series: dict) -> dict:
        return {"key": series["key"], "sign": _stats(series["sign"]), "verify": _stats(series["verify"]),
                "signature_bytes": series["signature_bytes"], "public_key_bytes": series["public_key_bytes"]}

    def _speed_size(self, spec, raw, run, review):
        inputs, rule = spec["inputs"], spec["rule"]
        rounds, repeats = inputs["rounds"], inputs["repeats"]
        benches = raw["benches"]
        # A retest or a proof times the old and the new code side by side, but only for the plan's own program: another
        # program in the same file (phase 3a-fixes) is run again as it is, with no baseline, and measured like a first run.
        # (Every stored run record names its baseline_version; it is None exactly for those other programs.)
        retest = run.get("phase") in ("retest", "proof") and not ("baseline_version" in run and run["baseline_version"] is None)
        base_role = "new" if retest else "subject"
        base = self._series(benches, base_role, rounds, repeats)
        old = self._series(benches, "old", rounds, repeats) if retest else None
        control = self._series(benches, "control", rounds, repeats)
        detail: dict = {"pairs": rounds * repeats, "comparison": None, "noise_band_percent": None,
                        "control": {"delay_ms": inputs["control_delay_ms"]}}
        control_cmp = None
        if control is None or base is None:
            review["control"] = {"outcome": "errored" if base is not None else "not_run",
                                 "reason": "the slowed signer's timings could not be read" if base is not None else None}
        else:
            control_cmp = {op: paired_comparison(base[op], control[op], rule) for op in rule["ops"]}
            flagged = all(control_cmp[op]["flagged"] for op in spec["control"]["must"]["flagged"])
            review["control"] = ({"outcome": "as_expected", "reason": "flagged_on_sign_and_verify"} if flagged
                                 else {"outcome": "not_as_expected", "reason": "the_slowed_signer_was_not_flagged"})
            detail["control"].update(_public(control_cmp))
        reference = raw.get("reference")
        if isinstance(reference, dict) and reference.get("sign_ms") and reference.get("verify_ms"):
            detail["reference"] = {"library": reference.get("library"), "sign": _stats(reference["sign_ms"]),
                                   "verify": _stats(reference["verify_ms"]),
                                   "signature_bytes": reference.get("signature_bytes"),
                                   "public_key_bytes": reference.get("public_key_bytes")}
        else:
            detail["reference"] = None
        review["detail"] = detail
        if base is None or (retest and old is None):
            return "couldnt_run", "component_no_answer"
        detail[base_role] = self._summary(base)
        if not retest:
            if control_cmp:
                detail["noise_band_percent"] = _band(control_cmp)
            return "measured", None
        detail["old"] = self._summary(old)
        comparison = {op: paired_comparison(old[op], base[op], rule) for op in rule["ops"]}
        detail["comparison"] = _public(comparison)
        detail["noise_band_percent"] = _band(comparison)
        return ("slowdown" if any(c["flagged"] for c in comparison.values()) else "no_slowdown"), None

    # ---------------------------------------------------------------- phase 4a: the post-quantum status

    def _pq_status(self, spec, raw, run, review):
        found = pq_status_of(raw, (spec["inputs"].get("guidance") or {}).get("minimum_bits"),
                             tracks=spec["rule"].get("type") == "pq_status_tracks")
        review["control"], review["detail"] = found["control"], found["detail"]
        return found["code"], found["reason_code"]

    def _signing_status(self, spec, raw, run, review):
        subject = raw["subject"]
        check = subject["check"]
        if check.get("result") != "True":
            review["detail"] = {"status": "couldnt_run", "component": subject.get("component"), "found": check.get("found"),
                                "why": check.get("reason")}
            raise _CouldntRun("claim_not_confirmed")
        # The control of this measurement is the independent library: it confirmed the key and the signature.
        review["control"] = {"outcome": "as_expected", "reason": "independent_library_confirmed_the_signature"}
        algorithm = spec["inputs"]["claimed_algorithm"]
        cost = None
        measured = raw.get("cost")
        if isinstance(measured, dict) and not measured.get("problem"):
            side = {"control": {"outcome": "not_run", "reason": None}, "detail": {}}
            try:
                self._mldsa_compare({"inputs": spec["inputs"]["mldsa"]}, measured, run, side)
                if side["control"]["outcome"] == "as_expected":
                    cost = side["detail"]
            except (KeyError, TypeError, ValueError, IndexError):
                cost = None
        family = signature_family(algorithm)
        review["detail"] = {"status": family or "couldnt_run", "algorithm": algorithm, "component": subject.get("component"),
                            "found": check.get("found"), "cost": cost}
        capability = raw.get("capability")
        if isinstance(capability, dict):
            # Phase 4c, a real library: it can make post-quantum signatures only if it made one that the independent
            # library confirmed. (Written only when it was asked, so the review of an older run stays what it was.)
            said = (capability.get("check") or {}).get("result")
            review["detail"]["can_make_pq"] = True if said == "True" else False if said == "False" else None
            review["detail"]["pq_algorithm"] = capability.get("algorithm")
        if family is None:
            return "couldnt_run", "unknown_algorithm"
        return family, None

    # ---------------------------------------------------------------- catalog: post-quantum readiness

    def _pq_readiness(self, spec, raw, run, review):
        if spec["rule"].get("type") == "pq_status_offered":
            # Since phase 4a: the same measurement and the same rule as the Migration step, so the two never disagree.
            found = pq_status_of(raw)
            review["control"] = found["control"]
            groups = found["detail"]["hybrid_groups"] or ([found["detail"]["pure_group"]] if found["detail"]["pure_group"] else [])
            review["detail"] = {**found["detail"], "group": groups[0] if groups else None, "asked_for": spec["inputs"]["group"]}
            if found["code"] in ("hybrid", "pq_only"):
                return "offered", None
            if found["code"] == "classical":
                return "not_offered", None
            return found["code"], found["reason_code"]
        line = spec["rule"]["offered_line"]
        control = raw.get("control")
        control_read = None
        if not isinstance(control, dict) or not isinstance(control.get("pq_only"), dict):
            review["control"] = {"outcome": "errored", "reason": "the control server could not be started or reached"}
        else:
            control_read = read_s_client(control["pq_only"].get("output"), line)
            review["control"] = ({"outcome": "as_expected", "reason": "detected_as_offered"} if control_read["negotiated_line"]
                                 else {"outcome": "not_as_expected", "reason": "the_control_server_was_not_detected_as_offering_it"})
        subject = raw["subject"]
        pq = read_s_client(subject["pq_only"].get("output"), line)
        normal = read_s_client((subject.get("normal") or {}).get("output"), line)
        review["detail"] = {"group": spec["inputs"]["group"], "checker": raw.get("checker"), "pq_only": pq,
                            "normal_established": normal["established"],
                            "control_detected": bool(control_read and control_read["negotiated_line"])}
        if pq["negotiated_line"]:
            return "offered", None
        if pq["alert"] == 40 and normal["established"]:
            return "not_offered", None
        if not normal["established"] and normal["alert"] is None and pq["alert"] is None:
            return "couldnt_run", "checker_cannot_reach"
        return "couldnt_run", "unreadable_answer"

    # ---------------------------------------------------------------- catalog: ML-DSA-65

    def _mldsa_compare(self, spec, raw, run, review):
        control = raw.get("control")
        if not isinstance(control, dict) or "altered_rejected" not in control or "genuine_accepted" not in control:
            review["control"] = {"outcome": "errored", "reason": "the altered-signature check did not run"}
        elif control["genuine_accepted"] is True and control["altered_rejected"] is True:
            review["control"] = {"outcome": "as_expected", "reason": "altered_signature_rejected"}
        else:
            review["control"] = {"outcome": "not_as_expected", "reason": "the_altered_signature_was_not_rejected"}
        m = raw["mldsa65"]
        repeats = spec["inputs"]["repeats"]
        for name in ("keygen_ms", "sign_ms", "verify_ms"):
            if len(m[name]) != repeats or not all(isinstance(x, (int, float)) and x > 0 for x in m[name]):
                raise ValueError("ML-DSA timings are not complete")
        detail = {"repeats": repeats, "label": spec["inputs"]["label"],
                  "mldsa65": {"library": m.get("library"), "keygen": _stats(m["keygen_ms"]), "sign": _stats(m["sign_ms"]),
                              "verify": _stats(m["verify_ms"]), "public_key_bytes": m["public_key_bytes"],
                              "signature_bytes": m["signature_bytes"]},
                  "component": None}
        component = raw.get("component")
        if isinstance(component, dict) and isinstance(component.get("benches"), list):
            series = self._series(component["benches"], "subject", 1, spec["inputs"]["component_repeats"])
            if series is not None:
                detail["component"] = self._summary(series)
        review["detail"] = detail
        return "measured", None

    # ---------------------------------------------------------------- the offer rule (a proposed code change)

    def review_proof(self, record: dict) -> dict:
        """May this change be offered? Decided from the proof record alone. Offered only if ALL of these hold:
          1. the changed code is byte for byte one of our registered demo components, and that is what ran
             (the caller made the comparison and passes the fact; no file is read here);
          2. every test in the proof has a run;
          3. every pass-or-fail test that runs the changed code passed on it, and there is at least one such
             test. A report-only test has no pass or fail: it only has to run, and alone it is not enough;
          4. the control behaved in every proof run that reached a result;
          5. every server test (and every test of another program in the file) came out the same as before: the same result and the same reason. A test that
             could not run before, for the same reason, counts as unchanged; its control was not run;
          6. every failed test the change was made for (the record's `answers`) is in this proof, runs the
             changed code and passed on it, and there is at least one such test. So a proof of a plan from
             which those tests were taken out never makes the change a fix;
          7. the speed comparison was made: the proof holds a Speed and size test that ran on the changed code
             and came out "No slowdown beyond measured noise"."""
        if record.get("proposed_by") == self.engine_id:
            raise ReviewNotAllowed("The reviewer never reviews a change it proposed itself.")
        matches = (record.get("built") or {}).get("matches")
        code_is_ours = (isinstance(matches, dict) and bool(matches.get("name")) and bool(matches.get("version"))
                        and matches.get("version") == record.get("version"))
        tests = []
        for test in record.get("tests") or []:
            first, run = test.get("first"), test.get("proof")
            # Only the plan's own program runs the changed code. Servers, and other programs from the same file
            # (phase 3a-fixes), don't: like the server tests they only have to come out the same as before.
            group = "server" if test.get("target") in ("server", "other_program") else "code"
            report_only = group == "code" and PROOF_PASS_CODES.get(test.get("kind")) == REPORT_ONLY_CODE
            if run is None:
                held, control_ok, reason = False, True, "no_run"
            else:
                # A run that could not run has no control outcome to judge; any other run must have a behaving control.
                control_ok = run.get("code") == "couldnt_run" or run.get("control_outcome") == "as_expected"
                if group == "code":
                    held = run.get("code") == PROOF_PASS_CODES.get(test.get("kind"))
                    reason = (run["code"] if run["code"] in ("passed", "no_slowdown") else "ran") if held else "did_not_pass"
                elif first is None:
                    held, reason = False, "nothing_to_compare"
                else:
                    held = (run.get("code"), run.get("reason_code")) == (first.get("code"), first.get("reason_code"))
                    reason = "same_as_before" if held else "changed"
                if not control_ok:
                    reason = "control_misbehaved"
            tests.append({"item_id": test.get("item_id"), "kind": test.get("kind"), "group": group, "report_only": report_only,
                          "held": held, "control_ok": control_ok, "ok": held and control_ok, "reason": reason})
        code = [t for t in tests if t["group"] == "code" and not t["report_only"]]  # the tests with a pass or fail
        reports = [t for t in tests if t["report_only"]]
        server = [t for t in tests if t["group"] == "server"]
        # 6: the failed tests the change answers, each looked up in this proof by its place in the plan
        by_item = {t["item_id"]: t for t in tests}
        answers = []
        for answer in record.get("answers") or []:
            answer = answer if isinstance(answer, dict) else {}
            test = by_item.get(answer.get("item_id"))
            if test is None or test["group"] != "code" or test["kind"] != answer.get("kind"):
                ok, reason = False, "not_in_proof"
            else:
                ok = test["ok"] and not test["report_only"]
                reason = "passed" if ok else "did_not_pass"
            answers.append({"item_id": answer.get("item_id"), "kind": answer.get("kind"), "ok": ok, "reason": reason})
        # 7: the speed comparison
        timed = [t for t in code if t["kind"] == SPEED_KIND]
        if not timed:
            speed = {"ok": False, "reason": "not_in_proof"}
        elif all(t["ok"] for t in timed):
            speed = {"ok": True, "reason": "no_slowdown"}
        else:
            speed = {"ok": False, "reason": "did_not_pass"}
        checks = {"code_is_ours": bool(code_is_ours),
                  "changed_code_passed": bool(code) and all(t["held"] for t in code),
                  "report_only_ran": all(t["held"] for t in reports),
                  "controls_behaved": all(t["control_ok"] for t in tests),
                  "server_unchanged": all(t["held"] for t in server),
                  "answered_tests_passed": bool(answers) and all(a["ok"] for a in answers),
                  "speed_compared": speed["ok"]}
        counts = {"tests": len(tests), "code": len(code), "code_ok": sum(t["ok"] for t in code),
                  "report_only": len(reports), "report_only_ok": sum(t["ok"] for t in reports),
                  "server": len(server), "server_ok": sum(t["ok"] for t in server)}
        return {"reviewer": self.engine_id, "schema": PROOF_REVIEW_SCHEMA, "record_sha256": sha256_hex(record),
                "offered": all(checks.values()), "checks": checks, "counts": counts,
                "tests": [{k: t[k] for k in ("item_id", "kind", "group", "report_only", "ok", "reason")} for t in tests],
                "answers": answers, "speed": speed}


# ---------------------------------------------------------------- phase 4b: a change tried on a test copy, then applied
# Pure functions over reviewed measurements (each already through the read gate). Nothing here is stored: the
# outcome of a try, of an Apply and of a Roll back is worked out again, from the records, every time it is shown.

KEX_STATUSES = ("classical", "hybrid", "pq_only")


def _facts_of(measured: dict | None) -> dict | None:
    """The facts a promise is checked against, from one reviewed measurement; None when it gave no answer."""
    if not isinstance(measured, dict):
        return None
    code, detail = measured.get("code"), measured.get("detail") or {}
    if code in KEX_STATUSES:
        auth = (detail.get("auth") or {}).get("status")
        return {"kex": code, "auth": auth if auth in ("classical", "post_quantum") else None,
                "classical_client": detail.get("classical_client"), "tls": None}
    if code in ("passed", "failed"):          # a server protocol check (the Acme Pay server's TLS fix, SPEC 7c)
        return {"kex": None, "auth": None, "classical_client": None, "tls": code}
    return None


def meets_promise(promise: dict, measured: dict | None) -> tuple[bool | None, list[dict]]:
    """(does this measurement show what the change promises?, one check per promised fact). None = no answer."""
    facts = _facts_of(measured)
    if facts is None or not promise:
        return None, []
    checks = []
    for key, want in promise.items():
        got = facts.get(key)
        if want is None:            # "authentication stays as it was" with no earlier answer to compare: not checked
            continue
        if got is None:
            return None, checks
        checks.append({"fact": key, "want": want, "got": got, "ok": got == want})
    return all(c["ok"] for c in checks), checks


def change_try_outcome(promise: dict, copies: list[tuple[str, dict | None, str | None]]) -> dict:
    """The verdict of one "Try on a test copy". copies: (which copy, its reviewed measurement, or None with the reason
    it was not tried, for example "needs isolated mode"). Passed only when every copy that was measured shows what
    the change promises, and at least one was. A copy whose measurement could not run or can't be trusted gives no
    answer, and then the try can't pass. A copy that was not tried is listed, and decides nothing."""
    out, measured = [], 0
    for label, m, skipped in copies:
        if m is None:
            out.append({"copy": label, "ok": None, "checks": [], "skipped": skipped})
            continue
        measured += 1
        ok, checks = meets_promise(promise, m)
        out.append({"copy": label, "ok": ok, "checks": checks, "skipped": None})
    if not measured:
        return {"code": "not_run", "checks": out}
    tried = [c for c in out if c["skipped"] is None]
    if any(c["ok"] is None for c in tried):
        return {"code": "couldnt_run", "checks": out}
    return {"code": "passed" if all(c["ok"] for c in tried) else "failed", "checks": out}


def apply_outcome(promise: dict, tried: dict | None, after: dict | None) -> dict:
    """After an Apply: does the first measurement of the system itself match the try? Differences are listed by fact."""
    ok, checks = meets_promise(promise, after)
    if ok is None:
        return {"code": "no_answer", "differences": []}
    tried_facts, after_facts = _facts_of(tried) or {}, _facts_of(after) or {}
    differences = [{"fact": key, "tried": tried_facts.get(key), "after": after_facts.get(key)}
                   for key in ("kex", "auth", "classical_client", "tls")
                   if tried_facts.get(key) is not None and tried_facts.get(key) != after_facts.get(key)]
    return {"code": "matches" if ok and not differences else "differs", "differences": differences, "checks": checks}


def rollback_outcome(before: dict | None, after: dict | None) -> dict:
    """After a Roll back: does the system measure as it did before the change?"""
    b, a = _facts_of(before), _facts_of(after)
    if a is None or b is None:
        return {"code": "no_answer", "differences": []}
    differences = [{"fact": key, "before": b.get(key), "after": a.get(key)} for key in ("kex", "auth", "classical_client", "tls")
                   if b.get(key) is not None and b.get(key) != a.get(key)]
    return {"code": "as_before" if not differences else "differs", "differences": differences}

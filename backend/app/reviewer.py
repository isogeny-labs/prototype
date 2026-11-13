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

from . import vectors
from .canonical import sha256_hex

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
}


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
    d = [n - o for o, n in zip(old, new)]
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
        if scored["missing"] or subject.get("no_answer"):
            return "couldnt_run", "component_no_answer"
        return ("failed" if scored["wrong"] else "passed"), None

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
        retest = run.get("phase") in ("retest", "proof")  # a proof times the old and the changed code side by side too
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

    # ---------------------------------------------------------------- catalog: post-quantum readiness

    def _pq_readiness(self, spec, raw, run, review):
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
          5. every server test came out the same as before: the same result and the same reason. A test that
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
            group = "server" if test.get("target") == "server" else "code"
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

"""The comparison of the app's answers with demo/expected-real-libraries.json (accuracy_real.compare_real). Pure: made-up
answers, no app and no containers. The real run is `python -m app.accuracy --only real`."""

import copy
import json

from app import accuracy_real as ar

KEY = json.loads(ar.EXPECTED_REAL_JSON.read_text(encoding="utf-8"))


def result(label, wrong=(), component=None, **more):
    code = {"Passed": "passed", "Failed": "failed"}.get(label, "measured")
    detail = {"wrong": [dict(w) for w in wrong], **more.pop("detail", {})}
    return {
        "label": label,
        "code": code,
        "component": component,
        "control": "as_expected",
        "plain": more.pop("plain", ""),
        "shows": more.pop("shows", []),
        "also_noticed": more.pop("also_noticed", []),
        "advisories": [],
        "real": True,
        "listed": " ".join(str(w["id"]) for w in wrong),
        "reason_code": None,
        "detail": detail,
    }


def w(case_id, got="accept", flags=()):
    return {
        "id": str(case_id),
        "got": got,
        "flags": list(flags),
        "expected": "invalid" if got == "accept" else "valid",
        "comment": "",
    }


def exam(total_parts):
    parts = [
        {
            "id": i,
            "title": t,
            "cases": n,
            "right": n,
            "nist": 1,
            "wycheproof": n - 1,
            "control": {"control": "c", "caught": 3, "of": 3},
        }
        for i, t, n in total_parts
    ]
    return result(
        "Passed",
        detail={"parts": parts, "right": sum(p["cases"] for p in parts), "total": sum(p["cases"] for p in parts)},
        shows=["45 NIST cases are left out for every library: they test the pre-hash variant (HashML-DSA)."],
    )


def good_answers():
    java_wrong = [w(i) for i in (6, 168, 171, 192, 195, 216, 219, 351, 363, 364, 477)] + [
        w(350, "reject"),
        w(479, "reject"),
    ]
    first = {
        ("openjdk 17.0.2", "official_vectors"): result("Failed", java_wrong),
        ("openjdk 17.0.2", "bad_signatures"): result("Failed", [w("r0-s0")]),
        ("openjdk 17.0.2", "speed_size"): result("Measured"),
        ("python-ecdsa 0.13.2", "official_vectors"): result(
            "Failed",
            [w(i, flags=["InvalidEncoding"]) for i in range(24)],
            plain="it accepted 24 signatures with a malformed encoding",
        ),
        ("python-ecdsa 0.13.2", "bad_signatures"): result("Failed", [w("extra-zero-padding")]),
        ("python-ecdsa 0.13.2", "speed_size"): result("Measured"),
        ("elliptic 6.5.6", "official_vectors"): result("Failed", [w(6, flags=["MissingZero"])]),
        ("elliptic 6.5.6", "bad_signatures"): result(
            "Passed", shows=["It does not catch CVE-2024-42460, which is published for this version."]
        ),
        ("elliptic 6.5.6", "speed_size"): result("Measured"),
        ("openssl 3.5.9 (ECDSA P-256)", "official_vectors"): result("Passed"),
        ("openssl 3.5.9 (ECDSA P-256)", "bad_signatures"): result("Passed"),
        ("openssl 3.5.9 (ML-DSA-65)", "mldsa_vectors"): exam(
            [("keygen", "Key generation", 25), ("sign", "Sign", 195), ("verify", "Verify", 255)]
        ),
        ("openssl 3.5.9 (ML-KEM-768)", "mlkem_vectors"): exam(
            [("keygen", "Key generation", 125), ("encaps", "Encapsulate", 300), ("decaps", "Decapsulate", 230)]
        ),
    }
    for (label, _kind), made in first.items():  # a first run ran on the version the file names
        made["component"] = label.split(" (")[0]
    after = {
        "openjdk": {
            ("openjdk 17.0.2", "official_vectors"): result(
                "Failed", [w(6), w(350, "reject"), w(479, "reject")], component="openjdk 17.0.3"
            ),
            ("openjdk 17.0.2", "bad_signatures"): result("Passed", component="openjdk 17.0.3"),
            ("openjdk 17.0.2", "speed_size"): result("No slowdown beyond measured noise"),
        },
        "python-ecdsa": {
            ("python-ecdsa 0.13.2", "official_vectors"): result(
                "Passed",
                component="python-ecdsa 0.13.3",
                detail={"general_errors": [{"id": "1", "error": "TypeError"}]},
                also_noticed=[
                    "On 5 of these cases python-ecdsa 0.13.3 stopped with a general program error (TypeError)"
                ],
            ),
            ("python-ecdsa 0.13.2", "bad_signatures"): result("Passed", component="python-ecdsa 0.13.3"),
            ("python-ecdsa 0.13.2", "speed_size"): result("Slowdown found"),
        },
        "elliptic": {
            ("elliptic 6.5.6", "official_vectors"): result("Passed", component="elliptic 6.5.7"),
            ("elliptic 6.5.6", "bad_signatures"): result("Passed", component="elliptic 6.5.7"),
            ("elliptic 6.5.6", "speed_size"): result("No slowdown beyond measured noise"),
        },
    }
    fix = lambda name: {  # noqa: E731
        "title": f"Update {name} to the fixed version (x)",
        "kind": "text",
        "status": "Text only",
        "pull_request": None,
        "buttons": [],
        "advisory_links": ["https://example.org/a"],
        "text": "",
    }
    blocked = {
        "status": "Classical",
        "today": "",
        "next": "sign with both, once its signing library can (the blocker).",
        "blockers": ["It signs with ECDSA P-256 only: it can't make post-quantum signatures measured."],
        "band": "Phase 2",
        "recommended": "x",
    }
    couldnt = {
        "label": "Couldn't run (needs isolated mode)",
        "code": "couldnt_run",
        "reason_code": "needs_isolated_mode",
    }
    return {
        "mode": "isolated",
        "notes": [],
        "stopped": None,
        "verify": {(e["component"], e["claim"]): {"result": "True", "summary": ""} for e in KEY["verify"]},
        "first": first,
        "after": after,
        "fixes_first": [fix("openjdk"), fix("python-ecdsa"), fix("elliptic")],
        "fixes_after": {
            "openjdk": [
                {
                    **fix("x"),
                    "title": "openjdk 17.0.3: no fixed version is known",
                    "text": "No fixed version of openjdk is known to this app. The cases are listed above.",
                }
            ]
        },
        "migration": {
            "openssl 3.5.9 (ECDSA P-256)": {
                "status": "Classical",
                "today": "",
                "blockers": [],
                "band": "Phase 2",
                "recommended": "x",
                "next": "sign with both ECDSA P-256 and ML-DSA. Not blocked: this library can already make ML-DSA-65 signatures measured.",
            },
            "openssl 3.5.9 (ML-DSA-65)": {
                "status": "Post-quantum only",
                "today": "",
                "next": "keep it there",
                "blockers": [],
                "band": "At the target",
                "recommended": "x",
            },
            "openjdk 17.0.2": blocked,
            "python-ecdsa 0.13.2": blocked,
            "elliptic 6.5.6": blocked,
        },
        "demo_mode": {
            "mode": "demo",
            "verify": [{"result": "Couldn't check", "summary": "runs only in isolated mode (Docker)"}] * 6,
            "tests": [couldnt] * 15,
            "migration": {"openjdk 17.0.2": {"status": "Couldn't check", "today": "runs only in isolated mode"}},
        },
    }


def test_every_answer_of_the_key_is_graded_and_the_good_answers_all_match():
    report = ar.compare_real(KEY, good_answers())
    wanted = [
        e["id"]
        for part in ("verify", "ecdsa_tests", "post_quantum_tests", "before_and_after", "fixes", "migration")
        for e in KEY[part]
    ] + ["RD1"]
    assert [line["id"] for line in report["lines"]] == wanted and len(wanted) == 33
    assert [line["id"] for line in report["lines"] if not line["match"]] == []
    assert report["matched"] == report["total"] == 33
    assert [r for r in report["regression"] if not r["same"]] == [] and len(report["regression"]) == 6


def test_a_wrong_answer_is_a_mismatch_never_hidden():
    def mismatches(change):
        answers = good_answers()
        change(answers)
        return [line["id"] for line in ar.compare_real(KEY, answers)["lines"] if not line["match"]]

    assert mismatches(
        lambda a: a["verify"].update({("openjdk 17.0.2", "ECDSA P-256"): {"result": "False", "summary": ""}})
    ) == ["RV1"]
    # Java 17.0.3 passing the exam would not match the key: it must stay Failed (Kevin's decision 2)
    assert "RE3" in mismatches(
        lambda a: a["after"]["openjdk"].update(
            {("openjdk 17.0.2", "official_vectors"): result("Passed", component="openjdk 17.0.3")}
        )
    )
    # the blank signature must be among what 17.0.2 accepted
    assert "RE1" in mismatches(
        lambda a: a["first"].update({("openjdk 17.0.2", "official_vectors"): result("Failed", [w(6)])})
    )

    # a control that did not behave makes its test a mismatch
    def bad_control(a):
        a["first"][("elliptic 6.5.6", "official_vectors")]["control"] = "not_as_expected"

    assert mismatches(bad_control) == ["RE9"]

    # a crash with no Also noticed note
    def no_note(a):
        a["after"]["python-ecdsa"][("python-ecdsa 0.13.2", "official_vectors")]["also_noticed"] = []

    assert mismatches(no_note) == ["RE7"]

    # a pull request offered for a real library
    def offered(a):
        a["fixes_first"][0]["pull_request"] = {"number": 1}

    assert mismatches(offered) == ["RF1"]

    # OpenSSL read as blocked
    def blocked(a):
        a["migration"]["openssl 3.5.9 (ECDSA P-256)"]["blockers"] = ["x"]

    assert mismatches(blocked) == ["RM1"]

    # something of a real library ran in demo mode
    def ran(a):
        a["demo_mode"]["tests"] = [{"label": "Passed", "code": "passed", "reason_code": None}] * 15

    assert mismatches(ran) == ["RD1"]


def test_an_answer_that_ran_on_another_version_is_a_mismatch():
    """elliptic 6.5.6 passes Attacker tricks too, so the label alone would not show a retest that never moved the library."""
    answers = good_answers()
    answers["after"]["elliptic"][("elliptic 6.5.6", "bad_signatures")]["component"] = "elliptic 6.5.6"
    wrong = [line["id"] for line in ar.compare_real(KEY, answers)["lines"] if not line["match"]]
    assert wrong == ["RE12", "RB3"]


def test_a_changed_trial_count_is_reported():
    answers = good_answers()
    answers["first"][("openjdk 17.0.2", "official_vectors")]["detail"][
        "wrong"
    ].pop()  # 12, not the trial's 13 (168 is still there)
    report = ar.compare_real(KEY, answers)
    changed = [r for r in report["regression"] if not r["same"]]
    assert [(r["what"], r["expected"], r["actual"]) for r in changed] == [("openjdk 17.0.2 exam wrong", 13, 12)]


def test_in_demo_mode_only_the_demo_mode_answer_is_graded():
    answers = copy.deepcopy(good_answers())
    answers.update(mode="demo", verify={}, first={}, after={}, fixes_first=[], fixes_after={}, migration={})
    report = ar.compare_real(KEY, answers)
    assert (report["matched"], report["total"]) == (1, 1) and report["regression"] == []
    assert [line["id"] for line in report["lines"] if line["applies"]] == ["RD1"]
    assert not any(
        line["match"] for line in report["lines"] if not line["applies"]
    )  # not applicable is never counted as a match

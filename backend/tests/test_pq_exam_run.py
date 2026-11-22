"""How a post-quantum exam is run (execute/pqvectors.py), with a stand-in for the container runner: the library's own cases go
to the library's image, and every control goes to the OpenSSL image, whatever library is examined. No Docker."""

from app.engine import pq_vectors
from app.engine import research
from app.run import runner
from app.run.execute import RunContext, pqvectors, signing

from test_real_libraries import real_claims


class FakeRunner:
    def __init__(self, cases):
        self.cases, self.calls = {c.id: c for c in cases}, []

    def run_job(self, job, *, time_limit=120.0, on_line=None, family=None):
        self.calls.append((job["subject"], family, len(job["cases"])))
        lines = []
        for asked in job["cases"]:
            case = self.cases[asked["id"]]
            line = {"subject": job["subject"], "id": case.id, "rc": 0, "error": None, "declined": case.expect == "refuse",
                    "valid": {"accept": True, "reject": False}.get(case.expect) if case.command == "verify" else None,
                    "answer_sha256": case.answer_sha256, "ms": 1.0}
            lines.append(line)
            if on_line:
                on_line(line)
        return runner.BatchResult(True, lines, None, "isolated", "fake", "2026-11-15T00:00:00.000Z", 1, "")


def context(fake, family_images):
    mode = runner.ModeInfo("isolated", "", None, True, "components-image", None, family_images)
    return RunContext(settings=None, mode=mode, runner=fake, gate=None, progress=lambda text, percent: None, log=lambda text: None,
                      address_check=lambda address: None, component=("openssl", "3.5.9"))


def spec_for(kind):
    claims = real_claims()
    ref = next(p["ref"] for p in research.programs(claims) if kind in research.program_kinds(p))
    return research.RuleEngine()._design(kind, claims, ref)


def test_the_library_runs_in_its_own_image_and_every_control_in_the_openssl_image(monkeypatch):
    cases = pq_vectors.load("mlkem_vectors")
    fake = FakeRunner(cases)
    # as if the library examined lived in another family's image
    monkeypatch.setattr(signing, "family_of", lambda ctx, version=None: "another-library")
    monkeypatch.setattr(pqvectors, "family_of", lambda ctx, version=None: "another-library")
    raw = pqvectors.run_pq_exam(spec_for("mlkem_vectors"), context(fake, {"another-library": "image-a", "openssl": "image-o"}))
    assert "problem" not in raw
    assert fake.calls[0] == ("openssl-3.5.9", "another-library", 655)
    assert [(subject, family) for subject, family, _ in fake.calls[1:]] == [
        ("control-pq-wrong-answer", "openssl"), ("control-pq-skip-key-check", "openssl"), ("control-pq-skip-key-check", "openssl")]
    assert [n for _, _, n in fake.calls[1:]] == [125, 300, 230]
    assert len(raw["subject"]["answers"]) == 655 and set(raw["controls"]) == {"keygen", "encaps", "decaps"}


def test_the_signature_exam_asks_the_accept_everything_control_for_verification():
    cases = pq_vectors.load("mldsa_vectors")
    fake = FakeRunner(cases)
    raw = pqvectors.run_pq_exam(spec_for("mldsa_vectors"), context(fake, {"openssl": "image-o"}))
    assert [(subject, family, n) for subject, family, n in fake.calls] == [
        ("openssl-3.5.9", "openssl", 475), ("control-pq-wrong-answer", "openssl", 25), ("control-pq-wrong-answer", "openssl", 191),
        ("control-accept-all", "openssl", 255)]
    assert raw["controls"]["verify"]["control"] == "accept_all"


def test_a_real_library_is_never_examined_outside_isolated_mode_or_without_its_image():
    fake = FakeRunner(pq_vectors.load("mlkem_vectors"))
    spec = spec_for("mlkem_vectors")
    demo = context(fake, {})
    demo.mode = runner.ModeInfo("demo", "", None, False, None, None)
    assert pqvectors.run_pq_exam(spec, demo)["problem"]["code"] == "needs_isolated_mode"
    assert pqvectors.run_pq_exam(spec, context(fake, {}))["problem"]["code"] == "real_image_missing"
    assert fake.calls == []   # nothing was started either time

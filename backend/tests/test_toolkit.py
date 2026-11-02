"""Cryptanalysis-suite toolkit: parameter bounds, argv construction, redaction, API, and (when crax is built) every control."""
import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from conftest import ok, new_project

import runners.all  # noqa: F401
from runners import get_runner, RunRequest
from runners.suite_tools import TOOLS, ParamError
from app import controls

REAL_CRAX = os.environ.get("IEL_CRAX_BIN") or shutil.which("crax")
LIMITS = {"timeout_s": 120, "memory_mb": 1024, "cpu_s": 120}


# ---------------------------------------------------------------- validation and argv (no binary needed)

@pytest.mark.parametrize("tool,params,needle", [
    ("suite_curve_audit", {"curve": "--help"}, "curve must"),
    ("suite_weak_curve", {"curve": "custom; rm -rf /"}, "curve must be one of"),
    ("suite_weak_curve", {"curve": "custom", "p": "-7"}, "non-negative"),
    ("suite_weak_curve", {"curve": "custom", "p": str(2 ** 600)}, "at most 521 bits"),
    ("suite_ecdsa_audit", {"curve": "p256", "public_key": "1,2", "signatures": [{"r": "1", "s": "2", "z": "--x"}]}, "decimal"),
    ("suite_ecdsa_audit", {"curve": "p256", "public_key": "1,2", "signatures": [{"r": "1", "s": "1", "z": "1"}] * 513}, "1 to 512"),
    ("suite_rsa_key_audit", {"moduli": [str(i + 3) for i in range(33)]}, "1 to 32"),
    ("suite_rsa_key_audit", {"moduli": ["15"], "fermat_iterations": 10 ** 9}, "fermat_iterations"),
    ("suite_mlwe_estimate", {"scheme": "kyber-9000"}, "scheme must be one of"),
    ("suite_generic_rho", {"curve": "p256", "secret": "1"}, "curve must be one of"),
    ("suite_factor_toy", {"n": str(2 ** 200)}, "at most 128 bits"),
    ("suite_aes_reduced", {"technique": "linear", "samples": "4096"}, "samples"),
    ("suite_hash_kat", {"algorithm": "sha256", "hex": "zz"}, "hex"),
])
def test_tool_parameters_are_bounded(tool, params, needle):
    with pytest.raises(ParamError, match=needle):
        TOOLS[tool].build(TOOLS[tool].validate(params))


def test_argv_comes_only_from_validated_values():
    t = TOOLS["suite_ecdsa_audit"]
    p = t.validate({"curve": "p256", "public_key": "5,6", "signatures": [{"r": "1", "s": "2", "z": "3"}], "full_sweep": True,
                    "unexpected": "--force", "demo_sigs": 64})
    assert "unexpected" not in p and "demo_sigs" not in p          # undeclared and inapplicable keys are dropped
    assert t.build(p) == [["ecdsa", "audit", "--curve", "p256", "--q", "5,6", "--no-prefilter", "--sig", "1,2,3"]]
    weak = TOOLS["suite_weak_curve"]
    assert weak.build(weak.validate({"curve": "p256", "p": "7"})) == [["ecdlp", "--curve", "p256", "--analyze-only", "--x", "1"]]
    rsa = TOOLS["suite_rsa_key_audit"]
    cmds = rsa.build(rsa.validate({"moduli": "15 21"}))
    assert cmds[0] == ["rsa", "batch-gcd", "15", "21"] and len(cmds) == 5


def test_every_tool_declares_limitations_acceptance_and_known_family():
    from runners.suite_tools import FAMILIES
    for t in TOOLS.values():
        assert t.family in FAMILIES and t.limitations and t.acceptance and t.question
        for c in t.controls:
            t.build(t.validate(c["params"]))                        # every static preset is valid
    for cid in controls.GENERATED:
        tool, params, note = controls.generate(cid)
        assert note["kind"] in ("positive", "negative") and note["source"]
        TOOLS[tool].build(TOOLS[tool].validate(params))


def test_weak_rsa_controls_plant_what_they_claim():
    import math
    w = controls.weak_rsa_moduli()
    n0, n1, n2 = (int(x) for x in w["moduli"][:3])
    assert math.gcd(n0, n1) > 1
    s = math.isqrt(n2)
    assert (s + 1) ** 2 - n2 < 2 ** 200                             # close primes: n2 is near a square
    v = controls.wiener_rsa_modulus()
    assert int(v["public_exponent"]).bit_length() > 900             # large e, small d


# ---------------------------------------------------------------- redaction with a fake suite

def _fake_crax(tmp_path: Path) -> Path:
    binary = tmp_path / "crax"
    binary.write_text(f"""#!{sys.executable}
import json, sys
a = sys.argv[1:]
if a == ["--version"]:
    print("crax 0.1.0-test"); raise SystemExit(0)
if a[1:3] == ["ecdsa", "audit"]:
    print(json.dumps({{"status": "ok", "curve": "P-256", "signatures": 2, "bias_score": 0.9, "verdict": "key_recovered",
                      "k_bits": 128, "d": "424242424242", "verified": True}}))
elif a[1:3] == ["rsa", "batch-gcd"]:
    print(json.dumps({{"moduli": 2, "factored": [{{"index": 0, "p": "3", "q": "5"}}, {{"index": 1, "p": "3", "q": "7"}}], "duplicates": []}}))
elif a[1] == "rsa":
    print(json.dumps({{"attack": a[2], "n": a[3], "p": None, "q": None, "d": None, "verified": False}})); raise SystemExit(1)
else:
    raise SystemExit(2)
""")
    binary.chmod(0o755)
    return binary


def test_recovered_secrets_from_real_targets_are_redacted(monkeypatch, tmp_path):
    monkeypatch.setenv("IEL_CRAX_BIN", str(_fake_crax(tmp_path)))
    runner = get_runner("cryptanalysis_suite")
    r = runner.run(RunRequest("suite_ecdsa_audit", {"curve": "p256", "public_key": "1,2", "signatures": [{"r": "1", "s": "2", "z": "3"}]}, {}, {}, LIMITS))
    assert r.status == "completed", r.failures
    assert r.metrics["key_recovered"] == 1
    assert not next(s for s in r.scenarios if s["id"] == "ecdsa_verdict")["pass"]   # expected no_bias: a real finding
    assert b"424242424242" not in r.raw_output and b"[redacted sha256:" in r.raw_output and r.exclusions

    rsa = runner.run(RunRequest("suite_rsa_key_audit", {"moduli": ["15", "21"]}, {}, {}, LIMITS))
    assert rsa.status == "completed", rsa.failures                  # exit 1 + JSON is a negative result, not a failure
    assert rsa.metrics["shared_prime_moduli"] == 2 and b'"3"' not in rsa.raw_output and rsa.exclusions
    synthetic = runner.run(RunRequest("suite_rsa_key_audit", {"moduli": ["15", "21"], "synthetic": True, "expect": "weakness_detected"}, {}, {}, LIMITS))
    assert synthetic.status == "completed" and all(s["pass"] for s in synthetic.scenarios) and not synthetic.exclusions


# ---------------------------------------------------------------- API

def test_toolkit_api_catalog_run_and_portfolio(engineer, reviewer, monkeypatch, tmp_path):
    monkeypatch.setenv("IEL_CRAX_BIN", str(_fake_crax(tmp_path)))
    tk = ok(engineer.get("/api/toolkit"))
    assert tk["suite"]["available"] and len(tk["suite"]["sha256"]) == 64
    assert {t["id"] for t in tk["tools"]} == set(TOOLS)
    assert any(c.get("generated") for t in tk["tools"] for c in t["controls"])
    pid = new_project(engineer, reviewer, name="toolkit api", kind="iot")["id"]
    impl = ok(engineer.post(f"/api/projects/{pid}/implementations", json={"name": "verifier", "version": "1", "role": "candidate", "profile_id": "ml_dsa_65"}))
    bad = engineer.post(f"/api/projects/{pid}/toolkit/run", json={"tool": "suite_rsa_key_audit", "implementation_id": impl["id"], "params": {"moduli": ["x"]}})
    assert bad.status_code == 400 and "decimal" in bad.json()["detail"]
    assert engineer.post(f"/api/projects/{pid}/toolkit/run", json={"tool": "rm", "implementation_id": impl["id"]}).status_code == 400
    run = ok(engineer.post(f"/api/projects/{pid}/toolkit/run", json={"tool": "suite_rsa_key_audit", "implementation_id": impl["id"],
                                                                    "params": {"moduli": ["15", "21"], "synthetic": True, "expect": "weakness_detected"}}))
    assert run["status"] == "completed" and run["overall_pass"] is True
    listed = ok(engineer.get(f"/api/projects/{pid}/toolkit/runs"))
    assert listed[0]["tool"] == "suite_rsa_key_audit" and listed[0]["metrics"]["weak_moduli"] == 2
    detail = ok(engineer.get(f"/api/projects/{pid}/runs/{run['id']}"))
    assert detail["experiment"]["definition"]["contract"].startswith("crax --json rsa")
    pf = ok(engineer.get("/api/research/portfolio"))
    assert pf["provenance"] == "imported" and len(pf["source"]["sha256"]) == 64 and pf["rows"]
    assert all("ratio_rho" in r and "validation_status" in r for r in pf["rows"])


def test_suite_tools_ignore_profile_fixture_params():
    """A catalog profile's `scheme` (firmware fixture) must never reach a suite tool such as the lattice estimate."""
    from app.services import build_run_request
    from app.models import Experiment, Implementation
    exp = Experiment(project_id="p", name="x", fixture="suite_mlwe_estimate", definition={"params": {"scheme": "ml-dsa-44"}})
    impl = Implementation(project_id="p", name="v", version="1", role="candidate", profile_id="ml_dsa_65", configuration={"fixture_params": {"scheme": "evil"}})
    assert build_run_request(None, exp, impl).params == {"scheme": "ml-dsa-44"}


# ---------------------------------------------------------------- the real suite (skipped when crax is not built)

@pytest.mark.skipif(not REAL_CRAX, reason="crax binary not available (set IEL_CRAX_BIN)")
@pytest.mark.parametrize("tool_id,index", [(t.id, i) for t in TOOLS.values() for i in range(len(t.controls))])
def test_real_suite_static_controls(monkeypatch, tool_id, index):
    monkeypatch.setenv("IEL_CRAX_BIN", str(Path(REAL_CRAX).resolve()))
    c = TOOLS[tool_id].controls[index]
    r = get_runner("cryptanalysis_suite").run(RunRequest(tool_id, c["params"], {}, {}, LIMITS))
    assert r.status == "completed", r.failures
    assert all(s["pass"] for s in r.scenarios), [s for s in r.scenarios if not s["pass"]]


@pytest.mark.skipif(not REAL_CRAX, reason="crax binary not available (set IEL_CRAX_BIN)")
@pytest.mark.parametrize("control_id", [c for c in controls.GENERATED if c != "es256_transcript"] + ["es256_transcript_quick"])
def test_real_suite_generated_controls(monkeypatch, control_id):
    monkeypatch.setenv("IEL_CRAX_BIN", str(Path(REAL_CRAX).resolve()))
    if control_id == "es256_transcript_quick":   # the seeded control runs the ~20 s full sweep; the test uses the prefilter path
        tool, params = "suite_ecdsa_audit", {**controls.es256_transcript(16), "mode": "transcript", "expect": "no_bias"}
        params.pop("source")
    else:
        tool, params, _ = controls.generate(control_id)
    r = get_runner("cryptanalysis_suite").run(RunRequest(tool, params, {}, {}, LIMITS))
    assert r.status == "completed", r.failures
    assert all(s["pass"] for s in r.scenarios), [s for s in r.scenarios if not s["pass"]]

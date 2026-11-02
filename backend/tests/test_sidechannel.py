"""Side-channel tool: parameter bounds, runner separation, site classification, end-to-end with fakes, API, real binary."""
import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from conftest import ok, new_project

import runners.all  # noqa: F401
from runners import get_runner, RunRequest
from runners.ct_audit_runner import map_entry, is_harness_site
from runners.suite_tools import TOOLS, ParamError

SNAP = json.loads((Path(__file__).resolve().parents[2] / "seeds" / "ct_audit_snapshot.json").read_text())
BY_TARGET = {e["target"]: e for e in SNAP["targets"]}
REAL_BIN = os.environ.get("IEL_CT_AUDIT_BIN")
LIMITS = {"timeout_s": 600, "cpu_s": 600}


@pytest.mark.parametrize("params", [{"target": "--help"}, {"target": "x25519; rm -rf /"}, {"target": "x25519", "instrument": "perf"},
                                    {"target": "x25519", "expect": "maybe"}])
def test_parameters_are_fixed_choices(params):
    with pytest.raises(ParamError):
        TOOLS["sidechannel_ct_audit"].validate(params)


def test_runners_only_accept_their_own_tools():
    assert "sidechannel_ct_audit" not in get_runner("cryptanalysis_suite").describe()["fixtures"]
    assert get_runner("ct_audit").describe()["fixtures"] == ["sidechannel_ct_audit"]
    r = get_runner("ct_audit").run(RunRequest("suite_curve_audit", {"curve": "p256"}, {}, {}))
    assert r.status == "failed" and "not allowlisted" in r.failures[0]


def test_site_classification_matches_the_frozen_run():
    """Library vs harness split on the imported isogeny-labs/crypto #3296 summary (the corrected report's counts)."""
    expected = {"ctrl_pos_branch": (2, 0), "x25519": (0, 0), "smul_p256": (3, 1), "smul_sm2_generic": (1, 1),
                "inv_prime_ct": (5, 1), "inv_euclid": (6, 2), "ed25519_sign": (7, 0)}
    for target, (lib, harness) in expected.items():
        m = map_entry(BY_TARGET[target], "both", "clean")["metrics"]
        assert (m["taint_sites_library"], m["taint_sites_harness"]) == (lib, harness), target
    assert not is_harness_site("ct_dynamic_audit::ctrl_pos_branch @ research/ct_dynamic_audit_20261102/src/main.rs:125 [UninitCondition]")
    assert is_harness_site("{closure#0} @ research/ct_dynamic_audit_20261102/src/main.rs:145 [UninitCondition]")


def test_verdicts_follow_expectations_and_not_applicable_is_neither():
    pos = map_entry(BY_TARGET["ctrl_pos_branch"], "both", "leak_detected")
    assert all(s["pass"] for s in pos["scenarios"]) and pos["metrics"]["ir_secret_dependent"] == 1
    neg = map_entry(BY_TARGET["ctrl_neg_masked"], "both", "clean")
    assert all(s["pass"] for s in neg["scenarios"]) and neg["metrics"]["ir_secret_dependent"] == 0
    ed = map_entry(BY_TARGET["ed25519_sign"], "both", "clean")
    taint, ir = (next(s for s in ed["scenarios"] if s["id"] == k) for k in ("taint", "ir"))
    assert taint["pass"] is False and ir["pass"] is None and "ir_secret_dependent" not in ed["metrics"]
    only_taint = map_entry(BY_TARGET["x25519"], "taint", "clean")
    assert [s["id"] for s in only_taint["scenarios"]] == ["taint"] and "ir_min" not in only_taint["metrics"]


def _fakes(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A fake Valgrind that records its argv, and a fake ct_dynamic_audit whose `analyze` writes a fixed summary."""
    log = tmp_path / "argv.log"
    valgrind = tmp_path / "valgrind"
    valgrind.write_text(f"""#!{sys.executable}
import sys
if sys.argv[1:] == ["--version"]:
    print("valgrind-3.22.0-fake"); raise SystemExit(0)
open({str(log)!r}, "a").write(" ".join(sys.argv[1:]) + "\\n")
""")
    binary = tmp_path / "ct_dynamic_audit"
    entry = json.dumps(BY_TARGET["smul_sm2_generic"])
    binary.write_text(f"""#!{sys.executable}
import json, os, sys
open({str(log)!r}, "a").write("BIN " + " ".join(sys.argv[1:]) + "\\n")
if sys.argv[1] == "analyze":
    os.makedirs(sys.argv[3], exist_ok=True)
    json.dump([json.loads({entry!r})], open(os.path.join(sys.argv[3], "summary.json"), "w"))
""")
    for f in (valgrind, binary):
        f.chmod(0o755)
    return valgrind, binary, log


def test_end_to_end_with_fakes_builds_fixed_argv(monkeypatch, tmp_path):
    valgrind, binary, log = _fakes(tmp_path)
    monkeypatch.setenv("IEL_VALGRIND_BIN", str(valgrind))
    monkeypatch.setenv("IEL_CT_AUDIT_BIN", str(binary))
    r = get_runner("ct_audit").run(RunRequest("sidechannel_ct_audit", {"target": "smul_sm2_generic", "unexpected": "--force"}, {}, {}, LIMITS))
    assert r.status == "completed", r.failures
    lines = log.read_text().splitlines()
    assert lines[0].startswith("--tool=memcheck --xml=yes") and lines[0].endswith("taint smul_sm2_generic")
    assert lines[1].startswith("--tool=callgrind --collect-atstart=no") and lines[1].endswith("ir smul_sm2_generic")
    assert lines[2].startswith("BIN analyze ") and "--force" not in log.read_text()
    assert r.metrics["taint_sites_library"] == 1
    assert next(s for s in r.scenarios if s["id"] == "taint")["pass"] is False      # point.rs:390 is a real finding
    assert all("/tmp/iel-ct-" not in " ".join(c["argv"]) for c in r.commands)    # temp paths recorded as $WORKDIR
    assert "--xml-file=$WORKDIR/raw/memcheck-smul_sm2_generic.xml" in r.commands[0]["argv"]
    assert len(r.environment["ct_dynamic_audit_sha256"]) == 64


def test_toolkit_api_reports_per_tool_availability_and_refuses_when_unavailable(engineer, reviewer, monkeypatch, tmp_path):
    monkeypatch.setenv("IEL_CT_AUDIT_BIN", str(tmp_path / "missing"))
    tk = ok(engineer.get("/api/toolkit"))
    ct = next(t for t in tk["tools"] if t["id"] == "sidechannel_ct_audit")
    assert ct["runner"] == "ct_audit" and ct["available"] is False and "IEL_CT_AUDIT_BIN" in ct["unavailable_reason"]
    assert "Side channels" in tk["families"]
    pid = new_project(engineer, reviewer, name="sidechannel api", kind="application")["id"]
    impl = ok(engineer.post(f"/api/projects/{pid}/implementations", json={"name": "lib", "version": "1", "role": "baseline"}))
    res = engineer.post(f"/api/projects/{pid}/toolkit/run", json={"tool": "sidechannel_ct_audit", "implementation_id": impl["id"], "params": {"target": "x25519"}})
    assert res.status_code == 409 and "unavailable" in res.json()["detail"]


@pytest.mark.skipif(not (REAL_BIN and shutil.which("valgrind")), reason="ct_dynamic_audit binary or valgrind not available (set IEL_CT_AUDIT_BIN)")
@pytest.mark.parametrize("index", [0, 1])
def test_real_binary_controls(monkeypatch, index):
    monkeypatch.setenv("IEL_CT_AUDIT_BIN", REAL_BIN)
    c = TOOLS["sidechannel_ct_audit"].controls[index]
    r = get_runner("ct_audit").run(RunRequest("sidechannel_ct_audit", c["params"], {}, {}, LIMITS))
    assert r.status == "completed", r.failures
    assert all(s["pass"] for s in r.scenarios), r.scenarios

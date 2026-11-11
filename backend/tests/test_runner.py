"""The batch driver's protocol, the runner's limits, and how the mode is decided. All in demo mode (no Docker needed)."""
import dataclasses
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app import runner
from app.components import WITHHELD
from app.config import COMPONENTS_DIR, OPENSSL_IMAGE, Settings, load_settings

# a real point on P-256 (the curve's base point), so it is accepted as a public key
PUBLIC = ("04" "6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296"
          "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5")
CASE = {"id": "zero", "public_key": PUBLIC, "message": "", "signature": "3006020100020100"}


def settings_for(tmp_path, **kw):
    return Settings(data_dir=tmp_path, demo_tls_port=1, **kw)


@pytest.fixture
def demo(tmp_path):
    return runner.ComponentRunner(runner.detect_mode(settings_for(tmp_path, force_mode="demo")))


@pytest.fixture
def fake_driver(tmp_path, monkeypatch):
    """Swap our driver for a stand-in script, to test the runner's own limits."""
    def install(body: str) -> Path:
        path = tmp_path / "fake_driver.py"
        path.write_text("import json, os, sys, time\njob = json.loads(sys.stdin.read())\n" + body)
        monkeypatch.setattr(runner, "LOCAL_DRIVER", path)
        return path
    return install


# ------------------------------------------------------------------ driver protocol

def test_call_op_and_private_key_is_withheld(demo):
    result = demo.run_job({"op": "call", "subject": "acme-sign-1.4.3", "command": "info", "input": {}})
    assert result.ok and result.problem is None and result.mode == "demo" and len(result.lines) == 1
    line = result.lines[0]
    assert set(line) == {"subject", "command", "rc", "out", "error", "ms"} and line["rc"] == 0 and line["error"] is None
    assert (line["out"]["name"], line["out"]["version"]) == ("acme-sign", "1.4.3")
    assert result.started_at.endswith("Z") and result.duration_ms >= 0 and "driver.py" in result.command
    keygen = demo.run_job({"op": "call", "subject": "acme-sign-1.4.2", "command": "keygen", "input": {}})
    assert keygen.ok and keygen.lines[0]["out"]["private_key"] == WITHHELD and len(keygen.lines[0]["out"]["public_key"]) == 130
    bad = demo.run_job({"op": "call", "subject": "acme-sign-1.4.2", "command": "sign",
                        "input": {"private_key": "zz-not-hex", "message": "00"}})
    assert bad.ok and bad.lines[0]["rc"] == 1 and bad.lines[0]["out"] is None and "bad input" in bad.lines[0]["error"]
    assert "zz-not-hex" not in json.dumps(dataclasses.asdict(bad))


def test_verify_batch_op_order_and_shapes(demo):
    seen = []
    cases = [CASE, {**CASE, "id": "not-a-signature", "signature": "00"}, {**CASE, "id": "bad-key", "public_key": "04"}]
    result = demo.run_job({"op": "verify_batch", "subjects": ["acme-sign-1.4.2", "acme-sign-1.4.3", "control-accept-all"],
                           "cases": cases}, on_line=seen.append)
    assert result.ok and seen == result.lines
    assert [(line["subject"], line["id"]) for line in result.lines] == [
        (s, c["id"]) for s in ("acme-sign-1.4.2", "acme-sign-1.4.3", "control-accept-all") for c in cases]
    answers = {(line["subject"], line["id"]): (line["valid"], line["error"]) for line in result.lines}
    assert answers[("acme-sign-1.4.2", "zero")] == (True, None)       # the planted bug, seen through the harness
    assert answers[("acme-sign-1.4.3", "zero")] == (False, None)
    assert answers[("acme-sign-1.4.3", "not-a-signature")] == (False, None)
    assert answers[("acme-sign-1.4.3", "bad-key")][0] is None and "bad input" in answers[("acme-sign-1.4.3", "bad-key")][1]
    assert all(answers[("control-accept-all", c["id"])] == (True, None) for c in cases)
    assert all(set(line) == {"subject", "id", "rc", "valid", "error", "ms"} for line in result.lines)


def test_bench_rounds_op_alternates_order_and_never_shows_the_key(demo):
    subjects = ["acme-sign-1.4.2", "acme-sign-1.4.3", "control-slow:acme-sign-1.4.3"]
    result = demo.run_job({"op": "bench_rounds", "keygen_with": "acme-sign-1.4.2", "subjects": subjects, "rounds": 3,
                           "repeats": 4, "message": "aabbcc"})
    assert result.ok and result.lines[0] == {"keygen": "acme-sign-1.4.2", "rc": 0, "public_key_bytes": 65}
    rounds = result.lines[1:]
    assert [(line["round"], line["subject"]) for line in rounds] == (
        [(0, s) for s in subjects] + [(1, s) for s in reversed(subjects)] + [(2, s) for s in subjects])
    for line in rounds:
        assert set(line) == {"round", "subject", "rc", "out", "error"} and line["rc"] == 0 and line["error"] is None
        out = line["out"]
        assert len(out["sign_ms"]) == 4 and len(out["verify_ms"]) == 4 and out["all_verified"] is True
        assert out["public_key_bytes"] == 65 and "private_key" not in out
    assert len({line["out"]["signature_bytes"] for line in rounds}) == 1  # same key and message for every subject
    slow = [line["out"] for line in rounds if line["subject"].startswith("control-slow")]
    assert all(min(out["sign_ms"]) >= 3.0 and min(out["verify_ms"]) >= 3.0 for out in slow)
    text = json.dumps(dataclasses.asdict(result))
    assert "private" not in text.lower()
    assert "bench_rounds: 3 rounds of 4" in result.command


def test_roundtrip_op_makes_signs_and_checks_without_showing_the_key(demo):
    """The Verify step's round trip in one job: the test key is made and used inside the driver only."""
    import re
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    message = "00112233"
    result = demo.run_job({"op": "roundtrip", "subject": "acme-sign-1.4.2", "message": message})
    assert result.ok and [line["step"] for line in result.lines] == ["keygen", "sign", "verify"]
    assert all(set(line) == {"subject", "step", "rc", "out", "error", "ms"} and line["rc"] == 0 and line["error"] is None
               for line in result.lines)
    keygen, sign, verify = (line["out"] for line in result.lines)
    assert keygen["private_key"] == WITHHELD and verify == {"valid": True}
    public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(keygen["public_key"]))
    public.verify(bytes.fromhex(sign["signature"]), bytes.fromhex(message), ec.ECDSA(hashes.SHA256()))  # a real signature
    assert "roundtrip: acme-sign-1.4.2 keygen, sign, verify" in result.command
    done = subprocess.run([sys.executable, "-I", "-B", str(COMPONENTS_DIR / "harness" / "driver.py")],
                          input=json.dumps({"op": "roundtrip", "subject": "acme-sign-1.4.3", "message": message}),
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and done.stderr == "" and not re.search(r"\b[0-9a-f]{64}\b", done.stdout)
    assert json.loads(done.stdout.splitlines()[-1]) == {"done": True, "lines": 3}


def test_the_test_key_never_leaves_the_driver():
    """Run the driver directly and look at everything it writes: no 64-hex private key anywhere."""
    import re
    job = {"op": "bench_rounds", "keygen_with": "acme-sign-1.4.3", "subjects": ["acme-sign-1.4.3"], "rounds": 1, "repeats": 1, "message": ""}
    done = subprocess.run([sys.executable, "-I", "-B", str(COMPONENTS_DIR / "harness" / "driver.py")], input=json.dumps(job),
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and done.stderr == ""
    assert not re.search(r"\b[0-9a-f]{64}\b", done.stdout) and "private" not in done.stdout
    assert json.loads(done.stdout.splitlines()[-1]) == {"done": True, "lines": 2}


@pytest.mark.parametrize("job,why", [
    ({"op": "call", "subject": "acme-sign-9.9.9", "command": "info"}, "unknown subject"),
    ({"op": "call", "subject": "../acme-sign-1.4.2", "command": "info"}, "unknown subject"),
    ({"op": "call", "subject": "/bin/sh", "command": "info"}, "unknown subject"),
    ({"op": "call", "subject": str(COMPONENTS_DIR / "acme-sign-1.4.2" / "acme_sign.py"), "command": "info"}, "unknown subject"),
    ({"op": "call", "subject": ["acme-sign-1.4.2"], "command": "info"}, "unknown subject"),
    ({"op": "call", "subject": "control-slow:/etc/passwd", "command": "info"}, "unknown subject"),
    ({"op": "call", "subject": "acme-sign-1.4.2", "command": "info; id"}, "unknown command"),
    ({"op": "call", "subject": "acme-sign-1.4.2", "command": "info", "input": "x"}, "input must be"),
    ({"op": "verify_batch", "subjects": ["acme-sign-1.4.2", "nope"], "cases": [CASE]}, "unknown subject"),
    ({"op": "verify_batch", "subjects": ["acme-sign-1.4.2"], "cases": []}, "cases must be"),
    ({"op": "verify_batch", "subjects": ["acme-sign-1.4.2"], "cases": [{**CASE, "signature": "/etc/passwd"}]}, "hex"),
    ({"op": "verify_batch", "subjects": ["acme-sign-1.4.2"], "cases": [{**CASE, "id": 7}]}, "id"),
    ({"op": "bench_rounds", "keygen_with": "x", "subjects": ["acme-sign-1.4.2"], "rounds": 1, "repeats": 1}, "unknown subject"),
    ({"op": "bench_rounds", "keygen_with": "acme-sign-1.4.2", "subjects": ["acme-sign-1.4.2"], "rounds": 999, "repeats": 1}, "rounds"),
    ({"op": "bench_rounds", "keygen_with": "acme-sign-1.4.2", "subjects": ["acme-sign-1.4.2"], "rounds": 1, "repeats": 0}, "repeats"),
    ({"op": "roundtrip", "subject": "/bin/sh", "message": "00"}, "unknown subject"),
    ({"op": "roundtrip", "subject": "acme-sign-1.4.2", "message": "/etc/passwd"}, "hex"),
    ({"op": "run", "path": "/bin/sh"}, "unknown job"),
    (["not", "an", "object"], "unknown job"),
])
def test_jobs_that_do_not_fit_are_refused_before_anything_runs(demo, job, why):
    result = demo.run_job(job)
    assert not result.ok and result.lines == []
    assert result.problem.startswith(runner.PROBLEM_REFUSED_PREFIX) and why in result.problem


def test_no_path_or_program_is_taken_from_a_job(demo, tmp_path, monkeypatch):
    """The command line is fixed; a job only travels on stdin. Extra fields in a job change nothing."""
    marker = tmp_path / "marker"
    evil = tmp_path / "evil.py"
    evil.write_text(f"open({str(marker)!r}, 'w').write('ran')\nprint('{{\"valid\": true}}')\n")
    seen = []
    real_popen = subprocess.Popen

    def spy(argv, **kw):
        seen.append((list(argv), kw))
        return real_popen(argv, **kw)
    monkeypatch.setattr(runner.subprocess, "Popen", spy)
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "do-not-leak")
    job = {"op": "call", "subject": "acme-sign-1.4.2", "command": "info", "input": {}, "path": str(evil), "argv": [str(evil)],
           "network": "host", "volumes": ["/:/host"], "image": "alpine", "driver": str(evil), "env": {"X": "1"}}
    result = demo.run_job(job)
    assert result.ok and result.lines[0]["out"]["name"] == "acme-sign" and not marker.exists()
    (argv, kw), = seen
    assert argv[:2] == [sys.executable, "-I"] and argv[2] == "-X" and argv[3].startswith("pycache_prefix=")
    assert argv[4:] == [str(COMPONENTS_DIR / "harness" / "driver.py")]
    assert kw["shell"] is False and set(kw["env"]) == {"PATH", "LANG", "PYTHONIOENCODING"}
    assert str(evil) not in " ".join(argv) and Path(kw["cwd"]).name.startswith("evidence-lab-run-")
    assert not Path(kw["cwd"]).exists()  # the scratch folder is gone afterwards


def test_driver_subject_table_is_fixed_and_points_only_inside_the_components_folder():
    import importlib.util
    spec = importlib.util.spec_from_file_location("evlab_driver", COMPONENTS_DIR / "harness" / "driver.py")
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    assert set(driver.SUBJECTS) == {"acme-sign-1.4.2", "acme-sign-1.4.3", "control-accept-all",
                                    "control-slow:acme-sign-1.4.2", "control-slow:acme-sign-1.4.3"}
    for parts in driver.SUBJECTS.values():
        for part in parts:
            assert Path(part).is_file() and COMPONENTS_DIR in Path(part).resolve().parents


# ------------------------------------------------------------------ the runner's limits

def alive_in_group(group: int) -> list[int]:
    """Process ids in a process group that are still running (killed-but-not-yet-collected ones do not count)."""
    alive = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            except OSError:
                continue
            if int(fields[2]) == group and fields[0] not in ("Z", "X"):
                alive.append(int(entry.name))
    return alive


def test_done_line_is_required(demo, fake_driver):
    fake_driver("print(json.dumps({'subject': 'x', 'valid': True}), flush=True)\n")
    result = demo.run_job({"op": "call"})
    assert not result.ok and result.problem == runner.PROBLEM_NO_DONE and len(result.lines) == 1
    fake_driver("print(json.dumps({'a': 1})); print(json.dumps({'done': True, 'lines': 5}))\n")  # wrong count
    assert demo.run_job({"op": "call"}).problem == runner.PROBLEM_NO_DONE
    fake_driver("print(json.dumps({'a': 1})); print(json.dumps({'done': True, 'lines': 1})); sys.exit(3)\n")
    assert demo.run_job({"op": "call"}).problem == runner.PROBLEM_NO_DONE
    fake_driver("print(json.dumps({'a': 1})); print(json.dumps({'done': True, 'lines': 1}))\n")
    assert demo.run_job({"op": "call"}).ok
    fake_driver("print('this is not json')\n")
    assert demo.run_job({"op": "call"}).problem == runner.PROBLEM_BAD_LINE


def test_timeout_kills_the_driver_and_its_children(demo, fake_driver, monkeypatch):
    fake_driver("import subprocess\nsubprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                "print(json.dumps({'started': True}), flush=True)\ntime.sleep(60)\n")
    procs = []
    real_popen = subprocess.Popen

    def spy(argv, **kw):
        procs.append(real_popen(argv, **kw))
        return procs[-1]
    monkeypatch.setattr(runner.subprocess, "Popen", spy)
    t0 = time.monotonic()
    result = demo.run_job({"op": "call"}, time_limit=1.0)
    assert not result.ok and result.problem == runner.PROBLEM_TIMEOUT and time.monotonic() - t0 < 10
    assert result.lines == [{"started": True}]  # what arrived before the limit is kept
    assert procs[0].poll() is not None
    time.sleep(0.2)
    assert alive_in_group(procs[0].pid) == []  # nothing is left running in the driver's process group, child included


def test_real_driver_stops_at_the_time_limit(demo):
    job = {"op": "bench_rounds", "keygen_with": "acme-sign-1.4.2", "subjects": ["acme-sign-1.4.2"], "rounds": 50,
           "repeats": 1000, "message": ""}
    t0 = time.monotonic()
    result = demo.run_job(job, time_limit=1.5)
    assert result.problem == runner.PROBLEM_TIMEOUT and time.monotonic() - t0 < 10


def test_output_is_capped_at_one_megabyte(demo, fake_driver):
    fake_driver("line = json.dumps({'pad': 'x' * 1000})\nwhile True:\n    print(line, flush=True)\n")
    t0 = time.monotonic()
    result = demo.run_job({"op": "call"}, time_limit=30)
    assert not result.ok and result.problem == runner.PROBLEM_TOO_MUCH_OUTPUT and time.monotonic() - t0 < 20
    assert sum(len(json.dumps(line)) for line in result.lines) <= runner.MAX_OUTPUT_BYTES == 1024 * 1024


def test_lines_and_stderr_are_scrubbed(demo, fake_driver):
    fake_driver("print(json.dumps({'out': {'private_key': 'aa' * 32, 'note': '-----BEGIN PRIVATE KEY-----\\\\nMIGHxyz\\\\n-----END PRIVATE KEY-----'}}))\n"
                "print('-----BEGIN EC PRIVATE KEY-----\\\\nMHcCxyz', file=sys.stderr)\n"
                "print(json.dumps({'done': True, 'lines': 1}))\n")
    result = demo.run_job({"op": "call"})
    text = json.dumps(dataclasses.asdict(result))
    assert result.ok and result.lines[0]["out"] == {"private_key": WITHHELD, "note": WITHHELD}
    assert "aa" * 32 not in text and "MIGHxyz" not in text and "MHcCxyz" not in text and "PRIVATE KEY" not in text


# ------------------------------------------------------------------ mode detection

def probe(monkeypatch, value):
    monkeypatch.setattr(runner, "_probe", lambda: value)


def test_mode_without_docker(monkeypatch, tmp_path):
    probe(monkeypatch, (False, None, None))
    mode = runner.detect_mode(settings_for(tmp_path))
    assert (mode.name, mode.docker_running, mode.components_image, mode.openssl_image) == ("demo", False, None, None)
    assert mode.line == "Demo mode: running our own demo software, not isolated." and mode.reason == "Docker is not running."


def test_mode_with_docker_but_without_our_image_stays_demo_and_says_why(monkeypatch, tmp_path):
    probe(monkeypatch, (True, None, OPENSSL_IMAGE))
    mode = runner.detect_mode(settings_for(tmp_path))
    assert (mode.name, mode.docker_running, mode.components_image, mode.openssl_image) == ("demo", True, None, OPENSSL_IMAGE)
    assert mode.line == ("Demo mode: running our own demo software, not isolated. Docker is running, but the test images "
                         "are not prepared yet; ./run-demo.sh prepares them.")


def test_mode_isolated_when_docker_and_image_are_ready(monkeypatch, tmp_path):
    probe(monkeypatch, (True, "evidence-lab-components:abc", None))
    mode = runner.detect_mode(settings_for(tmp_path))
    assert (mode.name, mode.reason, mode.components_image) == ("isolated", None, "evidence-lab-components:abc")
    assert mode.line == "Isolated mode: our demo software runs in a locked-down container with no network."


def test_mode_forced_demo(monkeypatch, tmp_path):
    probe(monkeypatch, (True, "evidence-lab-components:abc", OPENSSL_IMAGE))
    mode = runner.detect_mode(settings_for(tmp_path, force_mode="demo"))
    assert mode.name == "demo" and mode.openssl_image == OPENSSL_IMAGE
    assert mode.line == "Demo mode: running our own demo software, not isolated. Isolated mode is switched off for this run."


def test_mode_forced_isolated_but_unavailable_never_runs_unisolated(monkeypatch, tmp_path):
    probe(monkeypatch, (False, None, None))
    mode = runner.detect_mode(settings_for(tmp_path, force_mode="isolated"))
    assert mode.name == "isolated" and mode.components_image is None and "not available" in mode.line
    marker = tmp_path / "ran"
    stand_in = tmp_path / "driver.py"
    stand_in.write_text(f"open({str(marker)!r}, 'w').write('x')\n")
    monkeypatch.setattr(runner, "LOCAL_DRIVER", stand_in)
    result = runner.ComponentRunner(mode).run_job({"op": "call", "subject": "acme-sign-1.4.2", "command": "info", "input": {}})
    assert not result.ok and result.problem == runner.PROBLEM_ISOLATED == "isolated mode is not available"
    assert result.mode == "isolated" and not marker.exists()


def test_no_silent_fallback_when_docker_fails_mid_way(monkeypatch, tmp_path):
    """Isolated mode with an image, but the docker command cannot start: the job fails; nothing runs locally."""
    mode = runner.ModeInfo("isolated", runner.ISOLATED_LINE, None, True, "evidence-lab-components:abc", None)
    marker = tmp_path / "ran"
    stand_in = tmp_path / "driver.py"
    stand_in.write_text(f"open({str(marker)!r}, 'w').write('x')\n")
    monkeypatch.setattr(runner, "LOCAL_DRIVER", stand_in)
    calls = []

    def no_docker(argv, **kw):
        calls.append(list(argv))
        raise FileNotFoundError("docker")
    monkeypatch.setattr(runner.subprocess, "Popen", no_docker)
    result = runner.ComponentRunner(mode).run_job({"op": "call", "subject": "acme-sign-1.4.2", "command": "info", "input": {}})
    assert not result.ok and result.problem == runner.PROBLEM_ISOLATED and result.mode == "isolated" and not marker.exists()
    assert len(calls) == 1 and calls[0][:2] == ["docker", "run"]


def test_container_command_is_one_fixed_list(monkeypatch):
    mode = runner.ModeInfo("isolated", runner.ISOLATED_LINE, None, True, "evidence-lab-components:abc", None)
    argv = runner.ComponentRunner(mode)._container_argv("evlab-0123456789ab")
    assert argv == ["docker", "run", "--name", "evlab-0123456789ab", *runner.DOCKER_RUN_FLAGS, "evidence-lab-components:abc",
                    "python", "-I", "-X", "pycache_prefix=/scratch/pyc", "/opt/evidence-lab/components/harness/driver.py"]
    flags = runner.DOCKER_RUN_FLAGS
    pairs = dict(zip(flags[2:], flags[3:]))
    assert flags[:2] == ("--rm", "-i") and "--read-only" in flags
    for flag, value in {"--network": "none", "--user": "65534:65534", "--cap-drop": "ALL", "--security-opt": "no-new-privileges",
                        "--memory": "256m", "--memory-swap": "256m", "--cpus": "2", "--pids-limit": "64", "--pull": "never",
                        "--label": "evidence-lab=1", "--workdir": "/scratch", "--ipc": "none"}.items():
        assert pairs[flag] == value, flag
    assert pairs["--tmpfs"].startswith("/scratch:rw,noexec,nosuid")
    for banned in ("-v", "--volume", "--mount", "--privileged", "--device", "-e", "--env", "--env-file", "--pid", "--cap-add",
                   "--volumes-from", "host"):
        assert banned not in flags and not any(f.startswith(banned + "=") for f in flags)
    assert "docker.sock" not in " ".join(argv)


def test_image_tag_follows_the_component_files(monkeypatch, tmp_path):
    import shutil
    tag = runner.components_image_tag()
    assert tag.startswith("evidence-lab-components:") and len(tag.split(":")[1]) == 16 and tag == runner.components_image_tag()
    copy = tmp_path / "components"
    shutil.copytree(COMPONENTS_DIR, copy)
    monkeypatch.setattr(runner, "COMPONENTS_DIR", copy)
    (copy / "harness" / "__pycache__").mkdir(exist_ok=True)
    (copy / "harness" / "__pycache__" / "x.pyc").write_bytes(b"cache")
    assert runner.components_image_tag() == tag  # caches do not count
    with open(copy / "acme-sign-1.4.3" / "acme_sign.py", "a") as handle:
        handle.write("# changed\n")
    assert runner.components_image_tag() != tag


def test_docker_questions_never_raise_without_docker(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    runner._probe_cache.clear()
    try:
        assert runner.docker_running() is False and runner.image_present("x") is False
        assert runner._probe() == (False, None, None)
        runner.sweep_stale_containers()
    finally:
        runner._probe_cache.clear()


def test_sweep_only_removes_containers_older_than_any_run(monkeypatch):
    """A second copy of the app (accuracy check, tests) must never remove the container of a test that is running
    in the first: only containers older than the longest time limit are leftovers."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    stamp = lambda seconds: (now - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.123456789Z")  # noqa: E731
    calls = []

    def fake_docker(args, timeout):
        calls.append(list(args))
        if args[0] == "ps":
            return 0, "aaa\nbbb\nccc\nddd\n"
        if args[0] == "inspect":   # one of them ended meanwhile, so docker answers 1 but still prints the others
            return 1, f"aaa {stamp(5)}\nbbb {stamp(runner.STALE_AFTER_SECONDS + 60)}\nccc {stamp(400)}\nddd not-a-date\n"
        return 0, ""
    monkeypatch.setattr(runner, "_docker", fake_docker)
    runner.sweep_stale_containers()
    assert runner.STALE_AFTER_SECONDS >= 2 * 300   # well past the longest job time limit (300 s, the speed test)
    assert [c for c in calls if c[0] == "rm"] == [["rm", "-f", "bbb"]]
    assert calls[0] == ["ps", "-aq", "--filter", "label=evidence-lab=1"]
    calls.clear()
    monkeypatch.setattr(runner, "_docker", lambda args, timeout: (calls.append(list(args)) or (0, "") if args[0] != "ps" else (0, "aaa\n")))
    runner.sweep_stale_containers()   # nothing readable about it: left alone
    assert not [c for c in calls if c[0] == "rm"]


def test_settings_defaults_and_environment(monkeypatch, tmp_path):
    plain = Settings(data_dir=tmp_path, demo_tls_port=8443)
    assert (plain.max_jobs, plain.force_mode, plain.speed_rounds, plain.speed_repeats) == (4, None, 40, 5)
    monkeypatch.setenv("EVIDENCE_LAB_MAX_JOBS", "2")
    monkeypatch.setenv("EVIDENCE_LAB_MODE", "Demo")
    monkeypatch.setenv("EVIDENCE_LAB_SPEED_ROUNDS", "5")
    loaded = load_settings(tmp_path, 8443)
    assert (loaded.max_jobs, loaded.force_mode, loaded.speed_rounds) == (2, "demo", 5)
    for name, value in (("EVIDENCE_LAB_MAX_JOBS", "0"), ("EVIDENCE_LAB_MAX_JOBS", "many"), ("EVIDENCE_LAB_MODE", "turbo"),
                        ("EVIDENCE_LAB_SPEED_ROUNDS", "1")):
        monkeypatch.setenv(name, value)
        with pytest.raises(SystemExit):
            load_settings(tmp_path, 8443)
        monkeypatch.delenv(name)

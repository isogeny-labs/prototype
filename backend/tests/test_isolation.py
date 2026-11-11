"""Isolated mode, with real containers. Skipped with a clear message when Docker is not running or our image
has not been prepared (cd backend && .venv/bin/python -m app.prepare)."""
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from app import runner, vectors
from app.config import COMPONENTS_DIR, REPO_ROOT, Settings

PROBE = r'''
import json, os, socket, subprocess, sys
out = {"uid": os.getuid(), "gid": os.getgid(), "cwd": os.getcwd()}

def can_write(path):
    try:
        with open(path, "w") as handle:
            handle.write("x")
        return True
    except OSError:
        return False

out["write"] = {p: can_write(p) for p in ("/scratch/ok.txt", "/probe.txt", "/tmp/probe.txt", "/opt/evidence-lab/components/probe.txt",
                                          "/opt/evidence-lab/components/acme-sign-1.4.3/acme_sign.py", "/etc/probe.txt",
                                          "/home/probe.txt", "/var/tmp/probe.txt", "/dev/shm/probe.txt")}
out["interfaces"] = sorted(os.listdir("/sys/class/net"))
def can_connect(address):
    try:
        socket.create_connection(address, timeout=2).close()
        return True
    except OSError:
        return False
out["connect"] = {"1.1.1.1:443": can_connect(("1.1.1.1", 443)), "host gateway": can_connect(("172.17.0.1", 22)),
                  "name lookup": can_connect(("example.com", 443))}
out["docker_socket"] = [p for p in ("/var/run/docker.sock", "/run/docker.sock") if os.path.exists(p)]
out["exists"] = {p: os.path.exists(p) for p in json.loads(sys.argv[1])}
found, private_markers = [], []
for folder, _, names in os.walk("/"):
    if folder.startswith(("/proc", "/sys", "/dev")):
        continue
    for name in names:
        full = os.path.join(folder, name)
        low = name.lower()
        if low.endswith((".sqlite3", ".sqlite", ".db")) or "signing-key" in low or "evidence-lab.sqlite" in low:
            found.append(full)
        if low.endswith((".pem", ".key")):
            if folder.startswith("/opt/evidence-lab"):
                found.append(full)
            try:
                with open(full, "rb") as handle:
                    if b"PRIVATE KEY" in handle.read():
                        private_markers.append(full)
            except OSError:
                pass
out["found"], out["private_markers"] = found, private_markers
out["image_files"] = sorted(os.path.relpath(os.path.join(f, n), "/opt/evidence-lab/components")
                            for f, _, ns in os.walk("/opt/evidence-lab/components") for n in ns)
out["env"] = sorted(os.environ)
with open("/proc/self/status") as handle:
    status = dict(line.split(":", 1) for line in handle.read().splitlines() if ":" in line)
out["caps"] = {k: status[k].strip() for k in ("CapEff", "CapPrm", "CapBnd")}
out["no_new_privs"] = status.get("NoNewPrivs", "").strip()
def first_readable(*paths):
    for path in paths:
        try:
            with open(path) as handle:
                return handle.read().strip()
        except OSError:
            pass
    return None
out["memory_max"] = first_readable("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes")
out["pids_max"] = first_readable("/sys/fs/cgroup/pids.max", "/sys/fs/cgroup/pids/pids.max")
print(json.dumps(out))
'''


def in_container(mode, *command, timeout=60):
    """Run something else inside a container started with the runner's own fixed command line."""
    argv = runner.ComponentRunner(mode)._container_argv("evlab-" + os.urandom(6).hex())
    assert tuple(argv[-len(runner.CONTAINER_COMMAND):]) == runner.CONTAINER_COMMAND
    argv = argv[:-len(runner.CONTAINER_COMMAND)] + list(command)
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)


def our_containers() -> list[str]:
    rc, out = runner._docker(["ps", "-a", "--filter", "label=evidence-lab=1", "--format", "{{.Names}}"], 10)
    assert rc == 0
    return out.split()


@pytest.fixture(scope="module")
def probe(docker_ready, tmp_path_factory):
    """One look around from inside the container, with a pretend host data folder that must stay invisible."""
    data_dir = tmp_path_factory.mktemp("host-data")
    (data_dir / "evidence-lab.sqlite3").write_text("pretend database")
    (data_dir / "evidence-signing-key.pem").write_text("pretend signing key")
    os.chmod(data_dir / "evidence-signing-key.pem", 0o600)
    host_paths = [str(data_dir), str(data_dir / "evidence-lab.sqlite3"), str(data_dir / "evidence-signing-key.pem"),
                  str(REPO_ROOT), str(REPO_ROOT / "data"), str(REPO_ROOT / "backend"), str(REPO_ROOT / "demo" / "expected.json"),
                  str(COMPONENTS_DIR), str(REPO_ROOT.parent)]
    done = in_container(docker_ready, "python", "-I", "-c", PROBE, json.dumps(host_paths))
    assert done.returncode == 0, done.stderr[-500:]
    return json.loads(done.stdout)


def test_container_has_no_network(probe):
    assert probe["interfaces"] == ["lo"]
    assert probe["connect"] == {"1.1.1.1:443": False, "host gateway": False, "name lookup": False}


def test_container_runs_as_nobody_with_no_privileges(probe):
    assert (probe["uid"], probe["gid"], probe["cwd"]) == (65534, 65534, "/scratch")
    assert set(probe["caps"].values()) == {"0000000000000000"} and probe["no_new_privs"] == "1"
    assert probe["memory_max"] == str(256 * 1024 * 1024) and probe["pids_max"] == "64"


def test_container_is_read_only_except_the_scratch_folder(probe):
    assert probe["write"].pop("/scratch/ok.txt") is True
    assert set(probe["write"].values()) == {False}, probe["write"]


def test_scratch_folder_cannot_run_programs(docker_ready):
    script = "cp /bin/busybox /scratch/tool && chmod +x /scratch/tool && /scratch/tool true; echo rc=$?"
    done = in_container(docker_ready, "sh", "-c", script)
    assert "rc=126" in done.stdout or "ermission denied" in done.stderr


def test_container_cannot_see_the_host_database_signing_key_or_docker_socket(probe):
    assert probe["docker_socket"] == []
    assert set(probe["exists"].values()) == {False}, probe["exists"]
    assert probe["found"] == [] and probe["private_markers"] == []
    assert not any(name.upper().startswith(("DOCKER", "EVIDENCE", "HOME_")) or "SECRET" in name.upper() or "TOKEN" in name.upper()
                   for name in probe["env"]), probe["env"]


def test_image_holds_only_the_component_files(probe):
    expected = sorted(p.relative_to(COMPONENTS_DIR).as_posix() for p in COMPONENTS_DIR.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts and p.name not in ("Dockerfile", ".dockerignore"))
    assert probe["image_files"] == expected
    assert expected == ["acme-sign-1.4.2/acme_sign.py", "acme-sign-1.4.3/acme_sign.py", "controls/accept_all.py",
                        "controls/slow.py", "harness/driver.py"]


def test_runner_starts_exactly_the_fixed_command_and_cannot_be_asked_for_more(docker_ready, monkeypatch):
    seen = []
    real_popen = subprocess.Popen

    def spy(argv, **kw):
        seen.append(list(argv))
        return real_popen(argv, **kw)
    monkeypatch.setattr(runner.subprocess, "Popen", spy)
    job = {"op": "call", "subject": "acme-sign-1.4.3", "command": "info", "input": {}, "network": "host",
           "volumes": ["/:/host"], "privileged": True, "image": "alpine", "user": "0", "flags": ["--network", "host"]}
    result = runner.ComponentRunner(docker_ready).run_job(job)
    assert result.ok and result.mode == "isolated" and result.lines[0]["out"]["version"] == "1.4.3"
    (argv,), name = seen, seen[0][3]
    assert name.startswith("evlab-") and len(name) == 18
    assert argv == ["docker", "run", "--name", name, *runner.DOCKER_RUN_FLAGS, docker_ready.components_image,
                    *runner.CONTAINER_COMMAND]
    assert "host" not in argv and "-v" not in argv and "--privileged" not in argv
    assert "docker run" in result.command and "--network none" in result.command
    assert name not in our_containers()  # removed when it finished


def test_same_3_of_484_result_as_demo_mode(docker_ready):
    vector_set = vectors.load_wycheproof("ecdsa_p256")
    cases = [{"id": c.id, "public_key": c.public_key, "message": c.message, "signature": c.signature} for c in vector_set.cases]
    result = runner.ComponentRunner(docker_ready).run_job(
        {"op": "verify_batch", "subjects": ["acme-sign-1.4.2", "acme-sign-1.4.3", "control-accept-all"], "cases": cases},
        time_limit=300)
    print(f"\n484 official cases x 3 subjects, isolated mode: {result.duration_ms} ms")
    assert result.ok and result.mode == "isolated" and len(result.lines) == 3 * 484, (result.problem, result.stderr_tail)

    def wrong(subject):
        got = {line["id"]: line["valid"] for line in result.lines if line["subject"] == subject}
        assert len(got) == 484 and all(isinstance(v, bool) for v in got.values())
        return [c.id for c in vector_set.cases if got[c.id] != (c.expected == "valid")]
    assert wrong("acme-sign-1.4.2") == ["168", "171", "364"]
    assert wrong("acme-sign-1.4.3") == []
    assert len(wrong("control-accept-all")) == 310


def test_bench_and_bad_signatures_work_in_the_container(docker_ready):
    run = runner.ComponentRunner(docker_ready)
    subjects = ["acme-sign-1.4.2", "control-slow:acme-sign-1.4.2"]
    bench = run.run_job({"op": "bench_rounds", "keygen_with": "acme-sign-1.4.2", "subjects": subjects, "rounds": 2,
                         "repeats": 3, "message": "aa"})
    assert bench.ok and [line.get("subject") for line in bench.lines[1:]] == subjects + subjects[::-1]
    assert all(line["out"]["all_verified"] and len(line["out"]["sign_ms"]) == 3 for line in bench.lines[1:])
    assert "private" not in json.dumps(bench.lines)
    vector_set = vectors.load_bad_signatures()
    cases = [{"id": c.id, "public_key": c.public_key, "message": c.message, "signature": c.signature} for c in vector_set.cases]
    result = run.run_job({"op": "verify_batch", "subjects": ["acme-sign-1.4.2", "acme-sign-1.4.3"], "cases": cases})
    assert result.ok
    for subject, expected_wrong in (("acme-sign-1.4.2", ["r0-s0", "s-plus-n"]), ("acme-sign-1.4.3", [])):
        got = {line["id"]: line["valid"] for line in result.lines if line["subject"] == subject}
        assert [c.id for c in vector_set.cases if got[c.id] != (c.expected == "valid")] == expected_wrong


def test_timeout_kills_and_removes_the_container(docker_ready, monkeypatch):
    monkeypatch.setattr(runner.secrets, "token_hex", lambda n: "7e57" * 3)
    job = {"op": "bench_rounds", "keygen_with": "acme-sign-1.4.2", "subjects": ["acme-sign-1.4.2"], "rounds": 50,
           "repeats": 1000, "message": ""}
    t0 = time.monotonic()
    result = runner.ComponentRunner(docker_ready).run_job(job, time_limit=3.0)
    assert not result.ok and result.problem == runner.PROBLEM_TIMEOUT and time.monotonic() - t0 < 30
    assert "evlab-7e577e577e57" not in our_containers()


def test_sweep_removes_only_old_leftover_containers(docker_ready, monkeypatch):
    argv = runner.ComponentRunner(docker_ready)._container_argv("evlab-leftover0001")
    argv = [a for a in argv[:-len(runner.CONTAINER_COMMAND)] if a not in ("--rm", "-i")] + ["sleep", "300"]
    argv.insert(2, "-d")
    assert subprocess.run(argv, capture_output=True, text=True, timeout=30).returncode == 0
    try:
        assert "evlab-leftover0001" in our_containers()
        runner.sweep_stale_containers()           # what every start of the app does
        assert "evlab-leftover0001" in our_containers()   # too young to be a leftover: it may be another copy's running test
        # Once it is older than any run can be, it is removed. Only this one container is offered to the sweep,
        # so other copies' running tests on this computer are not touched by this test.
        real = runner._docker
        full_id = real(["inspect", "--format", "{{.Id}}", "evlab-leftover0001"], 10)[1].strip()
        only_ours = lambda args, timeout: (0, full_id + "\n") if args[:2] == ["ps", "-aq"] else real(args, timeout)  # noqa: E731
        monkeypatch.setattr(runner, "_docker", only_ours)
        runner.sweep_stale_containers(older_than=0)
        monkeypatch.setattr(runner, "_docker", real)
        assert "evlab-leftover0001" not in our_containers()
    finally:
        subprocess.run(["docker", "rm", "-f", "evlab-leftover0001"], capture_output=True, timeout=30)


def test_a_missing_image_is_an_error_not_a_download_and_not_a_local_run(docker_ready, tmp_path, monkeypatch):
    marker = tmp_path / "ran"
    stand_in = tmp_path / "driver.py"
    stand_in.write_text(f"open({str(marker)!r}, 'w').write('x')\n")
    monkeypatch.setattr(runner, "LOCAL_DRIVER", stand_in)
    mode = runner.ModeInfo("isolated", runner.ISOLATED_LINE, None, True, "evidence-lab-components:0000000000000000", None)
    result = runner.ComponentRunner(mode).run_job({"op": "call", "subject": "acme-sign-1.4.2", "command": "info", "input": {}})
    assert not result.ok and result.problem == runner.PROBLEM_ISOLATED and result.mode == "isolated"
    assert not marker.exists() and not runner.image_present("evidence-lab-components:0000000000000000")


def test_detected_mode_is_isolated_with_the_prepared_image(docker_ready, tmp_path):
    assert docker_ready.name == "isolated" and docker_ready.components_image == runner.components_image_tag()
    assert docker_ready.line == "Isolated mode: our demo software runs in a locked-down container with no network."
    forced = runner.detect_mode(Settings(data_dir=tmp_path, demo_tls_port=1, force_mode="demo"))
    assert forced.name == "demo" and forced.docker_running is True

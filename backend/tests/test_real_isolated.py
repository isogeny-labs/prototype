"""Real libraries (phase 4c) at the level of the container runner.

The first two tests need no Docker: a real library never runs as a local program, and never without its own image.
The rest start the prepared real-library images and are skipped with a message when Docker is not running or the
image of the family they need has not been prepared (cd backend && .venv/bin/python -m app.prepare)."""
import json
import os
import subprocess

import pytest

from app import real_libraries, runner, vectors

SUBJECTS = [("openjdk-17.0.2", "openjdk", "17.0.2", "java"), ("openjdk-17.0.3", "openjdk", "17.0.3", "java"),
            ("python-ecdsa-0.13.2", "python-ecdsa", "0.13.2", "python-ecdsa"), ("python-ecdsa-0.13.3", "python-ecdsa", "0.13.3", "python-ecdsa"),
            ("elliptic-6.5.6", "elliptic", "6.5.6", "elliptic"), ("elliptic-6.5.7", "elliptic", "6.5.7", "elliptic"),
            ("openssl-3.5.9", "openssl", "3.5.9", "openssl")]


def info_job(subject: str) -> dict:
    return {"op": "call", "subject": subject, "command": "info", "input": {}}


def need(mode, *families: str) -> None:
    """Skip with a clear message when the image of a family this test needs is not prepared."""
    missing = [family for family in families if not mode.real_images.get(family)]
    if missing:
        pytest.skip(f"Skipped: the real-library image for {', '.join(missing)} is not prepared "
                    "(run: cd backend && .venv/bin/python -m app.prepare).")


def spy_on_processes(monkeypatch) -> list[list[str]]:
    """Record every program the runner starts (and still start it). A test asserts on the list afterwards."""
    started, real_popen = [], subprocess.Popen

    def spy(argv, *args, **kw):
        started.append(list(argv))
        return real_popen(argv, *args, **kw)
    monkeypatch.setattr(runner.subprocess, "Popen", spy)
    return started


# ------------------------------------------------------------------ no Docker needed

def test_demo_mode_never_runs_a_real_library_as_a_local_program(monkeypatch):
    started = spy_on_processes(monkeypatch)
    mode = runner.ModeInfo("demo", "", None, False, None, None)
    result = runner.ComponentRunner(mode).run_job(info_job("openssl-3.5.9"), family="openssl")
    assert not result.ok and result.problem == runner.PROBLEM_REAL_NEEDS_ISOLATED and result.lines == [] and result.mode == "demo"
    assert started == [], f"a process was started for a real library in demo mode: {started}"


def test_an_isolated_mode_without_that_familys_image_does_not_run_it(monkeypatch):
    started = spy_on_processes(monkeypatch)
    for images in ({}, {"java": "evidence-lab-real-java:0000000000000000"}):   # none at all, or only another family's
        mode = runner.ModeInfo("isolated", runner.ISOLATED_LINE, None, True, "evidence-lab-components:0000000000000000", None, real_images=images)
        result = runner.ComponentRunner(mode).run_job(info_job("openssl-3.5.9"), family="openssl")
        assert not result.ok and result.problem == runner.PROBLEM_REAL_IMAGE_MISSING and result.lines == [] and result.mode == "isolated"
    assert started == [], f"a process was started although the image is missing: {started}"


# ------------------------------------------------------------------ real containers

@pytest.mark.parametrize("subject, name, version, family", SUBJECTS, ids=[s[0] for s in SUBJECTS])
def test_each_subject_says_what_it_is_from_the_library_itself(docker_ready, subject, name, version, family):
    need(docker_ready, family)
    assert real_libraries.family_of(name, version) == family
    result = runner.ComponentRunner(docker_ready).run_job(info_job(subject), family=family)
    assert result.ok and result.mode == "isolated", (result.problem, result.stderr_tail)
    assert len(result.lines) == 1 and not result.lines[0].get("error"), result.lines
    out = result.lines[0]["out"]
    assert str(out["name"]).casefold() == name.casefold() and out["version"] == version, out


def test_the_blank_signature_is_accepted_by_java_17_0_2_and_rejected_by_17_0_3(docker_ready):
    need(docker_ready, "java")
    vector_set = vectors.load_bad_signatures()
    cases = [{"id": c.id, "public_key": c.public_key, "message": c.message, "signature": c.signature} for c in vector_set.cases if c.id == "r0-s0"]
    assert len(cases) == 1, "the bad-signature list has no case r0-s0"
    result = runner.ComponentRunner(docker_ready).run_job(
        {"op": "verify_batch", "subjects": ["openjdk-17.0.2", "openjdk-17.0.3"], "cases": cases}, time_limit=120, family="java")
    assert result.ok, (result.problem, result.stderr_tail)
    answers = {line["subject"]: line["valid"] for line in result.lines if line["id"] == "r0-s0"}
    assert answers == {"openjdk-17.0.2": True, "openjdk-17.0.3": False}, f"(CVE-2022-21449) the blank signature: {answers}"


def test_a_subject_of_another_familys_image_is_refused_and_nothing_runs(docker_ready):
    need(docker_ready, "openssl")
    result = runner.ComponentRunner(docker_ready).run_job(info_job("openjdk-17.0.2"), family="openssl")
    assert not result.ok and result.lines == []
    assert result.problem is not None and result.problem.startswith(runner.PROBLEM_REFUSED_PREFIX), result.problem


def test_a_real_library_runs_with_the_same_fixed_lock_down_as_our_demo_components(docker_ready, monkeypatch):
    need(docker_ready, "openssl")
    image = docker_ready.real_images["openssl"]
    assert runner.ComponentRunner(docker_ready)._container_argv("x", "openssl") == [
        "docker", "run", "--name", "x", *runner.DOCKER_RUN_FLAGS, image, *runner.REAL_CONTAINER_COMMAND]
    assert "--network" in runner.DOCKER_RUN_FLAGS and "none" in runner.DOCKER_RUN_FLAGS and "--read-only" in runner.DOCKER_RUN_FLAGS
    started = spy_on_processes(monkeypatch)
    result = runner.ComponentRunner(docker_ready).run_job(info_job("openssl-3.5.9"), family="openssl")
    assert result.ok and len(started) == 1
    (argv,), name = started, started[0][3]
    assert name.startswith("evlab-")
    assert argv == ["docker", "run", "--name", name, *runner.DOCKER_RUN_FLAGS, image, *runner.REAL_CONTAINER_COMMAND]
    assert "-v" not in argv and "--privileged" not in argv and "host" not in argv


PROBE = r'''
import json, os, socket
out = {"uid": os.getuid(), "cwd": os.getcwd()}

def can_write(path):
    try:
        with open(path, "w") as handle:
            handle.write("x")
        return True
    except OSError:
        return False

out["write"] = {p: can_write(p) for p in ("/scratch/ok.txt", "/probe.txt", "/tmp/probe.txt", "/etc/probe.txt", "/opt/probe.txt",
                                          "/opt/evidence-lab/real/probe.txt", "/usr/local/probe.txt", "/home/probe.txt")}
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
print(json.dumps(out))
'''


def test_inside_a_real_library_image_there_is_no_network_and_the_files_are_read_only(docker_ready):
    need(docker_ready, "openssl")
    argv = runner.ComponentRunner(docker_ready)._container_argv("evlab-" + os.urandom(6).hex(), "openssl")
    assert tuple(argv[-len(runner.REAL_CONTAINER_COMMAND):]) == runner.REAL_CONTAINER_COMMAND
    argv = argv[:-len(runner.REAL_CONTAINER_COMMAND)] + ["python", "-I", "-c", PROBE]   # the same container, another command
    done = subprocess.run(argv, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr[-500:]
    seen = json.loads(done.stdout)
    assert seen["interfaces"] == ["lo"]
    assert seen["connect"] == {"1.1.1.1:443": False, "host gateway": False, "name lookup": False}
    assert (seen["uid"], seen["cwd"]) == (65534, "/scratch")
    assert seen["write"].pop("/scratch/ok.txt") is True
    assert set(seen["write"].values()) == {False}, seen["write"]
    assert seen["docker_socket"] == []

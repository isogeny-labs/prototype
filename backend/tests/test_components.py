import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from app import components
from app.compare import COULDNT, FALSE, TRUE
from app.components import WITHHELD, lookup, run_component, verify_software_claim
from app.config import DEMO_DIR

ACME = DEMO_DIR / "components" / "acme-sign-1.4.2" / "acme_sign.py"
ACME_143 = DEMO_DIR / "components" / "acme-sign-1.4.3" / "acme_sign.py"
CONTROLS = DEMO_DIR / "components" / "controls"


def load_acme(path=ACME):
    spec = importlib.util.spec_from_file_location("acme_sign_" + path.parent.name.replace(".", "").replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ registry

def test_registry_finds_only_exact_demo_components():
    assert lookup("acme-sign", "1.4.2") == ACME and ACME.is_file()
    assert lookup("acme-sign", "1.4.3") == ACME_143 and ACME_143.is_file()  # phase 2: the corrected demo version
    assert components.VERSIONS == {"acme-sign": ["1.4.2", "1.4.3"]}
    assert components.component_key("acme-sign", "1.4.3") == "acme-sign-1.4.3"
    with pytest.raises(ValueError):
        components.component_key("acme-sign", "../1.4.3")


@pytest.mark.parametrize("name,version", [
    ("acme-sign", "1.4.4"), ("acme-sign", "9.9.9"), ("acme-sign", ""), ("Acme-Sign", "1.4.2"), ("acme-sign ", "1.4.2"),
    ("../acme-sign", "1.4.2"), ("acme-sign", "../1.4.2"), ("../../etc/passwd", "1"), ("acme-sign/../acme-sign", "1.4.2"),
    ("acme-sign-1.4.2", ""), ("/bin/sh", "1"), ("other-tool", "1.0"), (None, None), (["acme-sign"], "1.4.2"), ("", ""),
])
def test_registry_rejects_everything_else(name, version):
    assert lookup(name, version) is None


def test_runner_only_accepts_the_four_commands():
    with pytest.raises(ValueError):
        run_component(ACME, "info; rm -rf /")


def test_runner_uses_argument_list_no_shell_time_limit_and_minimal_environment(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen.update(argv=argv, **kw)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "do-not-leak")
    monkeypatch.setattr(components.subprocess, "run", fake_run)
    run_component(ACME, "info")
    assert seen["argv"] == [sys.executable, "-I", "-B", str(ACME), "info"]
    assert seen["shell"] is False and seen["timeout"] == components.TIME_LIMIT_SECONDS
    assert "SUPER_SECRET_TOKEN" not in seen["env"] and set(seen["env"]) == {"PATH", "LANG", "PYTHONIOENCODING"}


def test_runner_time_limit(tmp_path):
    slow = tmp_path / "slow.py"
    slow.write_text("import time\ntime.sleep(30)\n")
    run = run_component(slow, "info", time_limit=0.5)
    assert not run.ok and "did not finish" in run.problem


# ------------------------------------------------------------------ acme-sign 1.4.2 itself

def test_component_is_standalone_and_marked_as_deliberately_flawed():
    source = ACME.read_text()
    assert "DELIBERATELY FLAWED" in source.split('"""')[1]
    imports = {line.split()[1].split(".")[0] for line in source.splitlines() if line.startswith(("import ", "from "))}
    assert imports <= {"hashlib", "hmac", "json", "secrets", "sys", "time"}  # standard library only, never the app


def test_info_command():
    run = run_component(ACME, "info")
    assert run.ok and (run.data["name"], run.data["version"], run.data["algorithm"]) == ("acme-sign", "1.4.2", "ECDSA P-256")


def test_bad_command_and_bad_input_do_not_crash_or_echo_input():
    done = subprocess.run([sys.executable, "-I", str(ACME), "explode"], input="{}", capture_output=True, text=True, timeout=20)
    assert done.returncode == 2 and "usage" in json.loads(done.stdout)["error"]
    run = run_component(ACME, "sign", {"private_key": "zz-not-hex-zz", "message": "00"})
    assert not run.ok and "zz-not-hex-zz" not in run.stdout


def test_50_random_keys_and_messages_round_trip_and_verify_with_pyca():
    acme = load_acme()
    for i in range(50):
        keys = acme.cmd_keygen({})
        message = os.urandom(i * 7 % 200)
        sig = acme.cmd_sign({"private_key": keys["private_key"], "message": message.hex()})["signature"]
        assert acme.cmd_verify({"public_key": keys["public_key"], "message": message.hex(), "signature": sig}) == {"valid": True}
        public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(keys["public_key"]))
        public.verify(bytes.fromhex(sig), message, ec.ECDSA(hashes.SHA256()))  # raises if not a real P-256 signature
        # ordinary bad signatures are still rejected
        other = (message + b"x").hex()
        assert acme.cmd_verify({"public_key": keys["public_key"], "message": other, "signature": sig}) == {"valid": False}


def test_component_also_verifies_signatures_made_by_pyca():
    acme = load_acme()
    for _ in range(10):
        key = ec.generate_private_key(ec.SECP256R1())
        from cryptography.hazmat.primitives import serialization
        public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        message = os.urandom(40)
        sig = key.sign(message, ec.ECDSA(hashes.SHA256()))
        assert acme.cmd_verify({"public_key": public.hex(), "message": message.hex(), "signature": sig.hex()})["valid"]


def test_planted_bug_is_present_in_1_4_2():
    """The demo depends on this flaw (same kind as CVE-2022-21449). It is a job for the phase 2 tests to
    catch it; the Verify step does not try this case."""
    acme = load_acme()
    keys = acme.cmd_keygen({})
    zero = "3006020100020100"  # DER for r = 0, s = 0
    assert acme.cmd_verify({"public_key": keys["public_key"], "message": b"anything".hex(), "signature": zero})["valid"]


# ------------------------------------------------------------------ the Verify step for a software claim

def test_true_for_the_real_claim_and_evidence_is_complete_and_redacted(monkeypatch):
    real, private = run_component, []

    def spy(path, command, payload=None, **kw):
        run = real(path, command, payload, **kw)
        if command == "keygen":
            private.append(run.data["private_key"])
        return run
    monkeypatch.setattr(components, "run_component", spy)
    res = verify_software_claim(ACME, "acme-sign", "1.4.2", "ECDSA P-256")
    assert res["result"] == TRUE and res["reason"] is None
    assert [e["title"].split("(")[-1].rstrip(")") for e in res["evidence"][:4]] == ["info", "keygen", "sign", "verify"]
    assert res["evidence"][4]["tool"] == "cryptography (pyca)" and res["evidence"][4]["output"].startswith("OK")
    text = json.dumps(res)
    assert len(private) == 1 and len(private[0]) == 64 and private[0] not in text
    assert text.count(WITHHELD) >= 2  # keygen output and sign input
    assert "3006020100020100" not in text  # no r = 0 / s = 0 case in Verify
    for item in res["evidence"]:
        assert set(item) == {"title", "command", "output", "started_at", "duration_ms", "tool", "tool_version"}


@pytest.mark.parametrize("name,version,algorithm,word", [
    ("acme-sign", "1.4.3", "ECDSA P-256", "version"),
    ("acme-sign", "1.4.2", "Ed25519", "algorithm"),
    ("acme-sign", "1.4.2", "ECDSA P-384", "algorithm"),
    ("acme-signer", "1.4.2", "ECDSA P-256", "name"),
])
def test_wrong_name_version_or_algorithm_claim_is_false(name, version, algorithm, word):
    res = verify_software_claim(ACME, name, version, algorithm)
    assert res["result"] == FALSE and word in res["found"]
    assert len(res["evidence"]) == 1  # decided from info alone; nothing was signed


def fake_component(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "fake.py"
    path.write_text("import json, sys\ncmd = sys.argv[1]\nreq = json.loads(sys.stdin.read() or '{}')\n"
                    "INFO = {'name': 'acme-sign', 'version': '1.4.2', 'algorithm': 'ECDSA P-256'}\n" + body)
    return path


def test_component_that_lies_about_its_algorithm_is_false(tmp_path):
    """Says ECDSA P-256 in info, but its 'signature' is not one: the independent check catches it."""
    path = fake_component(tmp_path, f"""
import importlib.util
spec = importlib.util.spec_from_file_location('real', {str(ACME)!r}); real = importlib.util.module_from_spec(spec); spec.loader.exec_module(real)
if cmd == 'info': print(json.dumps(INFO))
elif cmd == 'keygen': print(json.dumps(real.cmd_keygen(req)))
elif cmd == 'sign': print(json.dumps({{'signature': '3006020101020101'}}))
elif cmd == 'verify': print(json.dumps({{'valid': True}}))
""")
    res = verify_software_claim(path, "acme-sign", "1.4.2", "ECDSA P-256")
    assert res["result"] == FALSE and "independent check failed" in res["found"]


def test_broken_or_silent_component_is_couldnt_check(tmp_path):
    crash = fake_component(tmp_path, "raise SystemExit(3)\n")
    res = verify_software_claim(crash, "acme-sign", "1.4.2", "ECDSA P-256")
    assert res["result"] == COULDNT and "info" in res["reason"]
    half = fake_component(tmp_path, "print(json.dumps(INFO) if cmd == 'info' else 'not json')\n")
    res = verify_software_claim(half, "acme-sign", "1.4.2", "ECDSA P-256")
    assert res["result"] == COULDNT and "keygen" in res["reason"]


# ------------------------------------------------------------------ the Verify step in isolated mode

def isolated_runner(tmp_path, available=True):
    """A runner whose mode is isolated. With available=True its jobs are carried out by the real harness (as a
    local process here, so the test needs no Docker); what matters is which path Verify takes."""
    from app import runner
    from app.config import Settings
    inner = runner.ComponentRunner(runner.detect_mode(Settings(data_dir=tmp_path, demo_tls_port=1, force_mode="demo")))
    image = "evidence-lab-components:test" if available else None
    mode = runner.ModeInfo("isolated", runner.ISOLATED_LINE, None, available, image, None)

    class Recording(runner.ComponentRunner):
        jobs: list = []

        def run_job(self, job, **kw):
            self.jobs.append(job)
            return inner.run_job(job, **kw) if available else super().run_job(job, **kw)
    return Recording(mode)


def no_local_runs(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the component was run as a local process in isolated mode")
    monkeypatch.setattr(components, "run_component", refuse)


def test_isolated_mode_checks_the_claim_through_the_runner_only(tmp_path, monkeypatch):
    no_local_runs(monkeypatch)
    run = isolated_runner(tmp_path)
    res = verify_software_claim(ACME, "acme-sign", "1.4.2", "ECDSA P-256", runner=run)
    assert res["result"] == TRUE and res["reason"] is None
    assert [j["op"] for j in run.jobs] == ["call", "roundtrip"] and {j["subject"] for j in run.jobs} == {"acme-sign-1.4.2"}
    assert [e["title"].split("(")[-1].rstrip(")") for e in res["evidence"][:4]] == ["info", "keygen", "sign", "verify"]
    assert all(e["tool"] == components.ISOLATED_TOOL and "not isolated" not in e["tool"] for e in res["evidence"][:4])
    assert res["evidence"][4]["tool"] == "cryptography (pyca)" and res["evidence"][4]["output"].startswith("OK")
    text = json.dumps(res)
    assert WITHHELD in text and not re.search(r'"private_key\\?": \\?"[0-9a-f]{64}', text)
    for item in res["evidence"]:
        assert set(item) == {"title", "command", "output", "started_at", "duration_ms", "tool", "tool_version"}
    # decided from info alone when the claim does not match; nothing is signed
    run.jobs.clear()
    res = verify_software_claim(ACME, "acme-sign", "1.4.2", "Ed25519", runner=run)
    assert res["result"] == FALSE and "algorithm" in res["found"] and [j["op"] for j in run.jobs] == ["call"]
    # a file that is not one of our registered components is never handed to the runner
    run.jobs.clear()
    res = verify_software_claim(tmp_path / "other.py", "acme-sign", "1.4.2", "ECDSA P-256", runner=run)
    assert res["result"] == COULDNT and run.jobs == [] and res["evidence"] == []


def test_isolated_mode_that_is_not_available_is_couldnt_check_and_nothing_runs(tmp_path, monkeypatch):
    from app import runner
    no_local_runs(monkeypatch)
    marker = tmp_path / "ran"
    stand_in = tmp_path / "driver.py"
    stand_in.write_text(f"open({str(marker)!r}, 'w').write('x')\n")
    monkeypatch.setattr(runner, "LOCAL_DRIVER", stand_in)
    res = verify_software_claim(ACME, "acme-sign", "1.4.2", "ECDSA P-256", runner=isolated_runner(tmp_path, available=False))
    assert res["result"] == COULDNT and res["evidence"] == [] and not marker.exists()
    assert res["reason"] == "Isolated mode is not available on this computer, so the component was not run."


def test_demo_mode_runner_keeps_the_local_check_unchanged(tmp_path):
    from app import runner
    from app.config import Settings
    demo = runner.ComponentRunner(runner.detect_mode(Settings(data_dir=tmp_path, demo_tls_port=1, force_mode="demo")))
    res = verify_software_claim(ACME, "acme-sign", "1.4.2", "ECDSA P-256", runner=demo)
    assert res["result"] == TRUE
    assert all(e["tool"] == "Demo component, run by Evidence Lab in demo mode (not isolated)" for e in res["evidence"][:4])


# ------------------------------------------------------------------ phase 2: strict format, 1.4.3, bench, controls

N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551


def cli(path_args, command, payload=None):
    done = subprocess.run([sys.executable, "-I", "-B", *map(str, path_args), command], input=json.dumps(payload or {}),
                          capture_output=True, text=True, timeout=60)
    return done.returncode, json.loads(done.stdout)


def der_int(raw: bytes) -> bytes:
    return b"\x02" + bytes([len(raw)]) + raw


def der(r_raw: bytes, s_raw: bytes) -> str:
    body = der_int(r_raw) + der_int(s_raw)
    return (b"\x30" + bytes([len(body)]) + body).hex()


def minimal(value: int) -> bytes:
    return value.to_bytes((value.bit_length() + 8) // 8 or 1, "big")


@pytest.fixture(scope="module")
def signed():
    """One genuine signature made by 1.4.3 from a throwaway test key: (public key, message, r, s)."""
    acme = load_acme(ACME_143)
    keys = acme.cmd_keygen({})
    message = b"phase 2 test message".hex()
    r, s = acme.der_decode(bytes.fromhex(acme.cmd_sign({"private_key": keys["private_key"], "message": message})["signature"]))
    return keys["public_key"], message, r, s


@pytest.mark.parametrize("path,version", [(ACME, "1.4.2"), (ACME_143, "1.4.3")])
def test_five_commands_in_and_out(path, version):
    rc, info = cli([path], "info")
    assert rc == 0 and info == {
        "name": "acme-sign", "version": version, "algorithm": "ECDSA P-256", "hash": "SHA-256", "signature_format": "DER",
        "public_key_format": "uncompressed point, hex (04 || X || Y)", "commands": ["keygen", "sign", "verify", "info", "bench"]}
    rc, keys = cli([path], "keygen")
    assert rc == 0 and set(keys) == {"private_key", "public_key"} and len(keys["private_key"]) == 64
    assert len(keys["public_key"]) == 130 and keys["public_key"].startswith("04")
    rc, signed_out = cli([path], "sign", {"private_key": keys["private_key"], "message": "616263"})
    assert rc == 0 and set(signed_out) == {"signature"}
    verify_in = {"public_key": keys["public_key"], "message": "616263", "signature": signed_out["signature"]}
    assert cli([path], "verify", verify_in) == (0, {"valid": True})
    assert cli([path], "verify", {**verify_in, "message": "616264"}) == (0, {"valid": False})
    rc, bench = cli([path], "bench", {"repeats": 3, "message": "616263", "private_key": keys["private_key"]})
    assert rc == 0 and keys["private_key"] not in json.dumps(bench)
    rc, usage = cli([path], "explode")
    assert rc == 2 and "bench" in usage["error"]


@pytest.mark.parametrize("path", [ACME, ACME_143])
def test_bench_shape_counts_and_no_private_key(path):
    rc, out = cli([path], "bench", {"repeats": 7, "message": "00ff"})
    assert rc == 0 and set(out) == {"repeats", "warmups", "clock", "sign_ms", "verify_ms", "signature_bytes",
                                    "public_key_bytes", "all_verified"}
    assert (out["repeats"], out["warmups"], out["clock"], out["public_key_bytes"], out["all_verified"]) == (
        7, 2, "time.perf_counter", 65, True)
    assert len(out["sign_ms"]) == 7 and len(out["verify_ms"]) == 7 and 68 <= out["signature_bytes"] <= 72
    assert all(isinstance(v, float) and 0 < v < 5000 and round(v, 4) == v for v in out["sign_ms"] + out["verify_ms"])
    assert "private" not in json.dumps(out)
    for bad in ({"repeats": 0}, {"repeats": 1001}, {"repeats": "many"}, {"repeats": True}, {"message": "zz"},
                {"repeats": 1, "private_key": "00"}):
        rc, err = cli([path], "bench", bad)
        assert rc == 1 and set(err) == {"error"}


def test_1_4_3_differs_from_1_4_2_only_by_version_docstring_and_the_range_check():
    def body(path):
        source = path.read_text()
        return source.split('"""', 2)[2].splitlines()  # everything after the opening description
    old, new = body(ACME), body(ACME_143)
    assert len(old) == len(new)
    changed = [(a, b) for a, b in zip(old, new) if a != b]
    assert changed == [
        ('VERSION = "1.4.2"', 'VERSION = "1.4.3"'),
        ("    # PLANTED BUG (demo): a correct verifier rejects here unless 1 <= r < N and 1 <= s < N.",
         "    if not (1 <= r < N and 1 <= s < N):"),
        ("    # 1.4.2 skips that check.", '        return {"valid": False}'),
    ]
    assert "DELIBERATELY FLAWED" in ACME.read_text() and "DELIBERATELY FLAWED" not in ACME_143.read_text()


@pytest.mark.parametrize("path", [ACME, ACME_143])
def test_signature_format_is_strict_in_both_versions(path, signed):
    """Negative-looking and padded numbers, long-form lengths, wrong tags and stray bytes are all refused.
    This strictness is NOT the planted bug: 1.4.2 has it too."""
    acme = load_acme(path)
    public, message, r, s = signed

    def valid(signature_hex):
        return acme.cmd_verify({"public_key": public, "message": message, "signature": signature_hex})["valid"]

    good = der(minimal(r), minimal(s))
    assert valid(good) is True
    high = N - 1  # a 32-byte value whose top bit is set
    assert valid(der(minimal(r), high.to_bytes(32, "big"))) is False            # reads as negative: missing 00
    assert valid(der(r.to_bytes(32, "big") if r >> 255 else b"\x80" + r.to_bytes(32, "big")[1:], minimal(s))) is False
    assert valid(der(b"\x00" + minimal(r), minimal(s))) is False               # needless 00 in front
    assert valid(der(minimal(r), b"\x00" + minimal(s))) is False
    assert valid(der(b"\x00\x01", minimal(s))) is False
    body = der_int(minimal(r)) + der_int(minimal(s))
    assert valid((b"\x30\x81" + bytes([len(body)]) + body).hex()) is False        # long-form length
    assert valid((b"\x31" + bytes([len(body)]) + body).hex()) is False            # wrong tag
    assert valid(good + "00") is False and valid(good[:-2]) is False and valid("") is False
    assert valid(der(b"", minimal(s))) is False                                   # empty number


def test_range_check_is_the_one_difference_in_behaviour(signed):
    old, new = load_acme(ACME), load_acme(ACME_143)
    public, message, r, s = signed
    cases = {"r0-s0": der(b"\x00", b"\x00"), "s+n": der(minimal(r), minimal(s + N)), "r0-sn": der(b"\x00", minimal(N))}
    for name, signature in cases.items():
        request = {"public_key": public, "message": message, "signature": signature}
        assert old.cmd_verify(request) == {"valid": True}, name      # the planted bug
        assert new.cmd_verify(request) == {"valid": False}, name     # fixed
    for signature in (der(minimal(r), minimal(s)), der(minimal(r), b"\x00"), der(minimal(N), minimal(s)),
                      der(minimal(r + N), minimal(s))):
        request = {"public_key": public, "message": message, "signature": signature}
        assert old.cmd_verify(request) == new.cmd_verify(request)


def test_control_accept_all_says_yes_to_anything():
    path = CONTROLS / "accept_all.py"
    assert "DELIBERATELY BROKEN" in path.read_text().split('"""')[1]
    for payload in ({}, {"public_key": "not even hex", "message": 5, "signature": None},
                    {"public_key": "04" + "00" * 64, "message": "", "signature": "3006020100020100"}):
        assert cli([path], "verify", payload) == (0, {"valid": True})
    rc, info = cli([path], "info")
    assert rc == 0 and info["name"] == "control-accept-all" and "deliberately broken" in info["control"]
    rc, keys = cli([path], "keygen")
    assert rc == 0 and len(keys["public_key"]) == 130
    rc, bench = cli([path], "bench", {"repeats": 2})
    assert rc == 0 and len(bench["verify_ms"]) == 2 and bench["all_verified"] is True
    assert cli([path], "explode")[0] == 2


def test_control_slow_adds_about_three_milliseconds_to_sign_and_verify():
    import statistics
    path = CONTROLS / "slow.py"
    assert "DELIBERATELY SLOWED" in path.read_text().split('"""')[1]
    rc, info = cli([path, ACME], "info")
    assert rc == 0 and (info["name"], info["wraps"], info["delay_ms"]) == ("control-slow", "acme-sign 1.4.2", 6.0)
    key = load_acme().cmd_keygen({})["private_key"]
    request = {"repeats": 15, "message": "abcd", "private_key": key}
    rc, plain = cli([ACME], "bench", request)
    rc2, slow = cli([path, ACME], "bench", request)
    assert rc == 0 and rc2 == 0 and slow["all_verified"] is True and key not in json.dumps(slow)
    for op in ("sign_ms", "verify_ms"):
        assert len(slow[op]) == 15 and min(slow[op]) >= 6.0           # every single call carries the delay
        added = statistics.median(slow[op]) - statistics.median(plain[op])
        assert 3.0 < added < 12.0, (op, added)                        # about 6 ms, with room for a busy machine
    # it is the same component underneath: its answers are unchanged
    rc, keys = cli([path, ACME_143], "keygen")
    rc, signed_out = cli([path, ACME_143], "sign", {"private_key": keys["private_key"], "message": "aa"})
    assert cli([path, ACME_143], "verify", {"public_key": keys["public_key"], "message": "aa",
                                             "signature": signed_out["signature"]}) == (0, {"valid": True})
    assert cli([path, ACME_143], "verify", {"public_key": keys["public_key"], "message": "aa",
                                             "signature": "3006020100020100"}) == (0, {"valid": False})
    assert cli([path, ACME], "explode")[0] == 2 and cli([path, "/nonexistent/x.py"], "info")[0] == 2


def test_controls_and_harness_are_standard_library_only():
    for path in (CONTROLS / "accept_all.py", CONTROLS / "slow.py", DEMO_DIR / "components" / "harness" / "driver.py", ACME_143):
        imports = {line.split()[1].split(".")[0] for line in path.read_text().splitlines() if line.startswith(("import ", "from "))}
        assert imports <= {"hashlib", "hmac", "json", "secrets", "sys", "time", "os", "importlib", "subprocess", "concurrent"}, path


def test_redact_and_scrub_remove_private_keys_and_pem_blocks():
    pem = "-----BEGIN EC PRIVATE KEY-----\nMHcCAQEEIAbcd\n-----END EC PRIVATE KEY-----"
    value = {"private_key": "aa" * 32, "nested": [{"PrivateKey": "bb", "note": f"before {pem} after"}], "public_key": "04cc"}
    clean = components.scrub(value)
    assert clean == {"private_key": WITHHELD, "nested": [{"PrivateKey": WITHHELD, "note": f"before {WITHHELD} after"}],
                     "public_key": "04cc"}
    assert value["private_key"] == "aa" * 32  # a copy; the original is untouched
    text = components.redact(value, ["04cc"])
    assert "aa" * 32 not in text and "PRIVATE KEY" not in text and "MHcCAQEE" not in text and "04cc" not in text
    assert "PRIVATE KEY" not in components.redact("log line -----BEGIN PRIVATE KEY-----\nMIGH never closed")
    assert components.redact("plain text") == "plain text"

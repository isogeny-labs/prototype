import importlib.util
import json
import os
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


def load_acme():
    spec = importlib.util.spec_from_file_location("acme_sign_142", ACME)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------ registry

def test_registry_finds_only_exact_demo_components():
    assert lookup("acme-sign", "1.4.2") == ACME and ACME.is_file()


@pytest.mark.parametrize("name,version", [
    ("acme-sign", "1.4.3"), ("acme-sign", "9.9.9"), ("acme-sign", ""), ("Acme-Sign", "1.4.2"), ("acme-sign ", "1.4.2"),
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
    assert imports <= {"hashlib", "hmac", "json", "secrets", "sys"}  # standard library only, never the app


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

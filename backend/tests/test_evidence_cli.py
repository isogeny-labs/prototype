"""`python -m evidence verify file.json`: passes on a fresh file and fails on ANY change, however small."""
import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

import evidence
from app.canonical import canonical_bytes
from app.evidence_export import PUBLIC_KEY_FILE, ensure_signing_key, key_fingerprint, sign_envelope
from evidence import FAILED, SIGNER_NOT_CONFIRMED, VERIFIED, verify_bytes

BACKEND = Path(__file__).resolve().parents[1]


def small_file(data_dir: Path) -> tuple[bytes, str]:
    """A small but awkward evidence file: accents, escapes, floats, nesting, empty things."""
    public = ensure_signing_key(data_dir)
    evidence_part = {"schema": "isogeny.evidence/1", "signer_key_fingerprint": key_fingerprint(public),
                     "generated_at": "2026-11-11T01:58:10.000Z", "disclaimer": "café ≤ ±2.4% \U0001f512",
                     "text": "line one\nline \"two\"\ttab \\ slash \u001b end", "numbers": [0, -1, 7.0312, 1e-07, 1e+22, 12345678901234567890],
                     "tests": [{"spec_hash": "ab" * 32, "runs": [], "ok": True, "none": None, "empty": {}, "Mixed Case Key": "Value"}]}
    return sign_envelope(evidence_part, data_dir), public


def test_a_fresh_file_verifies(tmp_path):
    raw, public = small_file(tmp_path)
    outcome = verify_bytes(raw, public)
    assert outcome.ok and outcome.code == VERIFIED and outcome.message == "Evidence verified"
    assert outcome.fingerprint == json.loads(raw)["fingerprint"] and outcome.signer == key_fingerprint(public)


def test_every_single_byte_changed_fails_small_file(tmp_path):
    raw, public = small_file(tmp_path)
    assert 600 < len(raw) < 2000
    tried = 0
    for position in range(len(raw)):
        masks = [0x01, 0x80] + ([0x20] if chr(raw[position]).isalpha() else []) + ([0x02, 0x04, 0x08, 0x10, 0x40] if position % 7 == 0 else [])
        for mask in masks:
            changed = bytearray(raw)
            changed[position] ^= mask
            for trusted in (public, None):   # with or without a trusted key, a changed file is a failure, never "not confirmed"
                outcome = verify_bytes(bytes(changed), trusted)
                assert outcome.code == FAILED, f"byte {position} xor {mask:#04x} was not noticed"
                assert outcome.message.startswith("Evidence NOT verified: ")
            tried += 1
    assert tried > 2 * len(raw)
    for position in range(len(raw) + 1):   # one byte added or removed anywhere
        assert verify_bytes(raw[:position] + b" " + raw[position:], public).code == FAILED
        assert verify_bytes(raw[:position] + raw[position + 1:], public).code == FAILED or position == len(raw)


def test_a_broad_sample_of_bytes_changed_fails_real_file(demo_flow):
    made = demo_flow.lab.export_evidence(demo_flow.plan.id)
    raw = demo_flow.lab.evidence_file(made["id"], "json")[1]
    public = (demo_flow.lab.settings.data_dir / PUBLIC_KEY_FILE).read_text().strip()
    assert verify_bytes(raw, public).ok and len(raw) > 50_000
    step = max(1, len(raw) // 700)
    positions = sorted(set(range(0, len(raw), step)) | set(range(0, 250)) | set(range(len(raw) - 400, len(raw))))
    assert len(positions) > 1000
    for position in positions:
        for mask in [0x01] + ([0x20] if chr(raw[position]).isalpha() else []):
            changed = bytearray(raw)
            changed[position] ^= mask
            assert verify_bytes(bytes(changed), public).code == FAILED, f"byte {position} xor {mask:#04x} was not noticed"


def test_same_content_written_differently_fails(tmp_path):
    raw, public = small_file(tmp_path)
    envelope = json.loads(raw)
    same = lambda obj, **kw: json.dumps(obj, ensure_ascii=False, **kw).encode("utf-8")  # noqa: E731
    variants = {
        "newline at the end": raw + b"\n",
        "space at the start": b" " + raw,
        "spaces after separators": same(envelope, sort_keys=True),
        "pretty printed": same(envelope, sort_keys=True, indent=1),
        "keys in another order": same({k: envelope[k] for k in ("signature", "public_key", "fingerprint", "evidence")}, separators=(",", ":")),
        "non-ASCII escaped": json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("ascii"),
        "uppercase fingerprint": canonical_bytes({**envelope, "fingerprint": envelope["fingerprint"].upper()}),
        "uppercase signature": canonical_bytes({**envelope, "signature": envelope["signature"].upper()}),
        "uppercase public key": canonical_bytes({**envelope, "public_key": envelope["public_key"].upper()}),
        "a repeated key": raw[:-1] + b',"signature":"' + envelope["signature"].encode() + b'"}',
        "an extra part": canonical_bytes({**envelope, "extra": 1}),
        "a missing part": canonical_bytes({k: v for k, v in envelope.items() if k != "signature"}),
        "byte order mark": b"\xef\xbb\xbf" + raw,
        "two files glued together": raw + raw,
        "empty": b"", "not json": b"hello", "a list": b"[]", "not utf-8": b"\xff\xfe" + raw,
        "NaN inside": raw.replace(b"7.0312", b"NaN"),
        "short signature": canonical_bytes({**envelope, "signature": envelope["signature"][:-2]}),
        "wrong schema": sign_envelope({**envelope["evidence"], "schema": "something/else"}, tmp_path),
    }
    for name, data in variants.items():
        assert verify_bytes(data, public).code == FAILED, name
        assert verify_bytes(data, None).code == FAILED, name


def test_changed_evidence_with_a_recomputed_fingerprint_fails_on_the_signature(tmp_path):
    raw, public = small_file(tmp_path)
    envelope = json.loads(raw)
    envelope["evidence"]["text"] = "edited"
    envelope["fingerprint"] = __import__("hashlib").sha256(canonical_bytes(envelope["evidence"])).hexdigest()
    outcome = verify_bytes(canonical_bytes(envelope), public)
    assert outcome.code == FAILED and "signature is not valid" in outcome.message


def test_a_file_signed_again_with_another_key_fails(tmp_path):
    raw, public = small_file(tmp_path / "ours")
    other_public = ensure_signing_key(tmp_path / "theirs")
    assert other_public != public
    edited = {**json.loads(raw)["evidence"], "text": "edited by someone else"}
    # signed by the other key, still naming our key: the evidence and the signer disagree
    assert verify_bytes(sign_envelope(edited, tmp_path / "theirs"), public).code == FAILED
    # signed by the other key and naming it: self-consistent, but not the signer we trust
    forged = sign_envelope({**edited, "signer_key_fingerprint": key_fingerprint(other_public)}, tmp_path / "theirs")
    outcome = verify_bytes(forged, public)
    assert outcome.code == FAILED and "not by the key you trust" in outcome.message
    assert verify_bytes(forged, other_public).ok   # (it is a real file of that other app)
    # with no trusted key at all, the best it can get is "not confirmed", never a pass
    unknown = verify_bytes(forged, None)
    assert unknown.code == SIGNER_NOT_CONFIRMED and not unknown.ok
    assert unknown.message == "The file is consistent with itself, but the signer could not be confirmed."


def run_cli(*args, cwd=BACKEND, env_data_dir=None):
    env = {"PATH": "/usr/bin:/bin"}
    if env_data_dir is not None:
        env["EVIDENCE_LAB_DATA_DIR"] = str(env_data_dir)
    return subprocess.run([sys.executable, "-m", "evidence", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)


def test_the_command_line(tmp_path):
    data_dir = tmp_path / "data"
    raw, public = small_file(data_dir)
    good, bad = tmp_path / "evidence.json", tmp_path / "changed.json"
    good.write_bytes(raw)
    changed = bytearray(raw)
    changed[len(raw) // 2] ^= 0x01
    bad.write_bytes(bytes(changed))
    fingerprint = json.loads(raw)["fingerprint"]

    ok = run_cli("verify", str(good), "--data-dir", str(data_dir))
    assert ok.returncode == 0 and ok.stdout.startswith("Evidence verified\n") and fingerprint in ok.stdout, ok.stdout + ok.stderr
    assert key_fingerprint(public) in ok.stdout and "Signer confirmed" in ok.stdout
    assert run_cli("verify", str(good), env_data_dir=data_dir).returncode == 0          # the app's own data folder is the default
    assert run_cli("verify", str(good), "--public-key", public).returncode == 0
    assert run_cli("verify", str(good), "--public-key", str(data_dir / PUBLIC_KEY_FILE)).returncode == 0

    for args in (("verify", str(bad), "--data-dir", str(data_dir)), ("verify", str(bad), "--public-key", public),
                 ("verify", str(bad), "--data-dir", str(tmp_path / "empty"))):
        failed = run_cli(*args)
        assert failed.returncode == 1 and failed.stdout.startswith("Evidence NOT verified: "), failed.stdout + failed.stderr
        assert "Evidence verified" not in failed.stdout

    wrong_key = run_cli("verify", str(good), "--public-key", "00" * 32)
    assert wrong_key.returncode == 1 and "not by the key you trust" in wrong_key.stdout

    unknown = run_cli("verify", str(good), "--data-dir", str(tmp_path / "empty"))
    assert unknown.returncode == 2 and "Evidence verified" not in unknown.stdout
    assert unknown.stdout.startswith("The file is consistent with itself, but the signer could not be confirmed.\n")
    assert "This is not a pass." in unknown.stdout
    assert run_cli("verify", str(good), env_data_dir=tmp_path / "empty").returncode == 2

    for args in (("verify", str(tmp_path / "missing.json")), ("verify", str(good), "--public-key", "zz"), ("verify",), (), ("sign", str(good))):
        refused = run_cli(*args)
        assert refused.returncode == 1 and "Evidence verified" not in refused.stdout, args
    # the private key is never needed, read or shown by the checker
    assert "PRIVATE" not in ok.stdout + unknown.stdout


def test_the_checker_imports_almost_nothing_from_the_app():
    for name in ("__init__.py", "__main__.py"):
        tree = ast.parse((BACKEND / "evidence" / name).read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                modules.add(("." * node.level) + (node.module or ""))
        app_modules = {m for m in modules if m == "app" or m.startswith("app.")}
        assert app_modules <= {"app.canonical", "app.config"}, app_modules
        assert not {m for m in modules if m.split(".")[0] in ("subprocess", "pickle", "sqlalchemy", "fastapi", "requests", "socket")}
    assert evidence.SIGNING_CONTEXT == __import__("app.evidence_export").evidence_export.SIGNING_CONTEXT


@pytest.mark.parametrize("value", ["", "abc", "g" * 64, "A" * 63])
def test_bad_trusted_keys_are_not_keys(value, tmp_path):
    assert evidence.read_public_key(value) is None

"""The vendored official vectors and our fixed bad-signature cases: pinned by hash, read as data, and the
demo components give exactly the expected answers on them (through the real harness, in demo mode)."""
import json
import shutil
from pathlib import Path

import pytest

from app import reference, runner, vectors
from app.config import REPO_ROOT, VECTORS_DIR, Settings

ECDSA_SHA = "182db4f3e230f6f9fa9f800d2a614dede30284b8e8438bbfe1171905402e9332"
ED_SHA = "ea80ffebac085e21cb9d3e903e7fa2b448d96702da5b31f061d0b83b430b74b3"
COMMIT = "dab4ea2ed021eb633874959ca601004f3457d911"
SUBJECTS = ["acme-sign-1.4.2", "acme-sign-1.4.3", "control-accept-all"]


def as_cases(vector_set):
    return [{"id": c.id, "public_key": c.public_key, "message": c.message, "signature": c.signature} for c in vector_set.cases]


def wrong_ids(vector_set, lines, subject):
    """Case ids where the subject's yes/no differs from the published answer. Every case must have an answer."""
    got = {line["id"]: line["valid"] for line in lines if line["subject"] == subject}
    assert len(got) == len(vector_set.cases) and all(isinstance(v, bool) for v in got.values())
    return [c.id for c in vector_set.cases if got[c.id] != (c.expected == "valid")]


def demo_runner(tmp_path):
    mode = runner.detect_mode(Settings(data_dir=tmp_path, demo_tls_port=1, force_mode="demo"))
    assert mode.name == "demo"
    return runner.ComponentRunner(mode)


# ------------------------------------------------------------------ the files

def test_both_wycheproof_files_are_pinned_by_hash_and_commit():
    assert vectors.WYCHEPROOF["ecdsa_p256"]["sha256"] == ECDSA_SHA and vectors.WYCHEPROOF["ed25519"]["sha256"] == ED_SHA
    assert vectors.WYCHEPROOF_COMMIT == COMMIT and COMMIT in vectors.WYCHEPROOF_SOURCE_URL
    folder = VECTORS_DIR / "wycheproof"
    assert vectors.file_sha256(folder / "ecdsa_secp256r1_sha256_test.json") == ECDSA_SHA
    assert vectors.file_sha256(folder / "ed25519_test.json") == ED_SHA
    readme = (folder / "README.md").read_text()
    for needed in (ECDSA_SHA, ED_SHA, COMMIT, "https://github.com/C2SP/wycheproof", "Apache License 2.0"):
        assert needed in readme


def test_wycheproof_cases_load_as_data():
    ecdsa = vectors.load_wycheproof("ecdsa_p256")
    assert (ecdsa.name, ecdsa.sha256, len(ecdsa.cases)) == ("ecdsa_p256", ECDSA_SHA, 484) and COMMIT in ecdsa.source
    counts = {kind: sum(c.expected == kind for c in ecdsa.cases) for kind in ("valid", "invalid", "acceptable")}
    assert counts == {"valid": 174, "invalid": 310, "acceptable": 0}
    case = next(c for c in ecdsa.cases if c.id == "168")
    assert case.comment == "Signature with special case values r=0 and s=0" and case.expected == "invalid"
    assert case.signature == "3006020100020100" and case.flags == ("InvalidSignature",)
    assert all(len(c.public_key) == 130 and c.public_key.startswith("04") for c in ecdsa.cases)
    ed = vectors.load_wycheproof("ed25519")
    counts = {kind: sum(c.expected == kind for c in ed.cases) for kind in ("valid", "invalid", "acceptable")}
    assert len(ed.cases) == 210 and counts == {"valid": 117, "invalid": 64, "acceptable": 29}
    assert all(len(c.public_key) == 64 for c in ed.cases)
    # case numbers are per file: 168 in the Ed25519 file is an unrelated case
    assert "r=0" not in next(c for c in ed.cases if c.id == "168").comment


@pytest.mark.parametrize("which,relative", [("ecdsa_p256", "wycheproof/ecdsa_secp256r1_sha256_test.json"),
                                            ("ed25519", "wycheproof/ed25519_test.json"),
                                            ("bad", "bad-signatures/cases.json")])
def test_a_changed_or_missing_file_is_refused(tmp_path, monkeypatch, which, relative):
    copy = tmp_path / "vectors"
    shutil.copytree(VECTORS_DIR, copy)
    monkeypatch.setattr(vectors, "VECTORS_DIR", copy)
    load = vectors.load_bad_signatures if which == "bad" else (lambda: vectors.load_wycheproof(which))
    load()  # the untouched copy loads
    target = copy / relative
    raw = bytearray(target.read_bytes())
    position = raw.index(b'"invalid"') + 1
    raw[position:position + 7] = b"valid  "[:7]  # flip one published answer; the file is still valid JSON
    target.write_bytes(bytes(raw))
    with pytest.raises(vectors.VectorFileChanged, match="not the pinned copy"):
        load()
    target.unlink()
    with pytest.raises(vectors.VectorFileChanged, match="missing"):
        load()


def test_bad_signature_file_is_pinned_and_holds_no_private_key():
    path = VECTORS_DIR / "bad-signatures" / "cases.json"
    assert vectors.file_sha256(path) == vectors.BAD_SIGNATURES["sha256"]
    assert vectors.BAD_SIGNATURES["sha256"] in (path.parent / "README.md").read_text()
    data = json.loads(path.read_text())
    assert data["schema"] == "isogeny.bad-signatures/1" and "private" not in path.read_text().lower().replace("private key was never", "")
    assert all(set(c) == {"id", "what", "public_key", "message", "signature", "expected"} for c in data["cases"])
    cases = vectors.load_bad_signatures().cases
    assert tuple(c.id for c in cases) == vectors.BAD_SIGNATURE_IDS and len(cases) == 16
    assert [c.id for c in cases if c.expected == "valid"] == ["good-1", "good-2"]
    assert sum(c.expected == "invalid" for c in cases) == 14
    by_id = {c.id: c for c in cases}
    assert by_id["r0-s0"].signature == "3006020100020100" and by_id["empty"].signature == ""
    assert len({c.public_key for c in cases}) == 1  # one test key; only its public half is in the file
    assert all(c.comment for c in cases)
    # the builder script is kept for transparency and can never overwrite the shipped file
    builder = (REPO_ROOT / "backend" / "tools" / "build_bad_signature_cases.py").read_text()
    assert 'open(sys.argv[1], "x"' in builder and "private_bytes" not in builder


# ------------------------------------------------------------------ the reference library

def test_reference_library_is_right_on_every_official_case():
    ecdsa = vectors.load_wycheproof("ecdsa_p256")
    answers = reference.answers("ecdsa_p256", ecdsa.cases)
    assert len(answers) == 484
    assert [c.id for c in ecdsa.cases if (answers[c.id] == "accept") != (c.expected == "valid")] == []
    ed = vectors.load_wycheproof("ed25519")
    answers = reference.answers("ed25519", ed.cases)
    counted = [c for c in ed.cases if c.expected != "acceptable"]
    assert len(counted) == 181  # 117 valid + 64 invalid; the 29 "acceptable" cases may go either way
    assert [c.id for c in counted if (answers[c.id] == "accept") != (c.expected == "valid")] == []
    assert reference.LIBRARY.startswith("cryptography ")


def test_reference_library_is_right_on_all_16_bad_signature_cases():
    cases = vectors.load_bad_signatures().cases
    answers = reference.answers("bad_signatures", cases)
    assert [c.id for c in cases if (answers[c.id] == "accept") != (c.expected == "valid")] == []
    assert reference.verify_ecdsa_p256("not hex", "", "") is False and reference.verify_ed25519("00", "", "zz") is False


def test_reference_bench_has_the_adapter_shape():
    out = reference.bench_ecdsa_p256(5, "abcd")
    assert len(out["sign_ms"]) == 5 and len(out["verify_ms"]) == 5 and out["public_key_bytes"] == 65
    assert 68 <= out["signature_bytes"] <= 72 and "private" not in json.dumps(out)


# ------------------------------------------------------------------ the demo components, through the harness

@pytest.fixture(scope="module")
def official_run(tmp_path_factory):
    vector_set = vectors.load_wycheproof("ecdsa_p256")
    result = demo_runner(tmp_path_factory.mktemp("official")).run_job(
        {"op": "verify_batch", "subjects": SUBJECTS, "cases": as_cases(vector_set)}, time_limit=240)
    print(f"\n484 official cases x 3 subjects, demo mode: {result.duration_ms} ms")
    return vector_set, result


def test_acme_sign_1_4_2_is_wrong_on_exactly_168_171_364_of_484(official_run):
    vector_set, result = official_run
    assert result.ok and result.mode == "demo" and len(result.lines) == 3 * 484
    assert wrong_ids(vector_set, result.lines, "acme-sign-1.4.2") == ["168", "171", "364"]
    wrong = {line["id"]: line["valid"] for line in result.lines
             if line["subject"] == "acme-sign-1.4.2" and line["id"] in ("168", "171", "364")}
    assert wrong == {"168": True, "171": True, "364": True}  # all three: a bad signature accepted


def test_acme_sign_1_4_3_is_right_on_all_484(official_run):
    vector_set, result = official_run
    assert wrong_ids(vector_set, result.lines, "acme-sign-1.4.3") == []


def test_accept_all_control_is_wrong_on_every_invalid_official_case(official_run):
    vector_set, result = official_run
    assert wrong_ids(vector_set, result.lines, "control-accept-all") == [c.id for c in vector_set.cases if c.expected == "invalid"]
    assert sum(c.expected == "invalid" for c in vector_set.cases) == 310


def test_official_run_lines_keep_case_order_and_carry_no_keys(official_run):
    vector_set, result = official_run
    ids = [c.id for c in vector_set.cases]
    for subject in SUBJECTS:
        assert [line["id"] for line in result.lines if line["subject"] == subject] == ids
    assert all(set(line) == {"subject", "id", "rc", "valid", "error", "ms"} for line in result.lines)
    assert "private" not in json.dumps(result.lines)


def test_bad_signature_cases_on_both_versions_and_the_control(tmp_path):
    vector_set = vectors.load_bad_signatures()
    result = demo_runner(tmp_path).run_job({"op": "verify_batch", "subjects": SUBJECTS, "cases": as_cases(vector_set)})
    assert result.ok and len(result.lines) == 3 * 16
    assert wrong_ids(vector_set, result.lines, "acme-sign-1.4.3") == []
    wrong = wrong_ids(vector_set, result.lines, "acme-sign-1.4.2")
    assert wrong == ["r0-s0", "s-plus-n"]  # exactly the two listed in demo/vectors/bad-signatures/README.md
    readme = (VECTORS_DIR / "bad-signatures" / "README.md").read_text()
    assert "wrong on exactly **`r0-s0`** and **`s-plus-n`**" in readme
    # every wrong one is a value outside 1..n-1 that was accepted: the one planted bug
    by_id = {c.id: c for c in vector_set.cases}
    assert all(by_id[i].expected == "invalid" and ("r = 0" in by_id[i].comment or "above the allowed range" in by_id[i].comment)
               for i in wrong)
    assert wrong_ids(vector_set, result.lines, "control-accept-all") == [c.id for c in vector_set.cases if c.expected == "invalid"]


def test_vectors_module_holds_no_verdict_logic_and_reads_json_only():
    source = Path(vectors.__file__).read_text()
    for banned in ("eval(", "exec(", "pickle", "subprocess", "importlib", "yaml"):
        assert banned not in source

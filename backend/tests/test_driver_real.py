"""The batch driver's phase 4c parts, run as a local process on a copy of it: the extra word --real, the table of a real-library
image, the known-answer batch, the key-exchange round trip, and what is never written out. The library is a tiny fake
wrapper written here; no Docker, no real library."""

import hashlib
import json
import shutil
import subprocess
import sys

import pytest

from app.run.components import WITHHELD
from app.config import COMPONENTS_DIR

# fixed answers of the fake wrapper: none of these may appear anywhere in what the driver writes
PUBLIC, PRIVATE, CIPHERTEXT, SECRET, SIGNATURE = "1a2b3c4d", "5e6f7a8b", "9c0d1e2f", "3a4b5c6d", "7e8f9a0b"
HIDDEN = (PUBLIC, PRIVATE, SECRET, SIGNATURE)
FAKE = f'''import json, sys
command = sys.argv[1]
text = sys.stdin.read()
req = json.loads(text) if text.strip() else {{}}
if req.get("public_key") == "00":
    print(json.dumps({{"refused": True, "note": "no"}}))
elif command == "keygen":
    print(json.dumps({{"public_key": "{PUBLIC}", "private_key": "{PRIVATE}"}}))
elif command == "encaps":
    print(json.dumps({{"ciphertext": "{CIPHERTEXT}", "shared_secret": "{SECRET}"}}))
elif command == "decaps":
    print(json.dumps({{"shared_secret": "{SECRET}"}}))
elif command == "sign":
    print(json.dumps({{"signature": "{SIGNATURE}"}}))
elif command == "verify":
    print(json.dumps({{"valid": False, "note": "general error: IndexError"}}))
else:
    print(json.dumps({{"error": "unknown command"}}))
'''


class Sandbox:
    """A copy of the driver where the app puts it (components/harness/driver.py), and an image's table next to it (real/)."""

    def __init__(self, root):
        self.root = root
        (root / "components" / "harness").mkdir(parents=True)
        shutil.copy(COMPONENTS_DIR / "harness" / "driver.py", root / "components" / "harness" / "driver.py")
        shutil.copytree(
            COMPONENTS_DIR / "controls",
            root / "components" / "controls",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        (root / "real").mkdir()
        (root / "real" / "fake.py").write_text(FAKE)
        self.driver = root / "components" / "harness" / "driver.py"
        self.table = {"fake-1.0": [sys.executable, "-I", str(root / "real" / "fake.py")]}
        self.write_table(self.table)

    def write_table(self, table) -> None:
        (self.root / "real" / "subjects.json").write_text(table if isinstance(table, str) else json.dumps(table))

    def run(self, job, *args):
        done = subprocess.run(
            [sys.executable, "-I", "-B", str(self.driver), *args],
            input=job if isinstance(job, str) else json.dumps(job),
            capture_output=True,
            text=True,
            timeout=60,
        )
        lines = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
        return done.returncode, lines, done.stdout


@pytest.fixture
def box(tmp_path):
    return Sandbox(tmp_path)


def sha(*parts) -> str:
    return hashlib.sha256("\n".join(parts).encode("ascii")).hexdigest()


def kat(*cases, subject="fake-1.0"):
    return {
        "op": "kat_batch",
        "subject": subject,
        "cases": [{"id": i, "command": c, "input": given} for i, c, given in cases],
    }


# ---------------------------------------------------------------- who may run what


def test_without_real_the_fake_subject_is_unknown(box):
    rc, lines, _ = box.run(kat(("a", "keygen", {})))
    assert rc == 2 and lines == [{"refused": "unknown subject"}]


def test_with_real_the_table_is_read_and_the_subject_runs(box):
    rc, lines, _ = box.run(kat(("a", "keygen", {})), "--real")
    assert rc == 0 and lines[-1] == {"done": True, "lines": 1} and lines[0]["id"] == "a" and lines[0]["error"] is None


@pytest.mark.parametrize(
    "args", [("--fake",), ("real",), ("--real", "--real"), ("--real", "x"), ("-real",), ("--REAL",), ("",)]
)
def test_any_other_argument_is_refused_before_anything_is_read(box, args):
    rc, lines, _ = box.run(kat(("a", "keygen", {})), *args)
    assert rc == 2 and lines == [{"refused": "unknown argument"}]


@pytest.mark.parametrize(
    "table",
    [
        "not json at all",
        "[]",
        "{}",
        '[["a"]]',
        "null",
        '{"fake-1.0": "python"}',
        '{"fake-1.0": []}',
        '{"fake-1.0": [1]}',
        '{"fake-1.0": [""]}',
        '{"fake-1.0": ["ok", null]}',
        '{"fake-1.0": {"a": "b"}}',
    ],
)
def test_a_table_that_is_not_an_object_of_string_lists_stops_the_driver(box, table):
    box.write_table(table)
    rc, lines, out = box.run(kat(("a", "keygen", {})), "--real")
    assert rc == 2 and lines == [{"refused": "this image's table of real-library subjects could not be read"}]


def test_a_missing_table_stops_the_driver(box):
    (box.root / "real" / "subjects.json").unlink()
    rc, lines, _ = box.run(kat(("a", "keygen", {})), "--real")
    assert rc == 2 and lines == [{"refused": "this image's table of real-library subjects could not be read"}]


@pytest.mark.parametrize(
    "name", ["acme-sign-1.4.2", "acme-sign-1.4.3", "control-accept-all", "control-slow:acme-sign-1.4.2"]
)
def test_a_table_entry_may_not_reuse_a_built_in_subject_name(box, name):
    box.write_table({"fake-1.0": box.table["fake-1.0"], name: box.table["fake-1.0"]})
    rc, lines, _ = box.run(kat(("a", "keygen", {})), "--real")
    assert rc == 2 and lines == [{"refused": "this image's table of real-library subjects could not be read"}]


def test_a_job_cannot_name_a_program_or_a_path(box):
    for subject in ("/bin/sh", sys.executable, "../real/fake.py", "fake-1.0 ", "FAKE-1.0", None, 5, ["fake-1.0"]):
        rc, lines, _ = box.run(kat(("a", "keygen", {}), subject=subject), "--real")
        assert rc == 2 and lines == [{"refused": "unknown subject"}], subject


# ---------------------------------------------------------------- known-answer cases


def test_kat_batch_reports_declined_valid_and_the_fingerprint_never_the_answer(box):
    job = kat(
        ("k", "keygen", {"seed": "0102", "algorithm": "ML-KEM-768"}),
        ("e", "encaps", {"public_key": "0a0b", "randomness": "0c0d", "algorithm": "ML-KEM-768"}),
        ("d", "decaps", {"private_key": "0e0f", "ciphertext": "0102"}),
        (
            "s",
            "sign",
            {
                "private_key": "0e0f",
                "message": "",
                "context": "",
                "randomness": "aa",
                "deterministic": True,
                "interface": "external",
                "algorithm": "ML-DSA-65",
            },
        ),
        ("v", "verify", {"public_key": "0a0b", "message": "00", "signature": "0102", "interface": "mu"}),
        ("refused", "encaps", {"public_key": "00"}),
    )
    rc, lines, out = box.run(job, "--real")
    assert rc == 0 and lines[-1] == {"done": True, "lines": 6}
    by_id = {line["id"]: line for line in lines[:-1]}
    assert [line["id"] for line in lines[:-1]] == ["k", "e", "d", "s", "v", "refused"]  # in case order
    for line in by_id.values():
        assert {"subject", "id", "rc", "error", "declined", "valid", "answer_sha256", "ms"} <= set(line) and line[
            "subject"
        ] == "fake-1.0"
    assert (by_id["k"]["declined"], by_id["k"]["valid"], by_id["k"]["error"]) == (False, None, None)
    assert by_id["k"]["answer_sha256"] == sha(f"public_key={PUBLIC}", f"private_key={PRIVATE}")
    assert by_id["e"]["answer_sha256"] == sha(f"ciphertext={CIPHERTEXT}", f"shared_secret={SECRET}")
    assert by_id["d"]["answer_sha256"] == sha(f"shared_secret={SECRET}")
    assert by_id["s"]["answer_sha256"] == sha(f"signature={SIGNATURE}")
    assert (by_id["v"]["declined"], by_id["v"]["valid"], by_id["v"]["answer_sha256"]) == (False, False, None)
    assert by_id["v"]["note"] == "general error: IndexError"
    assert (by_id["refused"]["declined"], by_id["refused"]["valid"], by_id["refused"]["answer_sha256"]) == (
        True,
        None,
        None,
    )
    assert by_id["refused"]["note"] == "no"
    for value in HIDDEN:
        assert value not in out, value  # no key, secret or signature value is written anywhere
    assert CIPHERTEXT not in out  # nor a ciphertext: only its fingerprint


def test_kat_batch_says_a_case_has_no_answer_when_the_library_gives_nothing_usable(box):
    (box.root / "real" / "fake.py").write_text(
        "import sys, json\nsys.stdin.read()\nprint(json.dumps({'ciphertext': 'zz'}))\n"
    )
    rc, lines, _ = box.run(
        kat(("e", "encaps", {"public_key": "0a0b"}), ("v", "verify", {"public_key": "0a0b"})), "--real"
    )
    assert rc == 0
    assert [(line["id"], line["declined"], line["answer_sha256"], line["error"]) for line in lines[:-1]] == [
        ("e", None, None, "bad output"),
        ("v", None, None, "bad output"),
    ]


@pytest.mark.parametrize(
    "bad_input",
    [
        {"unknown_key": "00"},
        {"public_key": "zz"},
        {"public_key": "0"},
        {"public_key": 5},
        {"public_key": None},
        {"public_key": "00" * 20001},
        {"algorithm": "ML-DSA-99"},
        {"algorithm": "RSA 2048"},
        {"interface": "weird"},
        {"interface": None},
        {"deterministic": "yes"},
        {"deterministic": 1},
        {"private_key": ["00"]},
        {"command": "00"},
        {"../x": "00"},
    ],
)
def test_a_case_input_the_driver_does_not_know_refuses_the_whole_job_before_anything_runs(box, bad_input):
    marker = box.root / "ran.txt"
    (box.root / "real" / "fake.py").write_text(f"import sys\nopen({str(marker)!r}, 'a').write('x')\nprint('{{}}')\n")
    job = kat(("good", "keygen", {"seed": "00"}), ("bad", "keygen", bad_input), ("after", "keygen", {}))
    rc, lines, _ = box.run(job, "--real")
    assert rc == 2 and lines == [{"refused": "a case input holds something this driver does not pass on"}]
    assert not marker.exists()  # not even the good case before it was run


@pytest.mark.parametrize(
    "cases, why",
    [
        ([], "cases must be a list of 1 to 5000 cases"),
        ("x", "cases must be a list of 1 to 5000 cases"),
        ([{"id": "", "command": "keygen", "input": {}}], "every case needs a short text id"),
        ([{"id": "x" * 65, "command": "keygen", "input": {}}], "every case needs a short text id"),
        ([{"id": 5, "command": "keygen", "input": {}}], "every case needs a short text id"),
        ([{"id": "a", "command": "info", "input": {}}], "every case needs a known command and an input object"),
        ([{"id": "a", "command": "bench", "input": {}}], "every case needs a known command and an input object"),
        ([{"id": "a", "command": "keygen", "input": []}], "every case needs a known command and an input object"),
        ([{"id": "a", "command": "keygen"}], "every case needs a known command and an input object"),
    ],
)
def test_a_badly_formed_kat_job_is_refused(box, cases, why):
    rc, lines, _ = box.run({"op": "kat_batch", "subject": "fake-1.0", "cases": cases}, "--real")
    assert rc == 2 and lines == [{"refused": why}]


def test_a_job_that_is_not_json_or_has_an_unknown_op_is_refused(box):
    assert box.run("this is not json", "--real")[:2] == (2, [{"refused": "the job was not JSON"}])
    assert box.run({"op": "launch"}, "--real")[:2] == (2, [{"refused": "unknown job"}])
    assert box.run("[1]", "--real")[:2] == (2, [{"refused": "unknown job"}])


# ---------------------------------------------------------------- the plain call job


def test_a_plain_call_cannot_ask_encaps_or_decaps(box):
    for command in ("encaps", "decaps", "kat", "rm", ""):
        rc, lines, _ = box.run({"op": "call", "subject": "fake-1.0", "command": command, "input": {}}, "--real")
        assert rc == 2 and lines == [{"refused": "unknown command"}], command


def test_a_plain_call_still_withholds_the_private_key(box):
    rc, lines, out = box.run({"op": "call", "subject": "fake-1.0", "command": "keygen", "input": {}}, "--real")
    assert rc == 0 and lines[0]["out"] == {"public_key": PUBLIC, "private_key": WITHHELD} and PRIVATE not in out


# ---------------------------------------------------------------- verify_batch and the note


def test_verify_batch_passes_the_wrappers_note_on(box):
    job = {
        "op": "verify_batch",
        "subjects": ["fake-1.0"],
        "algorithm": "ECDSA P-256",
        "cases": [{"id": "c1", "public_key": "0a0b", "message": "00", "signature": "0102"}],
    }
    rc, lines, _ = box.run(job, "--real")
    assert rc == 0 and lines[-1] == {"done": True, "lines": 1}
    assert lines[0]["valid"] is False and lines[0]["error"] is None and lines[0]["note"] == "general error: IndexError"


def test_a_note_is_cut_short_and_made_printable_and_left_out_when_there_is_none(box):
    (box.root / "real" / "fake.py").write_text(
        "import sys, json\nreq = json.loads(sys.stdin.read())\n"
        "note = {'00': 'x' * 500, '01': 'a\\u0007b\\nc', '02': 5, '03': ''}.get(req['signature'][:2])\n"
        "out = {'valid': True}\nout.update({'note': note} if note is not None else {})\nprint(json.dumps(out))\n"
    )
    cases = [{"id": n, "public_key": "0a0b", "message": "00", "signature": n} for n in ("00", "01", "02", "03", "04")]
    rc, lines, _ = box.run({"op": "verify_batch", "subjects": ["fake-1.0"], "cases": cases}, "--real")
    notes = {line["id"]: line.get("note") for line in lines[:-1]}
    assert (
        notes["00"] == "x" * 120
        and notes["01"] == "a b c"
        and notes["02"] is None
        and notes["03"] is None
        and notes["04"] is None
    )
    assert "note" not in lines[2] and "note" not in lines[4]


# ---------------------------------------------------------------- the key-exchange round trip


def test_kem_roundtrip_writes_sizes_a_yes_no_one_ciphertext_and_one_fingerprint(box):
    job = {"op": "kem_roundtrip", "subject": "fake-1.0", "algorithm": "ML-KEM-768", "peer_public_key": "0a0b0c0d"}
    rc, lines, out = box.run(job, "--real")
    assert rc == 0 and lines[-1] == {"done": True, "lines": 4}
    steps = {line["step"]: line for line in lines[:-1]}
    assert [line["step"] for line in lines[:-1]] == ["keygen", "encaps", "decaps", "encaps_to_app"]
    assert steps["keygen"]["out"] == {"public_key_bytes": len(PUBLIC) // 2, "private_key": WITHHELD}
    assert steps["encaps"]["out"] == {"ciphertext_bytes": len(CIPHERTEXT) // 2, "shared_secret_bytes": len(SECRET) // 2}
    assert steps["decaps"]["out"] == {"same_secret": True}
    assert steps["encaps_to_app"]["out"] == {
        "ciphertext": CIPHERTEXT,
        "shared_secret_sha256": hashlib.sha256(bytes.fromhex(SECRET)).hexdigest(),
    }
    assert all(line["error"] is None for line in lines[:-1])
    for value in (PRIVATE, SECRET, PUBLIC):  # no private key, no shared secret, not even the public key
        assert value not in out, value


def test_kem_roundtrip_says_when_the_library_refuses_the_apps_key(box):
    rc, lines, out = box.run(
        {"op": "kem_roundtrip", "subject": "fake-1.0", "algorithm": "ML-KEM-768", "peer_public_key": "00"}, "--real"
    )
    assert rc == 0
    last = lines[-2]
    assert last["step"] == "encaps_to_app" and last["out"] is None and last["error"] == "the library refused: no"
    assert PRIVATE not in out and SECRET not in out


def test_kem_roundtrip_stops_at_the_first_step_that_fails(box):
    (box.root / "real" / "fake.py").write_text("import sys\nsys.stdin.read()\nprint('not json')\n")
    rc, lines, _ = box.run(
        {"op": "kem_roundtrip", "subject": "fake-1.0", "algorithm": "ML-KEM-768", "peer_public_key": "0a0b"}, "--real"
    )
    assert rc == 0 and [line["step"] for line in lines[:-1]] == ["keygen"] and lines[0]["error"] == "bad output"


@pytest.mark.parametrize(
    "job",
    [
        {"op": "kem_roundtrip", "subject": "fake-1.0", "algorithm": "ML-KEM-768"},
        {"op": "kem_roundtrip", "subject": "fake-1.0", "algorithm": "ML-KEM-768", "peer_public_key": ""},
        {"op": "kem_roundtrip", "subject": "fake-1.0", "algorithm": "ML-KEM-768", "peer_public_key": "xyz"},
        {"op": "kem_roundtrip", "subject": "fake-1.0", "algorithm": "ML-KEM-1", "peer_public_key": "0a0b"},
    ],
)
def test_a_badly_formed_kem_roundtrip_job_is_refused(box, job):
    rc, lines, _ = box.run(job, "--real")
    assert rc == 2 and len(lines) == 1 and set(lines[0]) == {"refused"}


# ---------------------------------------------------------------- what stayed as it was


def test_the_driver_still_knows_only_its_own_subjects_without_a_table(box):
    rc, lines, _ = box.run({"op": "call", "subject": "acme-sign-9.9", "command": "info", "input": {}})
    assert rc == 2 and lines == [{"refused": "unknown subject"}]

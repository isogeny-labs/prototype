"""The two official post-quantum case sets (ML-KEM-768 and ML-DSA-65), read as data from the pinned files, and the
fingerprint of an answer, which must be the same in the app and in the batch driver. No Docker."""
import hashlib
import importlib.util
import json
import re
from collections import Counter

import pytest

from app import pq_vectors, vectors
from app.config import COMPONENTS_DIR, VECTORS_DIR

NON_HEX_INPUTS = ("algorithm", "deterministic", "interface")
HEX = re.compile(r"(?:[0-9a-fA-F]{2})*")


@pytest.fixture(scope="module")
def kem():
    return pq_vectors.load("mlkem_vectors")


@pytest.fixture(scope="module")
def dsa():
    return pq_vectors.load("mldsa_vectors")


def count(cases, part):
    return Counter(c.expect for c in cases if c.part == part)


def load_driver():
    spec = importlib.util.spec_from_file_location("evlab_driver_for_pq", COMPONENTS_DIR / "harness" / "driver.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- the cases

def test_mlkem_has_655_cases_in_three_parts(kem):
    assert len(kem) == 655
    assert Counter(c.part for c in kem) == {"keygen": 125, "encaps": 300, "decaps": 230}
    assert [(p, n) for p, _, n in pq_vectors.EXAMS["mlkem_vectors"]["parts"]] == [("keygen", 125), ("encaps", 300), ("decaps", 230)]


def test_mlkem_expectations_part_by_part(kem):
    assert count(kem, "keygen") == {"answer": 125}
    assert count(kem, "encaps") == {"answer": 158, "refuse": 137, "accept": 5}
    assert count(kem, "decaps") == {"answer": 174, "refuse": 51, "accept": 5}


def test_mldsa_has_475_cases_in_three_parts(dsa):
    assert len(dsa) == 475
    assert Counter(c.part for c in dsa) == {"keygen": 25, "sign": 195, "verify": 255}
    assert [(p, n) for p, _, n in pq_vectors.EXAMS["mldsa_vectors"]["parts"]] == [("keygen", 25), ("sign", 195), ("verify", 255)]


def test_mldsa_expectations_part_by_part(dsa):
    assert count(dsa, "keygen") == {"answer": 25}
    assert count(dsa, "sign") == {"answer": 191, "refuse": 4}
    assert count(dsa, "verify") == {"accept": 88, "reject": 167}


def test_the_key_check_cases_that_the_controls_are_judged_by(kem):
    out_of_range = [c for c in kem if pq_vectors.KEY_OUT_OF_RANGE in c.flags]
    hash_wrong = [c for c in kem if pq_vectors.KEY_HASH_WRONG in c.flags]
    assert len(out_of_range) == 117 and {c.part for c in out_of_range} == {"encaps"} and {c.expect for c in out_of_range} == {"refuse"}
    assert len(hash_wrong) == 6 and {c.part for c in hash_wrong} == {"decaps"} and {c.expect for c in hash_wrong} == {"refuse"}
    assert not set(c.id for c in out_of_range) & set(c.id for c in hash_wrong)


def test_the_flags_appear_in_the_mldsa_set_nowhere(dsa):
    assert not [c for c in dsa if pq_vectors.KEY_OUT_OF_RANGE in c.flags or pq_vectors.KEY_HASH_WRONG in c.flags]


def test_ids_are_unique_and_every_case_is_filled_in(kem, dsa):
    for cases in (kem, dsa):
        assert len({c.id for c in cases}) == len(cases)
        for c in cases:
            assert c.source in (pq_vectors.NIST, pq_vectors.WYCHEPROOF) and c.file and c.command and c.input
            assert c.id.startswith("nist-" if c.source == pq_vectors.NIST else "wycheproof-")
            assert (c.answer_sha256 is not None) == (c.expect == "answer")
            if c.answer_sha256 is not None:
                assert re.fullmatch(r"[0-9a-f]{64}", c.answer_sha256)
            assert c.expect in (("accept", "reject") if c.command == "verify" else ("answer", "refuse", "accept"))
            assert len(c.comment) <= 160


def test_every_input_value_is_hex_or_one_of_the_allowed_flags(kem, dsa):
    for algorithm, cases in (("ML-KEM-768", kem), ("ML-DSA-65", dsa)):
        for c in cases:
            assert c.input["algorithm"] == algorithm
            for key, value in c.input.items():
                if key == "algorithm":
                    continue
                if key == "deterministic":
                    assert value is True, c.id
                elif key == "interface":
                    assert value in ("external", "internal", "mu"), c.id
                else:
                    assert isinstance(value, str) and HEX.fullmatch(value) and len(value) <= pq_vectors.MAX_HEX, (c.id, key)
    driver = load_driver()      # the driver passes on exactly the keys the cases use
    used = {key for c in kem + dsa for key in c.input}
    assert used <= set(driver.KAT_HEX_INPUTS) | set(NON_HEX_INPUTS)
    assert set(c.command for c in kem + dsa) <= set(driver.KAT_COMMANDS)


def test_the_pre_hash_variant_is_left_out_of_the_signature_exam(dsa):
    left_out, nist_cases = 0, 0
    for name in ("acvp_mldsa_siggen", "acvp_mldsa_sigver"):
        folder, file, _, _ = pq_vectors.FILES[name]
        data = json.loads((VECTORS_DIR / folder / file).read_text())
        for group in data["testGroups"]:
            if group.get("parameterSet") != "ML-DSA-65":
                continue
            if group.get("preHash") == "preHash":
                left_out += len(group["tests"])
            else:
                nist_cases += len(group["tests"])
    assert left_out == pq_vectors.EXAMS["mldsa_vectors"]["left_out"] == 45
    assert nist_cases == sum(1 for c in dsa if c.source == pq_vectors.NIST and c.part in ("sign", "verify"))


def test_mldsa_cases_say_which_form_of_the_message_they_sign(dsa):
    assert {c.input["interface"] for c in dsa if c.command in ("sign", "verify")} <= {"external", "internal", "mu"}
    assert not any("interface" in c.input for c in dsa if c.part == "keygen")


def test_the_exam_files_are_pinned_with_a_source_and_a_link():
    for exam in pq_vectors.EXAMS:
        pins = pq_vectors.file_pins(exam)
        assert len(pins) == len(pq_vectors.EXAMS[exam]["files"])
        for pin in pins:
            assert re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]) and pin["source"] in (pq_vectors.NIST, pq_vectors.WYCHEPROOF)
            assert pq_vectors.source_url(pin["file"]).startswith("https://github.com/")
            assert (VECTORS_DIR / ("acvp" if pin["source"] == pq_vectors.NIST else "wycheproof") / pin["file"]).is_file()
    with pytest.raises(KeyError):
        pq_vectors.source_url("nothing.json")


# ---------------------------------------------------------------- a changed or missing file is refused

@pytest.mark.parametrize("exam, name", [("mlkem_vectors", "wp_mlkem_encaps"), ("mlkem_vectors", "acvp_mlkem_keygen"),
                                        ("mldsa_vectors", "acvp_mldsa_sigver"), ("mldsa_vectors", "wp_mldsa_verify")])
def test_a_changed_file_is_refused(monkeypatch, exam, name):
    folder, file, sha256, source = pq_vectors.FILES[name]
    changed = dict(pq_vectors.FILES, **{name: (folder, file, "0" * 64 if sha256[0] != "0" else "1" * 64, source)})
    monkeypatch.setattr(pq_vectors, "FILES", changed)
    with pytest.raises(vectors.VectorFileChanged):
        pq_vectors.load(exam)


@pytest.mark.parametrize("exam", ["mlkem_vectors", "mldsa_vectors"])
def test_a_missing_file_is_refused(monkeypatch, tmp_path, exam):
    monkeypatch.setattr(pq_vectors, "VECTORS_DIR", tmp_path)
    with pytest.raises(vectors.VectorFileChanged):
        pq_vectors.load(exam)


def test_a_file_with_the_right_name_but_other_content_is_refused(monkeypatch, tmp_path):
    (tmp_path / "acvp").mkdir()
    (tmp_path / "wycheproof").mkdir()
    for folder, file, _, _ in pq_vectors.FILES.values():
        (tmp_path / folder / file).write_text("{}")
    monkeypatch.setattr(pq_vectors, "VECTORS_DIR", tmp_path)
    for exam in pq_vectors.EXAMS:
        with pytest.raises(vectors.VectorFileChanged):
            pq_vectors.load(exam)


# ---------------------------------------------------------------- the fingerprint of an answer is the driver's

def test_the_answer_fields_are_the_drivers():
    driver = load_driver()
    assert driver.ANSWER_FIELDS == pq_vectors.ANSWER_FIELDS
    assert driver.MAX_HEX == pq_vectors.MAX_HEX == 40000
    assert set(pq_vectors.ANSWER_FIELDS) == {"keygen", "encaps", "decaps", "sign"}


SAMPLES = {"keygen": {"public_key": "AaBb01", "private_key": "CcDd02"}, "encaps": {"ciphertext": "0A0b", "shared_secret": "FF00"},
           "decaps": {"shared_secret": "Ab12"}, "sign": {"signature": "DEADbeef"}}


@pytest.mark.parametrize("command", sorted(SAMPLES))
def test_the_fingerprint_is_the_same_value_the_driver_computes(command, monkeypatch):
    fields = SAMPLES[command]
    by_hand = hashlib.sha256("\n".join(f"{n}={fields[n].lower()}" for n in pq_vectors.ANSWER_FIELDS[command]).encode("ascii")).hexdigest()
    assert pq_vectors.answer_sha256(command, fields) == by_hand
    driver = load_driver()
    written = []
    monkeypatch.setattr(driver, "emit", written.append)
    monkeypatch.setattr(driver, "run_command", lambda subject, cmd, payload: (0, dict(fields), None, 1.0))
    job = {"op": "kat_batch", "subject": "acme-sign-1.4.2", "cases": [{"id": "c1", "command": command, "input": {}}]}
    driver.op_kat_batch(job)()
    (line,) = written
    assert line["answer_sha256"] == by_hand == pq_vectors.answer_sha256(command, fields)
    assert line["declined"] is False and line["valid"] is None
    assert not any(value in json.dumps(line) for value in fields.values())      # the answer itself is never written


def test_the_fingerprint_changes_with_any_field_and_ignores_the_letter_case():
    base = {"public_key": "aabb", "private_key": "ccdd"}
    assert pq_vectors.answer_sha256("keygen", base) == pq_vectors.answer_sha256("keygen", {"public_key": "AABB", "private_key": "CCDD"})
    assert pq_vectors.answer_sha256("keygen", base) != pq_vectors.answer_sha256("keygen", {"public_key": "aabb", "private_key": "ccde"})
    assert pq_vectors.answer_sha256("keygen", base) != pq_vectors.answer_sha256("keygen", {"public_key": "aabc", "private_key": "ccdd"})
    # the fields are in a fixed order, so swapping the two values is a different answer
    assert pq_vectors.answer_sha256("keygen", base) != pq_vectors.answer_sha256("keygen", {"public_key": "ccdd", "private_key": "aabb"})

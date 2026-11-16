"""Phase 4d, slow set (needs Docker and the prepared images): the five measurable demo rows on their pinned public
copies with the real controls, through the web (so the measured view's shape is checked too), and the CycloneDX and
SPDX lists giving the same answers."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from conftest import PASSWORD, free_port

pytestmark = pytest.mark.slow
DEMO = Path(__file__).resolve().parents[3] / "demo"


@pytest.fixture(scope="module")
def walk(docker_ready, tmp_path_factory):
    settings = Settings(data_dir=tmp_path_factory.mktemp("deps-isolated") / "data", demo_tls_port=free_port(), force_mode="isolated")
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/setup", json={"password": PASSWORD}).status_code == 200
        imp = client.post("/api/import/demo").json()
        pid = client.post(f"/api/import/{imp['id']}/plan").json()["id"]
        out = {}
        for name in ("dependencies-demo.cdx.json", "dependencies-demo.spdx.json"):
            view = client.post(f"/api/plans/{pid}/dependencies", params={"filename": name}, content=(DEMO / name).read_bytes(),
                               headers={"Content-Type": "application/octet-stream"}).json()
            pay = next(g for g in view["groups"] if g["label"] == "acme-pay-server 1.0.0")
            server = next(o["key"] for o in pay["picker"]["options"] if o["key"].startswith("server:"))
            assert client.post(f"/api/plans/{pid}/dependencies/tie", json={"top": pay["key"], "system": server}).status_code == 200
            assert client.post(f"/api/plans/{pid}/dependencies/measure", json={}).status_code == 200
            client.app.state.lab.wait_until_dependencies_measured(pid, 900)
            out[name] = client.get(f"/api/import/{imp['id']}/dependencies").json()
        yield out


def _rows(view):
    return {r["label"]: r for g in view["groups"] for r in g["rows"]}


EXPECTED = {   # from demo/expected-dependencies.json, isolated mode
    "python-ecdsa 0.13.2": {"ml_kem_768": ("no", "public_copy", "measured"), "x25519mlkem768": ("doesnt_apply", None, "not_offered"),
                            "ml_dsa_65": ("no", "public_copy", "measured")},
    "openssl 3.0.22": {q: ("no", "public_copy", "measured") for q in ("ml_kem_768", "x25519mlkem768", "ml_dsa_65")},
    "openjdk 17.0.2": {"ml_kem_768": ("no", "public_copy", "measured"), "x25519mlkem768": ("no", "release_notes", "not_offered"),
                       "ml_dsa_65": ("no", "public_copy", "measured")},
    "elliptic 6.5.6": {"ml_kem_768": ("no", "public_copy", "measured"), "x25519mlkem768": ("doesnt_apply", None, "not_offered"),
                       "ml_dsa_65": ("no", "public_copy", "measured")},
    "openssl 3.5.9": {q: ("yes", "public_copy", "measured") for q in ("ml_kem_768", "x25519mlkem768", "ml_dsa_65")},
}


def test_the_five_measurable_rows_with_the_real_controls(walk):
    rows = _rows(walk["dependencies-demo.cdx.json"])
    for label, want in EXPECTED.items():
        row = rows[label]
        got = {c["question"]: (c["answer"], c["label"], c["state"]) for c in row["cells"]}
        assert got == want, label
        assert row["measurement"]["controls"] == "as_expected" and row["measurement"]["result"]["control"]["outcome"] == "as_expected"
    assert rows["openssl 3.0.22"]["same_copy_note"] and rows["openssl 3.5.9"]["same_copy_note"]
    assert {c["agreement"] for c in rows["openssl 3.0.22"]["cells"]} == {"agrees"}
    assert {c["question"]: c["first_version"] for c in rows["python-ecdsa 0.13.2"]["cells"] if c["answer"] == "no"} == \
        {"ml_kem_768": "none_known", "ml_dsa_65": "none_known"}


def test_a_measured_no_says_what_the_library_itself_said(walk):
    rows = _rows(walk["dependencies-demo.cdx.json"])
    reasons = {c["question"]: c["reason"] for c in rows["openjdk 17.0.2"]["cells"]}
    assert reasons["ml_kem_768"].startswith("The library itself said no:") and "KeyPairGenerator not available" in reasons["ml_kem_768"]


def test_the_blocker_is_measured_now(walk):
    system = next(s for s in walk["dependencies-demo.cdx.json"]["systems"] if s["key"].startswith("server:"))
    assert all("measured on a public copy" in line["text"] for line in system["blocker_lines"])


def test_cyclonedx_and_spdx_give_the_same_answers(walk):
    def answers(view):
        return {label: [(c["answer"], c["label"], c["state"], c["agreement"]) for c in r["cells"]] for label, r in _rows(view).items()}
    assert answers(walk["dependencies-demo.cdx.json"]) == answers(walk["dependencies-demo.spdx.json"])

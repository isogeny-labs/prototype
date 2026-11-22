"""Phase 5a: Load demo projects. A "Demo" folder with one project per demo file, each with its first assessment and
the file already imported exactly as Import does it (Demo data label where the file is demo data). Twice adds nothing."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import PASSWORD, free_port

NAMES = ["Acme Pay", "Migration demo", "Multi-target", "Lab nginx (isolated mode)", "Real libraries (isolated mode)",
         "Real public servers (needs internet)"]


@pytest.fixture
def spare_client(tmp_path):
    """Demo mode, with every demo test server on a spare port (the demo files are written with these ports)."""
    s = Settings(data_dir=tmp_path / "data", demo_tls_port=free_port(), force_mode="demo",
                 extra_ports=(free_port(), free_port(), free_port()),
                 migration_ports=(free_port(), free_port(), free_port(), free_port(), free_port()),
                 lab_nginx_port=free_port())
    with TestClient(create_app(s)) as client:
        assert client.post("/api/setup", json={"password": PASSWORD}).status_code == 200
        yield client


@pytest.mark.slow
def test_load_demo_projects_makes_six_projects_with_their_files_and_twice_adds_nothing(spare_client):
    client = spare_client
    first = client.post("/api/demo-projects").json()
    assert first["added"] == NAMES and first["open_assessment_id"]
    assert first["summary"].startswith("Added 6 demo projects in the Demo folder")
    w = client.get("/api/workspace").json()
    demo = next(f for f in w["folders"] if f["name"] == "Demo")
    projects = {p["name"]: p for p in w["projects"] if p["folder_id"] == demo["id"]}
    assert sorted(projects) == sorted(NAMES)
    for p in projects.values():
        assert p["is_demo"] and p["assessments"] == 1 and p["latest"]["file"] is not None
        assert p["latest"]["status"]["key"] == "open"
    files = {name: p["latest"]["file"] for name, p in projects.items()}
    assert files["Acme Pay"]["filename"] == "acme-pay-cbom.json"
    assert files["Real public servers (needs internet)"]["filename"] == "migration-real-servers.csv"
    # The Demo data label follows the file, as Import decides it today: our own demo servers and components are demo
    # data; real libraries and real public servers are not.
    assert files["Acme Pay"]["is_demo"] and files["Migration demo"]["is_demo"] and files["Multi-target"]["is_demo"]
    assert not files["Real libraries (isolated mode)"]["is_demo"] and not files["Real public servers (needs internet)"]["is_demo"]
    # In demo mode, the files that need isolated mode say so, in Import's own words.
    assert any(n.startswith("Real libraries (isolated mode): Real software:") for n in first["notices"])
    # Nothing was verified: the real public servers have not been contacted.
    real = projects["Real public servers (needs internet)"]
    assert real["counts"]["claims"] is None
    # Twice adds nothing.
    again = client.post("/api/demo-projects").json()
    assert again["added"] == [] and again["summary"] == "The demo projects are already here. Nothing was added."
    assert len([p for p in client.get("/api/workspace").json()["projects"] if p["folder_id"] == demo["id"]]) == 6
    # An archived demo project is not made again either.
    client.post(f"/api/projects/{projects['Acme Pay']['id']}", json={"archived": True})
    assert client.post("/api/demo-projects").json()["added"] == []

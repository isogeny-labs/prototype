"""Phase 5a: folders and projects in a tree of any depth; rename, move and archive; nothing is ever deleted."""
import sqlite3

import pytest


def _workspace(client):
    return client.get("/api/workspace").json()


def test_the_organization_has_a_name_that_can_change(client):
    assert _workspace(client)["organization"] == "My organization"
    assert client.post("/api/organization", json={"name": "Acme Corp"}).json()["organization"] == "Acme Corp"
    assert client.post("/api/organization", json={"name": "   "}).status_code == 422


def test_folders_nest_to_any_depth_and_projects_sit_in_them(client):
    top = client.post("/api/folders", json={"name": "Payments"}).json()["id"]
    mid = client.post("/api/folders", json={"name": "EU", "parent_id": top}).json()["id"]
    low = client.post("/api/folders", json={"name": "Card processing", "parent_id": mid}).json()["id"]
    made = client.post("/api/projects", json={"name": "Acme Pay", "folder_id": low}).json()
    assert made["assessment_id"]                                    # a new project starts with its first assessment
    w = _workspace(client)
    p = next(x for x in w["projects"] if x["id"] == made["id"])
    assert [s["name"] for s in p["path"]] == ["Payments", "EU", "Card processing"]
    assert p["assessments"] == 1 and p["latest"]["title"] == "Assessment 1" and p["latest"]["file"] is None
    assert p["counts"] == {"claims": None, "tests": None, "fixes": None, "systems": None}   # nothing measured: no numbers
    folder = next(f for f in w["folders"] if f["id"] == low)
    assert [s["name"] for s in folder["path"]] == ["Payments", "EU"]


def test_rename_move_and_archive_folders_and_projects(client):
    a = client.post("/api/folders", json={"name": "A"}).json()["id"]
    b = client.post("/api/folders", json={"name": "B", "parent_id": a}).json()["id"]
    pid = client.post("/api/projects", json={"name": "Old name", "folder_id": b}).json()["id"]
    client.post(f"/api/projects/{pid}", json={"name": "New name"})
    client.post(f"/api/projects/{pid}", json={"move": True, "folder_id": None})   # to the top level
    client.post(f"/api/folders/{b}", json={"name": "B2", "move": True, "parent_id": None})
    client.post(f"/api/folders/{a}", json={"archived": True})
    w = _workspace(client)
    p = next(x for x in w["projects"] if x["id"] == pid)
    assert p["name"] == "New name" and p["folder_id"] is None and p["path"] == []
    folders = {f["id"]: f for f in w["folders"]}
    assert folders[b]["name"] == "B2" and folders[b]["parent_id"] is None
    assert folders[a]["archived"] is True                           # archived: still there, only hidden by the screens
    client.post(f"/api/folders/{a}", json={"archived": False})
    assert {f["id"]: f for f in _workspace(client)["folders"]}[a]["archived"] is False


def test_a_folder_cannot_go_inside_itself_or_its_own_folders(client):
    a = client.post("/api/folders", json={"name": "A"}).json()["id"]
    b = client.post("/api/folders", json={"name": "B", "parent_id": a}).json()["id"]
    c = client.post("/api/folders", json={"name": "C", "parent_id": b}).json()["id"]
    for target in (a, c):
        r = client.post(f"/api/folders/{a}", json={"move": True, "parent_id": target})
        assert r.status_code == 422 and "inside itself" in r.json()["error"]["message"]


def test_names_are_required_and_unknown_places_are_refused(client):
    assert client.post("/api/projects", json={"name": ""}).status_code == 422
    assert client.post("/api/projects", json={"name": "X", "folder_id": 999}).status_code == 404
    assert client.post("/api/folders", json={"name": "X", "parent_id": 999}).status_code == 404
    assert client.post("/api/projects/999", json={"name": "X"}).status_code == 404


def test_there_is_no_way_to_delete_and_the_database_refuses_it(client, settings):
    pid = client.post("/api/projects", json={"name": "Keep me"}).json()["id"]
    client.post("/api/folders", json={"name": "Keep me too"})
    assert client.delete(f"/api/projects/{pid}").status_code in (404, 405)
    con = sqlite3.connect(settings.db_path)
    try:
        for table in ("folders", "projects", "assessments"):
            with pytest.raises(sqlite3.DatabaseError, match="never deleted"):
                con.execute(f"DELETE FROM {table}")
    finally:
        con.close()


def test_every_new_route_needs_the_login(anon_client):
    for method, path in (("get", "/api/workspace"), ("post", "/api/folders"), ("post", "/api/projects"),
                         ("get", "/api/projects/1"), ("post", "/api/projects/1/assessments"), ("get", "/api/assessments/1"),
                         ("post", "/api/assessments/1"), ("post", "/api/demo-projects"), ("post", "/api/organization")):
        r = anon_client.get(path) if method == "get" else anon_client.post(path, json={})
        assert r.status_code == 401, path

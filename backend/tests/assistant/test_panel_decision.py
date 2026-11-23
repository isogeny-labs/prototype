"""Phase 6a: a decision made from the panel is recorded exactly like the same decision made on its page.

There is one decision route. The page's card sends it, and on Confirm the panel sends the very same request: the
proposal's id and the decision's key are what the panel's read holds. Here the same two decisions (an accept, and a
reject with a reason) are made on two copies of one assessment: on the first as the page sends them, on the second
as the panel sends them. The database rows, the Otto ledger's entries and the evidence file's part are then compared
field for field. Nothing in any record says "panel"."""

import json
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.db import OttoDecisionRow
from app.main import create_app
from app.otto import assurance
from conftest import PASSWORD, free_port
from tests.assistant import assistant_walk as made
from tests.otto import otto_helpers as helpers

pytestmark = [pytest.mark.needs_otto]
REASON = "Not this quarter"
# What differs between two copies for no other reason than when and where they were made.
TIMES = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)|\[\[time:[^\]]*\]\]|\d{1,2} [A-Z][a-z]+ \d{4}, \d{2}:\d{2} UTC"
)
HASHES = re.compile(r"\b[0-9a-f]{12,64}\b")


@pytest.fixture
def pack(tmp_path, monkeypatch):
    """One signed pack for every copy of the app in a test (each copy trusts its signer)."""
    files, keys = made.pack_files()
    helpers.trust(monkeypatch, tmp_path, keys)
    return files


def _client(folder, files) -> TestClient:
    updates = folder / "updates"
    updates.mkdir(parents=True)
    for name, data in files.items():
        (updates / name).write_bytes(data)
    settings = Settings(
        data_dir=folder / "data",
        demo_tls_port=free_port(),
        force_mode="demo",
        speed_rounds=25,
        speed_repeats=4,
        otto_updates_dir=updates,
        otto_recorded_dir=folder / "recorded",
    )
    return TestClient(create_app(settings))


def _start(client) -> tuple[int, int]:
    """Log in, bring the demo file in and install the pack: (the assessment, its plan)."""
    assert client.post("/api/setup", json={"password": PASSWORD}).status_code == 200
    client.post("/api/otto/packs/check")
    assert client.post("/api/otto/packs/install", json={"version": "2026.11.1"}).status_code == 200
    imp = client.post("/api/import/demo").json()
    plan = client.post(f"/api/import/{imp['id']}/plan").json()
    return imp["assessment_id"], plan["id"]


def _masked(value):
    """A record with what only says when and where it was made taken out: times, and fingerprints that rest on them."""
    text = json.dumps(value, sort_keys=True, default=str)
    return json.loads(HASHES.sub("<hash>", TIMES.sub("<time>", text)))


def _kept(client, assessment_id: int, plan_id: int) -> dict:
    """What the app keeps of the decisions: the database rows, the ledger's entries about them, and the evidence part."""
    lab = client.app.state.lab
    with lab.db() as db:
        rows = [
            {
                c.name: getattr(r, c.name)
                for c in OttoDecisionRow.__table__.columns
                if c.name not in ("id", "created_at")
            }
            for r in db.scalars(
                select(OttoDecisionRow).where(OttoDecisionRow.plan_id == plan_id).order_by(OttoDecisionRow.id)
            )
        ]
    ledger = assurance.Ledger(lab.settings.data_dir, assessment_id)
    entries = [ledger.about_proposal(o) for o in dict.fromkeys(r["objective_id"] for r in rows)]
    # (the part exactly as the evidence file takes it; the whole file, downloaded and verified with a decision from the
    # panel in it, is the end-to-end walk's to show: a download needs results, and running the plan is not this test's)
    part = [p for p in lab.otto_proposals_evidence(plan_id) if p["decisions"]]
    return {"rows": rows, "ledger": entries, "evidence": part}


def test_a_decision_from_the_panel_is_recorded_exactly_like_the_same_decision_on_its_page(tmp_path, pack):
    with _client(tmp_path / "page", pack) as page, _client(tmp_path / "panel", pack) as panel:
        # ---- the first copy: decided on the page (the ids are the ones the Advisories page's own cards hold)
        a_page, p_page = _start(page)
        cards = [p for p in page.get(f"/api/plans/{p_page}/otto/proposals").json()["proposals"] if p["kind"] == "check"]
        sent_by_page = [
            ("POST", f"/api/plans/{p_page}/otto/proposals/{cards[0]['id']}/accept", {}),
            ("POST", f"/api/plans/{p_page}/otto/proposals/{cards[1]['id']}/reject", {"reason": REASON}),
        ]
        for _, url, body in sent_by_page:
            assert page.post(url, json=body).status_code == 200

        # ---- the second copy: decided in the panel (the id and the decision's key come from the panel's own read)
        a_panel, p_panel = _start(panel)
        view = panel.get(f"/api/assessments/{a_panel}/assistant", params={"page": "checks"}).json()
        first, second = [e for e in view["on_page"]["entries"] if e["kind"] == "suggestion"][:2]
        accept = next(d for d in first["decisions"] if d["key"] == "accept")
        reject = next(d for d in second["decisions"] if d["key"] == "reject")
        assert accept["can"] and reject["can"] and reject["confirm"]["reason"]["max"] == 300
        sent_by_panel = [
            ("POST", f"/api/plans/{view['plan_id']}/otto/proposals/{first['id']}/{accept['key']}", {}),
            ("POST", f"/api/plans/{view['plan_id']}/otto/proposals/{second['id']}/{reject['key']}", {"reason": REASON}),
        ]
        # the request is the page's own: the same route, the same proposal, the same body
        assert sent_by_panel == sent_by_page and (a_page, p_page) == (a_panel, p_panel)
        for _, url, body in sent_by_panel:
            answer = panel.post(url, json=body)
            assert answer.status_code == 200
        # ... and the panel then shows what the page shows, in the same word
        after = panel.get(f"/api/assessments/{a_panel}/assistant", params={"page": "advisories"}).json()
        on_page = {
            p["id"]: p["status"]["word"] for p in panel.get(f"/api/plans/{p_panel}/otto/proposals").json()["proposals"]
        }
        in_panel = {e["id"]: e["badge"]["label"] for e in after["on_page"]["entries"] if e["kind"] == "suggestion"}
        assert in_panel[first["id"]] == on_page[first["id"]] == "Added"
        assert in_panel[second["id"]] == on_page[second["id"]] == f"Not added ({REASON})"

        # ---- what each copy kept, field for field
        kept_page, kept_panel = _kept(page, a_page, p_page), _kept(panel, a_panel, p_panel)
        assert len(kept_page["rows"]) == 2 and len(kept_page["ledger"]) == 2 and len(kept_page["evidence"]) == 2
        assert [r["decision"] for r in kept_page["rows"]] == ["accept", "reject"] and kept_page["rows"][1][
            "reason"
        ] == REASON
        assert _masked(kept_panel["rows"]) == _masked(kept_page["rows"])
        assert _masked(kept_panel["ledger"]) == _masked(kept_page["ledger"])
        assert _masked(kept_panel["evidence"]) == _masked(kept_page["evidence"])
        for name in (
            "rows",
            "ledger",
            "evidence",
        ):  # (only times and what rests on them were left out of the comparison)
            assert [sorted(r) if isinstance(r, dict) else None for r in kept_panel[name]] == [
                sorted(r) if isinstance(r, dict) else None for r in kept_page[name]
            ]
        # nothing kept anywhere says where the button was pressed
        assert not re.search(r"panel|assistant", json.dumps(kept_panel, default=str), re.I)


def test_the_panels_read_needs_the_login_and_refuses_what_is_not_a_page(tmp_path, pack):
    with _client(tmp_path / "one", pack) as client:
        assert client.get("/api/assessments/1/assistant", params={"page": "checks"}).status_code == 401
        assessment, plan = _start(client)
        ok = client.get(f"/api/assessments/{assessment}/assistant", params={"page": "checks", "item": "test-1"})
        assert ok.status_code == 200 and ok.json()["page"] == "checks" and ok.json()["plan_id"] == plan
        assert client.get(f"/api/assessments/{assessment}/assistant").json()["page"] == "overview"  # the default
        wrong = client.get(f"/api/assessments/{assessment}/assistant", params={"page": "settings"})
        assert wrong.status_code == 422 and "not part of an assessment" in wrong.json()["error"]["message"]
        assert client.get("/api/assessments/9999/assistant", params={"page": "checks"}).status_code == 404
        # it is a read: no other method reaches it
        assert client.post(f"/api/assessments/{assessment}/assistant", params={"page": "checks"}).status_code in (
            404,
            405,
        )
        # and a closed assessment can still be read
        client.post(f"/api/assessments/{assessment}", json={"close": True, "signed_off_by": "Sam Lee"})
        closed = client.get(f"/api/assessments/{assessment}/assistant", params={"page": "advisories"}).json()
        assert closed["notices"] and all(not d["can"] for e in closed["on_page"]["entries"] for d in e["decisions"])

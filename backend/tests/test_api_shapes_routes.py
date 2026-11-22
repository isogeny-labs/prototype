"""The routes no other test calls through the web (phase 4c+), called here once each, so that the answer of every
route that declares a shape has been checked against it (tests/api_shapes.py does the checking). One walk through
the Acme Pay demo, by the same requests the screens send."""

import time

import pytest

from conftest import play_back_speed

pytestmark = pytest.mark.slow  # a whole demo walk with a retest, a proof, a merge and a server change


def _wait(predicate, seconds: float = 300.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.2)
    raise AssertionError("still busy after the time limit")


def test_every_route_with_a_shape_is_called_once_through_the_web(client):
    import api_shapes

    lab = client.app.state.lab
    play_back_speed(lab)
    imp = client.post("/api/import/demo").json()
    address = imp["addresses"][0]["address"]
    assert (
        client.post(
            f"/api/import/{imp['id']}/confirm-address", json={"address": address, "confirmed": True}
        ).status_code
        == 200
    )
    pid = client.post(f"/api/import/{imp['id']}/plan").json()["id"]
    assert client.post(f"/api/plans/{pid}/run-all").status_code == 200
    _wait(lambda: not client.get(f"/api/plans/{pid}/lab").json()["busy"])

    # Evidence Lab: Retest new version, then Download evidence
    assert client.post(f"/api/plans/{pid}/retest", json={"version": "1.4.3"}).status_code == 200
    _wait(lambda: not client.get(f"/api/plans/{pid}/lab").json()["busy"])
    assert client.post(f"/api/plans/{pid}/evidence").status_code == 200

    # Fixes: connect, the proof runs by itself; pull request, approve, merge, Retest now
    assert client.post(f"/api/plans/{pid}/fixes/connect").status_code == 200
    _wait(lambda: not client.get(f"/api/plans/{pid}/fixes").json()["busy"])
    fix = next(f for f in client.get(f"/api/plans/{pid}/fixes").json()["fixes"] if f["kind"] == "code")["id"]
    assert client.post(f"/api/plans/{pid}/fixes/{fix}/pull-request", json={"reviewers": ["you"]}).status_code == 200
    assert client.post(f"/api/plans/{pid}/fixes/{fix}/approve", json={"reviewer": "you"}).status_code == 200
    assert client.post(f"/api/plans/{pid}/fixes/{fix}/merge").status_code == 200
    assert client.post(f"/api/plans/{pid}/fixes/{fix}/retest").status_code == 200
    _wait(lambda: not client.get(f"/api/plans/{pid}/lab").json()["busy"])

    # The Acme Pay server's TLS change: try on a test copy, ask for approval, approve, apply, roll back
    box = next(f for f in client.get(f"/api/plans/{pid}/fixes").json()["fixes"] if f["id"].startswith("fix-tls"))[
        "change_box"
    ]
    key = box["id"]
    assert client.post(f"/api/plans/{pid}/changes/try", json={"change": key}).status_code == 200
    lab.wait_until_changes_idle(pid)
    assert (
        client.post(f"/api/plans/{pid}/changes/ask-approval", json={"change": key, "reviewers": ["you"]}).status_code
        == 200
    )
    assert client.post(f"/api/plans/{pid}/changes/approve", json={"change": key, "reviewer": "you"}).status_code == 200
    assert client.post(f"/api/plans/{pid}/changes/apply", json={"change": key}).status_code == 200
    lab.wait_until_changes_idle(pid)
    assert client.post(f"/api/plans/{pid}/changes/rollback", json={"change": key}).status_code == 200
    lab.wait_until_changes_idle(pid)

    # Migration: measure, then the person's own choice for the signing program
    assert client.post(f"/api/plans/{pid}/migration/measure").status_code == 200
    _wait(lambda: not client.get(f"/api/import/{imp['id']}/migration").json()["busy"])
    systems = client.get(f"/api/import/{imp['id']}/migration").json()["systems"]
    program = next(s for s in systems if s["name"].startswith("acme-sign"))
    answer = client.post(
        f"/api/plans/{pid}/migration/choice",
        json={
            "system": program["key"],
            "option": "keep",
            "reason": "A test of the route.",
            "review_date": "2027-06-30",
        },
    )
    assert answer.status_code == 200, answer.text

    # Each of these routes has now answered once and its answer fitted its shape. Run proof again is offered only
    # after a failed or interrupted proof; it answers with the same Fixes view as connect, which is checked above.
    called = {
        ("POST", p)
        for p in (
            "/api/plans/{plan_id}/retest",
            "/api/plans/{plan_id}/evidence",
            "/api/plans/{plan_id}/fixes/connect",
            "/api/plans/{plan_id}/fixes/{fix_id}/pull-request",
            "/api/plans/{plan_id}/fixes/{fix_id}/approve",
            "/api/plans/{plan_id}/fixes/{fix_id}/merge",
            "/api/plans/{plan_id}/fixes/{fix_id}/retest",
            "/api/plans/{plan_id}/changes/try",
            "/api/plans/{plan_id}/changes/ask-approval",
            "/api/plans/{plan_id}/changes/approve",
            "/api/plans/{plan_id}/changes/apply",
            "/api/plans/{plan_id}/changes/rollback",
            "/api/plans/{plan_id}/migration/measure",
            "/api/plans/{plan_id}/migration/choice",
        )
    }
    assert called <= api_shapes.DECLARED and called <= api_shapes.CHECKED, sorted(called - api_shapes.CHECKED)

"""The 5c fixes: an advisory that first arrived with the most recently installed test pack carries the tag "New".

"Arrived with test pack 2026.11.2" is what the tag says on hover and to a screen reader. An advisory that a later pack
only updates arrived earlier, so it is not new. With one pack installed, every advisory is new. A closed assessment
uses the packs that were installed when it was closed. The tag is information: it decides nothing."""
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import otto_helpers as helpers
from app.otto import packs
from app.web import models
from conftest import demo_plan
from tests.view_helpers import problems

NEW_1 = {"label": "New", "title": "Arrived with test pack 2026.11.1"}
NEW_2 = {"label": "New", "title": "Arrived with test pack 2026.11.2"}


def _lab(tmp_path, monkeypatch):
    """Two packs in the updates folder. The second brings one advisory (CVE-2024-42460) and holds the first pack's
    CVE-2019-14853 again, updated (it now reads "Not offered"); CVE-2022-21449 is in the first pack only."""
    key = Ed25519PrivateKey.generate()
    first, public = helpers.make_pack("2026.11.1", None, [helpers.pack_advisory(),
                                                         helpers.pack_advisory("CVE-2019-14853", "Stops on a bad signature", state="none")], key)
    one = packs.read_envelope(first, {public: (helpers.SIGNER, False)})
    second, _ = helpers.make_pack("2026.11.2", one.fingerprint, [
        helpers.pack_advisory("CVE-2024-42460", "Missing leading zero accepted", flags=("MissingZero",)),
        helpers.pack_advisory("CVE-2019-14853", "Stops on a bad signature", flags=("BerEncodedSignature",), state="not_offered")], key)
    return helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": first, "2026.11.2.json": second}, [public])


def _new(view: dict) -> dict:
    return {row["id"]: row["new"] for row in view["rows"]}


@pytest.mark.needs_otto
def test_with_one_pack_every_advisory_is_new_and_the_tag_names_that_pack(tmp_path, monkeypatch):
    lab = _lab(tmp_path, monkeypatch)
    try:
        plan = demo_plan(lab)
        lab.check_pack_updates()
        lab.install_pack("2026.11.1")
        view = lab.advisories_view(plan.id)
        assert problems(view, models.AdvisoriesView, "advisories") == []
        assert _new(view) == {"CVE-2022-21449": NEW_1, "CVE-2019-14853": NEW_1}
    finally:
        lab.stop()


@pytest.mark.needs_otto
def test_after_a_second_pack_only_what_it_brought_is_new_and_what_it_only_updates_is_not(tmp_path, monkeypatch):
    lab = _lab(tmp_path, monkeypatch)
    try:
        plan = demo_plan(lab)
        lab.check_pack_updates()
        lab.install_pack("2026.11.1")
        lab.install_pack("2026.11.2")
        view = lab.advisories_view(plan.id)
        assert problems(view, models.AdvisoriesView, "advisories") == []
        assert _new(view) == {"CVE-2022-21449": None, "CVE-2019-14853": None, "CVE-2024-42460": NEW_2}
        rows = {row["id"]: row for row in view["rows"]}
        # the updated advisory is shown as the newer pack has it, and still counts as having arrived with the first
        assert rows["CVE-2019-14853"]["pack"] == "2026.11.2" and rows["CVE-2019-14853"]["test"]["label"] == "Not offered"
        assert rows["CVE-2024-42460"]["pack"] == "2026.11.2" and rows["CVE-2022-21449"]["pack"] == "2026.11.1"
        # the tag is information only: it adds no button and changes no count
        assert view["waiting"]["count"] == 2 and "new" not in view["waiting"]
    finally:
        lab.stop()


@pytest.mark.needs_otto
def test_a_closed_assessment_uses_the_packs_installed_when_it_was_closed(tmp_path, monkeypatch):
    lab = _lab(tmp_path, monkeypatch)
    try:
        plan = demo_plan(lab)
        lab.check_pack_updates()
        lab.install_pack("2026.11.1")
        assessment = lab.assessment_for(plan_id=plan.id)
        lab.update_assessment(assessment.id, {"close": True, "signed_off_by": "Sam Lee", "note": None})
        lab.install_pack("2026.11.2")                       # the installation moves on; the closed assessment does not
        assert _new(lab.advisories_view(plan.id)) == {"CVE-2022-21449": NEW_1, "CVE-2019-14853": NEW_1}
        newer = demo_plan(lab)                              # an assessment that is open sees both packs
        assert _new(lab.advisories_view(newer.id)) == {"CVE-2022-21449": None, "CVE-2019-14853": None, "CVE-2024-42460": NEW_2}
    finally:
        lab.stop()


@pytest.mark.needs_otto
def test_with_no_pack_there_is_nothing_to_tag(tmp_path, monkeypatch):
    lab = _lab(tmp_path, monkeypatch)
    try:
        plan = demo_plan(lab)
        assert lab.advisories_view(plan.id)["rows"] == []
    finally:
        lab.stop()

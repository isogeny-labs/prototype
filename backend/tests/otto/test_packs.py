"""Phase 5c, step 5: test packs. A pack is data, signed like an update. It is taken only when the signature holds,
the signer is trusted, the shape is exact and it follows the pack before it; packs install in order and are never
removed. (These tests use packs made for the tests; the two shipped packs have their own test.)"""

import json
import random
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text

import otto_fuzz
import otto_helpers as helpers
from app.db import OttoPackRow
from app.errors import BadRequest, Conflict
from app.otto import model, packs

# None of this needs the Otto harness: a pack is read, checked and installed by the app's own code.


def _two_packs():
    key = Ed25519PrivateKey.generate()
    first, public = helpers.make_pack(
        "2026.11.1",
        None,
        [helpers.pack_advisory(), helpers.pack_advisory("CVE-2019-14853", "Stops on a bad signature", state="none")],
        key,
    )
    one = packs.read_envelope(first, {public: (helpers.SIGNER, False)})
    second, _ = helpers.make_pack(
        "2026.11.2",
        one.fingerprint,
        [
            helpers.pack_advisory("CVE-2024-42460", "Missing leading zero accepted", flags=("MissingZero",)),
            helpers.pack_advisory(
                "CVE-2024-42461", "Loose length accepted", flags=("BerEncodedSignature",), state="not_offered"
            ),
        ],
        key,
    )
    return first, second, public


def test_a_pack_reads_back_and_says_what_it_holds():
    first, _, public = _two_packs()
    pack = packs.read_envelope(first, {public: (helpers.SIGNER, False)})
    assert pack.version == "2026.11.1" and pack.signer == helpers.SIGNER and not pack.made_here
    assert [a["id"] for a in pack.pack["advisories"]] == ["CVE-2022-21449", "CVE-2019-14853"] and len(
        pack.pack["tests"]
    ) == 1
    assert pack.design(pack.advisory("CVE-2022-21449")["test"]["design_sha256"])["advisory"] == "CVE-2022-21449"
    assert pack.design("0" * 64) is None and pack.advisory("CVE-0000-0000") is None


@pytest.mark.parametrize(
    "change, words",
    [
        (
            lambda e: e["pack"]["advisories"][0]["reading"].__setitem__("plain_name", "Something else"),
            "changed after it was signed",
        ),
        (lambda e: e.__setitem__("signature", "0" * 128), "signature does not hold"),
        (lambda e: e.__setitem__("fingerprint", "0" * 64), "changed after it was signed"),
        (lambda e: e.__setitem__("extra", 1), "not a signed test pack"),
        (lambda e: e.__setitem__("public_key", "zz"), "not in the form"),
    ],
)
def test_a_pack_with_one_thing_changed_is_refused(change, words):
    first, _, public = _two_packs()
    envelope = json.loads(first)
    change(envelope)
    from app.canonical import canonical_bytes

    with pytest.raises(packs.PackError) as refused:
        packs.read_envelope(canonical_bytes(envelope), {public: (helpers.SIGNER, False)})
    assert words in str(refused.value)


def test_a_pack_signed_by_an_unknown_key_is_refused():
    first, _, _ = _two_packs()
    with pytest.raises(packs.PackError) as refused:
        packs.read_envelope(first, {"0" * 64: ("someone else", False)})
    assert "does not trust" in str(refused.value)


def test_a_validly_signed_pack_that_holds_something_it_must_not_is_refused():
    """The signature is not enough: every design must be one this version can run, and nothing extra may ride along."""
    key = Ed25519PrivateKey.generate()
    entry, made = helpers.pack_advisory()
    for spoil, words in (
        (lambda e, d: d.__setitem__("control", "none"), "can't be run by this version"),
        (lambda e, d: d["cases"]["ids"].append("1"), "can't be run by this version"),
        (lambda e, d: e.__setitem__("command", "rm -rf /"), "exactly the fields"),
        (lambda e, d: e["test"]["trial"].__setitem__("outcome", "refuted"), "without a trial that held"),
        (lambda e, d: e["fix"]["trial"].__setitem__("replayed", False), "called proven without"),
        (lambda e, d: e["steps"][0].__setitem__("answer", "another answer"), "does not match its fingerprint"),
    ):
        e, d = json.loads(json.dumps(entry)), json.loads(json.dumps(made))
        spoil(e, d)
        if d != made:
            e["test"]["design_sha256"] = (
                helpers.designs.design_sha256(d)
                if d["control"] == "accept_all_verifier" and d["cases"]["ids"] == made["cases"]["ids"]
                else e["test"]["design_sha256"]
            )
        raw, public = helpers.make_pack("2026.11.1", None, [(e, d)], key) if True else (b"", "")
        with pytest.raises(packs.PackError) as refused:
            packs.read_envelope(raw, {public: (helpers.SIGNER, False)})
        assert words in str(refused.value), str(refused.value)


def test_damaged_pack_files_are_read_or_refused_plainly():
    """Seeded fuzz on the pack reader: a damaged copy is refused with one PackError, or (rarely) still the same pack."""
    first, _, public = _two_packs()
    keys = {public: (helpers.SIGNER, False)}
    doc = json.loads(first)
    rng = random.Random(20261119)
    outcomes = {"read": 0, "refused": 0}
    for n in range(300):
        data = otto_fuzz.damage_bytes(rng, first) if n % 2 else json.dumps(otto_fuzz.damage_json(rng, doc)).encode()
        start = time.monotonic()
        try:
            pack = packs.read_envelope(data, keys)
            assert pack.fingerprint == doc["fingerprint"]  # only an untouched pack ever reads
            outcomes["read"] += 1
        except packs.PackError as exc:
            assert str(exc) and len(str(exc)) < 400
            outcomes["refused"] += 1
        assert time.monotonic() - start < 2.0
    assert outcomes["refused"] >= 295


def test_a_signed_pack_that_is_damaged_inside_is_refused_plainly():
    """Seeded fuzz of the pack's shape check itself. The damage is inside the pack and the pack is then signed again
    with a trusted key, so its signature holds: only the shape check stands between such a pack and the app. A copy
    is refused with one plain sentence, or (where the damage left a well-formed pack) read; never anything else."""
    key = Ed25519PrivateKey.generate()
    keys = {helpers.public_hex(key): (helpers.SIGNER, False)}
    entries = [
        helpers.pack_advisory(),
        helpers.pack_advisory("CVE-2019-14853", "Stops on a bad signature", state="none"),
        helpers.pack_advisory(
            "CVE-2024-42460", "Missing leading zero accepted", flags=("MissingZero",), fix_state="not_proven"
        ),
    ]
    whole = json.loads(helpers.make_pack("2026.11.1", None, entries, key)[0])["pack"]
    assert packs.read_envelope(helpers.sign_pack(whole, key), keys).version == "2026.11.1"
    rng = random.Random(20261120)
    outcomes = {"read": 0, "refused": 0, "asked directly": 0}
    for _ in range(600):
        damaged = otto_fuzz.damage_json(rng, whole)
        for _ in range(rng.randrange(3)):
            damaged = otto_fuzz.damage_json(rng, damaged)
        try:
            raw = helpers.sign_pack(damaged, key)
        except (
            TypeError,
            ValueError,
        ):  # a value the canonical form can't hold (a float): the shape check is asked directly
            raw = None
            outcomes["asked directly"] += 1
        start = time.monotonic()
        try:
            if raw is None:
                packs.check_pack(damaged)
            else:
                packs.read_envelope(raw, keys)
            outcomes["read"] += 1
        except packs.PackError as exc:
            assert str(exc) and len(str(exc)) < 400
            outcomes["refused"] += 1
        assert time.monotonic() - start < 2.0
    assert outcomes["refused"] > 450 and outcomes["refused"] + outcomes["read"] == 600, outcomes


def test_a_pack_installed_by_an_earlier_build_that_can_t_be_read_is_said_plainly(tmp_path, monkeypatch):
    """A data folder can hold a pack from an earlier build whose form has changed since (here: its sources have no
    `read_from` yet). It is left out everywhere, never half-used, and Settings says so instead of "No test pack is
    installed yet"; nothing can be installed after it in that folder."""
    key = Ed25519PrivateKey.generate()
    public = helpers.public_hex(key)
    current = json.loads(helpers.make_pack("2026.11.1", None, [helpers.pack_advisory()], key)[0])
    older = json.loads(json.dumps(current["pack"]))
    for source in older["advisories"][0]["sources"]:
        del source["read_from"]
    stored = json.loads(helpers.sign_pack(older, key))
    with pytest.raises(packs.PackError):
        packs.read_envelope(helpers.sign_pack(older, key), {public: (helpers.SIGNER, False)})
    lab = helpers.lab_with_packs(
        tmp_path, monkeypatch, {"2026.11.1.json": helpers.sign_pack(current["pack"], key)}, [public]
    )
    try:
        with lab.db() as db:
            db.add(
                OttoPackRow(
                    version="2026.11.1",
                    fingerprint=stored["fingerprint"],
                    public_key=public,
                    signer=helpers.SIGNER,
                    made_here=False,
                    built_at=older["built_at"],
                    envelope=json.dumps(stored),
                )
            )
            db.commit()
        view = lab.check_pack_updates()["packs"]
        assert (
            view["installed"] == []
            and view["installed_line"] == "No installed test pack can be read by this version of the app."
        )
        assert (
            "Test pack 2026.11.1, installed here earlier, can't be read by this version of the app"
            in view["unreadable_line"]
        )
        assert "move the data folder away" in view["unreadable_line"]
        assert view["update"] is None  # the rebuilt 2026.11.1 in the updates folder does not follow it
        with pytest.raises(Conflict):
            lab.install_pack("2026.11.1")
    finally:
        lab.stop()
    (tmp_path / "fresh").mkdir()
    fresh = helpers.lab_with_packs(tmp_path / "fresh", monkeypatch, {}, [public])
    try:
        assert fresh.otto_view()["packs"]["unreadable_line"] is None
    finally:
        fresh.stop()


def test_packs_install_in_order_and_are_never_removed(tmp_path, monkeypatch):
    first, second, public = _two_packs()
    lab = helpers.lab_with_packs(
        tmp_path, monkeypatch, {"2026.11.1.json": first, "2026.11.2.json": second, "notes.txt": b"x"}, [public]
    )
    try:
        view = lab.otto_view()
        assert view["packs"]["installed"] == [] and view["packs"]["installed_line"] == "No test pack is installed yet."
        assert (
            view["packs"]["update"] is None and view["packs"]["checked_line"] is None
        )  # nothing is looked up until a person asks
        found = lab.check_pack_updates()
        assert (
            found["packs"]["update"]["version"] == "2026.11.1"
            and "1 more pack follows" in found["packs"]["checked_line"]
        )
        dialog = found["packs"]["update"]["dialog"]
        assert (
            dialog["confirm"] == "Install"
            and dialog["cancel"] == "Cancel"
            and any("Blank signature accepted (CVE-2022-21449): Test ready" in line for line in dialog["lines"])
        )
        with pytest.raises(Conflict) as out_of_order:
            lab.install_pack("2026.11.2")  # the second pack can't go first
        assert "can't be installed now" in str(out_of_order.value)
        after = lab.install_pack("2026.11.1")
        assert [p["version"] for p in after["packs"]["installed"]] == ["2026.11.1"] and after["packs"]["update"][
            "version"
        ] == "2026.11.2"
        with pytest.raises(Conflict):
            lab.install_pack("2026.11.1")  # not twice
        done = lab.install_pack("2026.11.2")
        assert [p["version"] for p in done["packs"]["installed"]] == ["2026.11.1", "2026.11.2"] and done["packs"][
            "update"
        ] is None
        assert done["packs"]["checked_line"] == "No newer test pack in the updates folder."
        assert done["packs"]["counts_line"] == "4 advisories and 2 tests in 2 installed packs."
        with lab.db() as db:  # the database itself refuses a removal or a change
            for statement in ("DELETE FROM otto_packs", "UPDATE otto_packs SET version = '1.0.0'"):
                with pytest.raises(Exception) as kept:
                    db.execute(text(statement))
                    db.commit()
                assert "append-only" in str(kept.value)
                db.rollback()
    finally:
        lab.stop()


def test_a_bad_file_in_the_updates_folder_is_named_and_left_alone(tmp_path, monkeypatch):
    first, second, public = _two_packs()
    broken = first.replace(b"Blank signature accepted", b"Blank signature rejected", 1)
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, {"2026.11.1.json": broken, "2026.11.2.json": second}, [public])
    try:
        view = lab.check_pack_updates()
        assert view["packs"]["update"] is None
        reasons = {r["file"]: r["reason"] for r in view["packs"]["refused"]}
        assert "changed after it was signed" in reasons["2026.11.1.json"]
        assert "follows an earlier pack that is not installed" in reasons["2026.11.2.json"]
    finally:
        lab.stop()


def test_live_otto_can_be_turned_on_only_with_a_key_and_the_limit_is_kept(tmp_path, monkeypatch):
    monkeypatch.delenv(model.KEY_ENV, raising=False)
    lab = helpers.lab_with_packs(tmp_path, monkeypatch, {}, [])
    try:
        view = lab.otto_view()["live"]
        assert view["key_present"] is False and view["switch"] == {
            "label": "Use live Claude",
            "on": False,
            "can_turn_on": False,
            "blocked_reason": "This can be turned on only when an API key is present.",
        }
        assert view["limit"]["value"] == "2.00" and "recorded during the build" in view["status_line"]
        with pytest.raises(Conflict) as no_key:
            lab.set_live_otto(on=True)
        assert "needs an API key" in str(no_key.value) and not lab.otto_live_ready()
        assert lab.set_live_otto(limit="3.5")["live"]["limit"]["value"] == "3.50"
        for bad in ("0", "abc", "-1", "1001", "2.505", ""):
            with pytest.raises(BadRequest):
                lab.set_live_otto(limit=bad)
        assert lab.otto_model().budget.limit_nano == 3_500_000_000 and not lab.otto_model().live_ready
        # with a key present the switch can be turned on, and off again; the key itself is never in the view
        monkeypatch.setenv(model.KEY_ENV, "made-up-key-for-tests-0123456789")
        on = lab.set_live_otto(on=True)
        assert (
            on["live"]["switch"]["on"]
            and on["live"]["key_present"]
            and on["answers"] == {"line": "Live: Claude, through your key", "live": True}
        )
        assert "made-up-key" not in json.dumps(on) and lab.otto_live_ready() and lab.otto_model().live_ready
        assert not lab.otto_model(live=False).live_ready  # a page that is only shown never makes a live call
        monkeypatch.delenv(model.KEY_ENV)
        without = lab.otto_view()
        assert (
            without["live"]["switch"]["on"]
            and not without["answers"]["live"]
            and "no API key is set" in without["live"]["status_line"]
        )
        assert lab.set_live_otto(on=False)["live"]["switch"]["on"] is False
    finally:
        lab.stop()

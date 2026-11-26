"""The Observatory's map on the Acme Pay demo, stage by stage: the file just brought in, the dependency list added,
after Verify, after Run all and after Measure status.

At every stage the boxes, ties, lines and gaps are exactly what the two demo files support (each is checked against the
files themselves, read here apart from the app); every result word on the map is the word its own page shows; every
link opens; the four counts are the Overview's; and no sentence rates anything.

One walk for the file. Its first three stages need no test run and are made at once (about a second), so everything
about them is in the everyday set. Run all and Measure status are made the first time a test asks for a later stage
(`walk.stage`), and those tests are in the slow set: with them the walk takes about eight seconds. A retest, an Apply
and a Change watch run are in test_observatory_later.py (slow set)."""

from __future__ import annotations

import pytest

from app.observatory import build
from app.present import observatory as words
from app.present import source as present_source
from tests.conftest import make_lab
from tests.observatory import observatory_walk as W

LABELS = {"live": "Observed live", "lab": "Proven in the lab", "file": "From your file", "published": "Published"}
EARLY, LATER = ("imported", "listed", "verified"), ("ran", "measured")
STAGES = [*EARLY, *(pytest.param(stage, marks=pytest.mark.slow) for stage in LATER)]
SERVICE = "Acme Pay token-signing service (demo data) 1.0.0"
ENDPOINT = W.CBOM["services"][0]["name"]


class Walk:
    def __init__(self, lab):
        self.lab = lab
        self.plan = plan = W.start(lab, small=True)
        # (a box's panel and the Overview are a read each: they are kept where a test reads them, to keep the walk short)
        self.at = {"imported": W.snapshot(lab, plan, panels=False)}
        W.add_list(lab, plan)
        self.at["listed"] = W.snapshot(lab, plan, overview=False)
        lab.verify(plan.imp["id"])
        self.at["verified"] = W.snapshot(lab, plan, overview=False)
        self._known: tuple[int, dict] | None = None

    def stage(self, name: str):
        if name not in self.at:
            lab, plan = self.lab, self.plan
            lab.run_all(plan.id)
            lab.wait_until_idle(plan.id, 240)
            self.at["ran"] = W.snapshot(lab, plan, panels=False, overview=False)
            lab.measure_migration(plan.id)
            lab.wait_until_measured(plan.id, 240)
            self.at["measured"] = W.snapshot(lab, plan)
        return self.at[name]

    @property
    def known(self) -> dict:
        """What a link can open, as the assessment stands now (read again after the walk has gone on)."""
        if self._known is None or self._known[0] != len(self.at):
            self._known = (len(self.at), W.known(self.lab, self.plan))
        return self._known[1]


@pytest.fixture(scope="module")
def walk(tmp_path_factory):
    lab = make_lab(tmp_path_factory.mktemp("observatory-map"))
    try:
        yield Walk(lab)
    finally:
        lab.stop()


# ---------------------------------------------------------------- the boxes, the ties and the lines, against the files


def test_the_scanner_file_alone_gives_the_service_its_endpoint_and_its_program(walk):
    view, plan = walk.at["imported"].view, walk.plan
    described = W.CBOM["metadata"]["component"]
    (service,) = view["services"]
    assert (service["key"], service["title"], service["version"]) == (
        "service",
        described["name"],
        described["version"],
    )
    assert service["sub"] == "Named in your scanner file" and service["in_files"] == ["scanner"] and service["is_demo"]
    # one box for the service's one endpoint (its address) and one for the one signing program: nothing else
    assert [(b["key"], b["kind"], b["title"]) for b in service["boxes"]] == [
        (plan.server, "server", ENDPOINT),
        (plan.program, "program", "acme-sign 1.4.2"),
    ]
    server, program = service["boxes"]
    assert server["sub"] == f"Server · {plan.address}" and server["address"] == plan.address
    assert program["sub"] == "Signing program · in your scanner file"
    assert server["ties"] == program["ties"] == [] and view["libraries"] == []
    assert view["libraries_note"]["sub"] == "Not brought in yet"
    assert view["libraries_note"]["link"] == {"page": "migration/dependencies", "item": None}
    assert view["structure_note"] is None and view["not_drawn"] is None


def test_the_two_files_name_the_same_service_and_the_map_says_so(walk):
    view = walk.at["listed"].view
    scanner, listed = W.CBOM["metadata"]["component"], W.LISTED["metadata"]["component"]
    assert (scanner["name"], scanner["version"]) == (listed["name"], listed["version"])  # what the files say
    (service,) = view["services"]  # ... so they are one box, and it says why
    assert service["sub"] == "Named in both files, with the same name and version"
    assert service["in_files"] == ["scanner", "dependencies"] and view["libraries_note"] is None


def test_each_top_entry_of_the_dependency_list_is_a_box_and_only_the_one_the_files_tie_is_merged(walk):
    view, plan = walk.at["listed"].view, walk.plan
    tops = W.listed_tops()
    assert sorted(tops) == ["acme-ledger", "acme-pay-server", "acme-sign"]
    # acme-sign 1.4.2 is in both files with the same name and version: the same box as the scanner file's program
    program = W.box(view, plan.program)
    assert (tops["acme-sign"]["name"], tops["acme-sign"]["version"]) == ("acme-sign", "1.4.2")
    assert program["in_files"] == ["scanner", "dependencies"] and program["sub"] == "Signing program · in both files"
    assert [(t["label"], t["source"]) for t in program["ties"]] == [("acme-sign 1.4.2", "name_version")]
    assert program["ties"][0]["words"] == (
        "In both files: acme-sign 1.4.2 in your dependency list is tied to it by name and version."
    )
    # the other two are tied to nothing: a box each, with nothing observed or run, no tag and no spot
    for key in ("acme-pay-server", "acme-ledger"):
        own = W.box(view, "top:" + key)
        assert own["kind"] == "own_software" and own["title"] == f"{tops[key]['name']} {tops[key]['version']}"
        assert own["sub"] == "Your software · in your dependency list" and own["in_files"] == ["dependencies"]
        assert own["observed"] is False and own["tag"] is None and own["spots"] == [] and own["ties"] == []
        # ... and the note is built from the real names of what it could be tied to
        assert own["note"] == f"Not tied to {ENDPOINT} or to acme-sign 1.4.2."
    assert [b["key"] for b in W.boxes(view)] == [plan.server, plan.program, "top:acme-pay-server", "top:acme-ledger"]
    assert W.box(view, plan.server)["in_files"] == ["scanner"] and W.box(view, plan.server)["ties"] == []


def test_the_certificate_and_acme_sign_both_use_the_one_algorithm_the_file_names(walk):
    view, plan = walk.at["listed"].view, walk.plan
    (algorithm,) = view["algorithms"]  # the file names one algorithm
    named = [c for c in W.CBOM["components"] if (c.get("cryptoProperties") or {}).get("assetType") == "algorithm"]
    assert [c["bom-ref"] for c in named] == ["alg-ecdsa-p256"]
    assert algorithm["key"] == "algorithm:alg-ecdsa-p256"
    assert (algorithm["plain"], algorithm["technical"]) == ("Classical signatures", "ECDSA P-256")  # plain name first
    assert algorithm["uses"] == [
        {"box": plan.server, "through": "certificate"},
        {"box": plan.program, "through": "signature"},
    ]
    assert algorithm["used"] == (
        f"Used in 2 places: the certificate on {plan.address} and the signatures of acme-sign 1.4.2."
    )
    # the file itself leads from the endpoint, through its certificate, and from acme-sign, to that algorithm
    assert W.file_says_uses("svc-token-signing", "cert-server") and W.file_says_uses("cert-server", "alg-ecdsa-p256")
    assert W.file_says_uses("lib-acme-sign", "alg-ecdsa-p256")


def test_the_libraries_are_grouped_under_the_top_entry_the_list_puts_them_under(walk):
    view = walk.at["listed"].view
    shown = {g["key"]: g for g in view["libraries"]}
    assert sorted(shown) == ["libraries:acme-ledger", "libraries:acme-pay-server"]  # acme-sign lists none
    assert W.libraries_under("acme-sign") == []
    names = {c["bom-ref"]: f"{c['name']} {c['version']}" for c in W.LISTED["components"]}
    rows = {r["label"]: r for g in walk.at["listed"].dependencies["groups"] for r in g["rows"]}
    for top, n in (("acme-ledger", 8), ("acme-pay-server", 2)):
        group = shown["libraries:" + top]
        under = W.libraries_under(top)
        assert len(under) == n == group["count"] and group["owner"] == "top:" + top
        assert group["title"] == f"{names[top]}'s libraries · {n}" and group["sub"] == "From your dependency list"
        # the first few are listed with Dependencies' own summary of their answers and its tag; the rest are a link
        assert [r["label"] for r in group["rows"]] == [names[k] for k in sorted(under, key=list(names).index)][:3]
        for r in group["rows"]:
            mine = rows[r["label"]]
            assert (r["answers_short"], r["via_words"]) == (mine["answers_short"], mine["via_words"])
            assert r["tag"] == present_source.of_answers(mine["cells"])
            assert r["link"] == {"page": "migration/dependencies", "item": mine["id"]}
        assert (group["more"] or {}).get("count") == (n - 3 if n > 3 else None)
    assert shown["libraries:acme-ledger"]["more"]["label"] == "5 more"
    assert shown["libraries:acme-ledger"]["more"]["link"] == {"page": "migration/dependencies", "item": None}
    openssl = next(r for r in shown["libraries:acme-pay-server"]["rows"] if r["label"] == "openssl 3.0.22")
    assert (openssl["answers_short"], openssl["via_words"], openssl["tag"]["key"]) == (
        "No to all three",
        "through python 3.12.3",
        "published",
    )


@pytest.mark.parametrize("stage", STAGES)
def test_every_line_is_one_the_files_state_and_none_ties_an_untied_entry_to_a_server(walk, stage):
    plan, view = walk.plan, walk.stage(stage).view
    uses = {
        (plan.server, "algorithm:alg-ecdsa-p256", "uses", "its certificate"),
        (plan.program, "algorithm:alg-ecdsa-p256", "uses", "signs with"),
    }
    libraries = {
        ("top:acme-pay-server", "libraries:acme-pay-server", "uses", "uses 2 libraries"),
        ("top:acme-ledger", "libraries:acme-ledger", "uses", "uses 8 libraries"),
    }
    ask = {("clients", plan.server, "ask", "?")}
    live = {("this_computer", plan.server, "live", "TLS · 1.3 and 1.2 accepted")}
    assert W.lines(view) == {
        "imported": uses | ask,
        "listed": uses | libraries | ask,
    }.get(stage, uses | libraries | ask | live)
    known = (
        {b["key"] for b in W.boxes(view)}
        | {a["key"] for a in view["algorithms"]}
        | {g["key"] for g in view["libraries"]}
        | {o["key"] for o in view["outside"]}
    )
    for ln in view["lines"]:
        assert ln["start"] in known and ln["end"] in known
        # no line between your own software that is tied to nothing and a server: that would be a guess
        assert not (ln["start"].startswith("top:") and ln["end"].startswith("server:"))
        assert not (ln["start"].startswith("server:") and ln["end"].startswith(("top:", "libraries:")))
        assert not (ln["start"] == "clients" and ln["kind"] != "ask")  # who connects is never drawn as known


def test_a_live_line_starts_at_this_computer_and_only_once_a_connection_was_made(walk):
    for stage in ("imported", "listed"):
        view = walk.at[stage].view
        assert not W.lines(view, "live")
        idle = [o["sub"] for o in view["outside"] if o["key"] == "this_computer"]
        assert idle == ["Evidence Lab · no handshake made yet"]
    view = walk.at["verified"].view
    assert {o["key"]: o["sub"] for o in view["outside"]} == {
        "clients": "Outside your systems. Who connects is not in your files.",
        "this_computer": "Evidence Lab · handshakes only",
    }
    # what was seen is read from the recorded handshakes: Verify's own evidence lists each version it tried
    found = next(r for r in walk.at["verified"].verify["results"] if r["claim"]["kind"] == "protocol_versions")
    tried = next(e for e in found["evidence"] if e["title"].startswith("TLS versions"))["output"].splitlines()
    assert [ln.split(":")[0] for ln in tried if ": accepted" in ln] == ["TLS 1.3", "TLS 1.2"]
    assert W.lines(view, "live") == {("this_computer", walk.plan.server, "live", "TLS · 1.3 and 1.2 accepted")}


@pytest.mark.parametrize("stage", STAGES)
def test_what_the_files_do_not_say_is_listed_with_where_it_can_be_filled(walk, stage):
    plan, view = walk.plan, walk.stage(stage).view
    gaps = {g["key"]: g for g in view["gaps"]["items"]}
    assert view["gaps"]["title"] == "What your files don't say"
    assert gaps["clients"]["text"].startswith(f"Who connects to {plan.address}.") and gaps["clients"]["link"] is None
    # the reader does not read data flows, so the map does not say the file names none: it says it does not read them
    assert "does not read them" in gaps["data_flows"]["text"] and "names none" not in gaps["data_flows"]["text"]
    to_dependencies = {"page": "migration/dependencies", "item": None}
    if stage == "imported":
        assert list(gaps) == ["software", "clients", "data_flows", "libraries"]
        assert gaps["software"]["text"].startswith(
            f"Which software answers on {plan.address}. Your scanner file names no software for it."
        )
        assert gaps["libraries"]["link"] == gaps["software"]["link"] == to_dependencies
        return
    assert list(gaps) == ["software", "clients", "data_flows"]
    # every untied top entry is named, neither is picked, and the way to tie one is given
    assert gaps["software"]["text"] == (
        f"Which software answers on {plan.address}. Your dependency list names 2 parts that are not tied to a system "
        "of your scanner file: acme-pay-server 1.0.0 and acme-ledger 5.1.0. The map does not guess which, if any, "
        "runs it. If one does, tie it on Dependencies (Part of)."
    )
    assert gaps["software"]["link"] == to_dependencies and gaps["software"]["link_label"] == "Dependencies"


# ---------------------------------------------------------------- stage by stage: what each check found


def test_before_any_check_every_spot_says_what_the_file_claims_and_that_it_is_not_checked(walk):
    for stage in ("imported", "listed"):
        view, plan = walk.at[stage].view, walk.plan
        assert view["state"] == "file_only" and view["empty"] is None
        assert (view["banner"]["strong"], view["banner"]["text"]) == (
            "Nothing has been checked yet.",
            # (a claim about a signing program is checked on a copy, never on a live system: the sentence says both)
            "This is what your scanner file says. Verify checks each claim: a server at its address, a signing program on "
            "a copy on this computer. The map fills in as each check runs.",
        )
        assert view["banner"]["link"] == {"page": "inventory/verify", "item": None}
        assert all(not c["checked"] and c["word"] in W.NOT_YET and c["tone"] is None for c in W.checks(view))
        server = [(s["key"], s["file_says"], s["claimed"], s["empty_text"]) for s in W.box(view, plan.server)["spots"]]
        assert server == [
            ("tls_versions", "The file says TLS 1.3 only", "TLS 1.3 only", "Not checked yet"),
            ("certificate", "The file says ECDSA P-256", "ECDSA P-256", "Not checked yet"),
            ("key_exchange", "Not in your file", None, "Not measured yet"),
        ]
        assert [(s["key"], s["file_says"]) for s in W.box(view, plan.program)["spots"]] == [
            ("signs", "The file says ECDSA P-256"),
            ("checks_signatures", "Not in your file"),
            ("speed_size", "Not in your file"),
        ]
        # what the file claims rests on the file: both boxes carry that one tag; a check that has not run has none
        for key in (plan.server, plan.program):
            assert W.box(view, key)["tag"]["key"] == "file" and not W.box(view, key)["observed"]
        by_kind = {c["kind"]: (c["tag"] or {}).get("key") for c in W.checks(view)}
        assert by_kind == {"claim": "file", "test": None, "status": None}
        assert all(c["link"]["page"] == "inventory/import" for c in W.checks(view) if c["kind"] == "claim")
        assert all(c["link"]["page"] == "checks" for c in W.checks(view) if c["kind"] == "test")


def test_after_verify_each_claim_carries_verifys_own_word_and_the_rest_still_says_not_checked(walk):
    at, plan = walk.at["verified"], walk.plan
    assert at.view["state"] == "checked" and at.view["banner"] is None
    results = {f"claim-{r['claim_id']}": r for r in at.verify["results"]}
    claims = [c for c in W.checks(at.view) if c["kind"] == "claim"]
    assert len(claims) == len(results) == 3
    for c in claims:
        res = results[c["id"]]
        assert c["word"] == res["result"] and c["checked"] and c["tag"] == res["source_tag"]
        assert c["link"] == {"page": "inventory/verify", "item": c["id"]}
    assert W.check(at.view, plan.server, "claim-1")["word"] == "False"  # the server accepts TLS 1.2
    assert all(c["word"] in W.NOT_YET for c in W.checks(at.view) if c["kind"] != "claim")
    # every result in the endpoint's box was observed live, every one in the program's box proven in the lab
    assert W.box(at.view, plan.server)["tag"]["key"] == "live" and W.box(at.view, plan.program)["tag"]["key"] == "lab"
    assert all(s["tag"] is None for b in W.boxes(at.view) for s in b["spots"])  # (said once, on the box)
    assert W.box(at.view, plan.server)["observed"] and not W.box(at.view, "top:acme-ledger")["observed"]


@pytest.mark.slow
def test_after_run_all_each_test_is_listed_by_name_with_evidences_own_word(walk):
    at, plan = walk.stage("ran"), walk.plan
    rows = {f"test-{r['item_id']}": r for r in at.lab["rows"]}
    tests = [c for c in W.checks(at.view) if c["kind"] == "test"]
    assert {c["id"] for c in tests} == set(rows) and len(tests) == 4
    for c in tests:
        row = rows[c["id"]]
        assert c["name"] == row["title"] and c["checked"] and c["beside"] == []
        assert (c["word"], c["tone"], c["code"]) == (
            row["result"]["label"],
            row["result"]["tone"],
            row["result"]["code"],
        )
        assert c["tag"] == row["result"]["source_tag"] and c["link"] == {"page": "evidence", "item": c["id"]}
    by_spot = {s["key"]: [c["name"] for c in s["checks"]] for b in W.boxes(at.view) for s in b["spots"]}
    assert by_spot["tls_versions"] == ["The claim", "Old TLS versions"]
    assert by_spot["certificate"] == ["The claim", "Certificate strength", "Post-quantum status"]
    assert by_spot["checks_signatures"] == ["Attacker tricks (our short list)"]
    assert by_spot["speed_size"] == ["Speed and size"]
    assert W.check(at.view, plan.server, "test-1")["word"] == "Failed"
    # Run all does not measure the post-quantum status: Measure status on the Migration plan does
    assert all(c["word"] == "Not measured yet" for c in W.checks(at.view) if c["kind"] == "status")


@pytest.mark.slow
def test_after_measure_status_each_track_carries_the_migration_plans_own_word(walk):
    at, plan = walk.stage("measured"), walk.plan
    systems = {s["key"]: s for s in at.migration["systems"]}
    statuses = {(b["key"], c["id"]): c for b in W.boxes(at.view) for c in W.checks(b) if c["kind"] == "status"}
    assert sorted(statuses) == sorted(
        [(plan.server, "status-kex"), (plan.server, "status-auth"), (plan.program, "status-signatures")]
    )
    for (key, check_id), c in statuses.items():
        track = next(t for t in systems[key]["tracks"] if t["key"] == check_id.removeprefix("status-"))
        assert c["name"] == "Post-quantum status" and c["word"] == track["status"]["label"] == "Classical"
        assert c["tag"] == systems[key]["source_tag"] and c["link"] == {"page": "migration/systems", "item": key}
    # key exchange has its own spot; authentication sits with the certificate; a program's sits with what it signs with
    assert [c["id"] for c in W.spot(at.view, plan.server, "key_exchange")["checks"]] == ["status-kex"]
    assert W.spot(at.view, plan.server, "certificate")["checks"][-1]["id"] == "status-auth"
    assert W.spot(at.view, plan.program, "signs")["checks"][-1]["id"] == "status-signatures"
    assert all(c["checked"] for c in W.checks(at.view))
    assert W.box(at.view, plan.server)["tag"]["key"] == "live" and W.box(at.view, plan.program)["tag"]["key"] == "lab"


@pytest.mark.parametrize("stage", STAGES)
def test_every_result_word_on_the_map_is_the_word_on_its_own_page(walk, stage):
    at = walk.stage(stage)
    verify = {f"claim-{r['claim_id']}": r["result"] for r in (at.verify or {}).get("results", [])}
    tests = {f"test-{r['item_id']}": (r["result"] or {}).get("label") for r in at.lab["rows"]}
    tracks = {
        (s["key"], t["key"]): t["status"]["label"]
        for s in (at.migration or {}).get("systems", [])
        for t in s["tracks"]
        if t["status"]["code"] != "not_measured"
    }
    seen = 0
    for b in W.boxes(at.view):
        for c in W.checks(b):
            own = (
                verify.get(c["id"])
                if c["kind"] == "claim"
                else tests.get(c["id"])
                if c["kind"] == "test"
                else tracks.get((b["key"], c["id"].removeprefix("status-")))
            )
            assert c["word"] == (own or ("Not measured yet" if c["kind"] == "status" else "Not checked yet")), c
            assert c["checked"] == (own is not None)
            seen += own is not None
    assert seen == {"imported": 0, "listed": 0, "verified": 3, "ran": 7, "measured": 10}[stage]
    # the map words no result: besides the checks' own words it says only that a check has not run yet
    page_words = set(verify.values()) | {w for w in tests.values() if w} | set(tracks.values())
    assert {c["word"] for c in W.checks(at.view)} <= page_words | {words.NOT_CHECKED, words.NOT_MEASURED}
    # ... and the same words, with each check's plain sentence as its page shows it, in the box's panel
    sentences = {f"claim-{r['claim_id']}": r["summary"] for r in (at.verify or {}).get("results", [])}
    sentences |= {f"test-{r['item_id']}": r["result"]["plain"] for r in at.lab["rows"] if r["result"]}
    for key, panel in at.panels.items():
        on_map = {c["id"]: c for c in W.checks(W.box(at.view, key))}
        for c in W.checks(panel):
            assert {k: c[k] for k in on_map[c["id"]]} == on_map[c["id"]]
            if c["id"] in sentences:
                assert c["plain"] == sentences[c["id"]]
            if c["kind"] == "status" and c["checked"]:
                system = next(s for s in at.migration["systems"] if s["key"] == key)
                track = next(t for t in system["tracks"] if t["key"] == c["id"].removeprefix("status-"))
                assert c["plain"] == track["sentence"]
                # the plan's one line for the system, once for the box and under no single track
                assert "next" not in c and panel["next"] == {
                    "text": system["plan_line"],
                    "label": "The system on Migration plan",
                    "link": {"page": "migration/systems", "item": key},
                }
        if not any(c["kind"] == "status" and c["checked"] for c in W.checks(panel)):
            assert panel["next"] is None  # no status measured (or a box that is no system): no next step is made up


@pytest.mark.parametrize("stage", STAGES)
def test_the_four_counts_are_the_overviews_and_every_tag_says_one_of_the_four(walk, stage):
    at = walk.stage(stage)
    # the Overview shows, group by group, the counts Checks works out; the map shows their sum
    summed = W.summed(at.checks["groups"])
    if at.overview is not None:
        assert W.summed(at.overview["groups"]) == summed
    assert W.counts(at.view) == summed and [c["key"] for c in at.view["counts"]] == list(present_source.KEYS)
    assert [c["label"] for c in at.view["counts"]] == [LABELS[k] for k in present_source.KEYS]
    assert (
        W.counts(at.view)
        == {
            "imported": {
                "live": 0,
                "lab": 0,
                "file": 5,
                "published": 0,
            },  # three claims and two systems, nothing checked
            # the list adds its ten libraries: four answered by their makers, six with no answer yet
            "listed": {"live": 0, "lab": 0, "file": 11, "published": 4},
            "verified": {"live": 2, "lab": 1, "file": 8, "published": 4},
            "ran": {"live": 4, "lab": 3, "file": 8, "published": 4},
            "measured": {"live": 5, "lab": 4, "file": 6, "published": 4},
        }[stage]
    )

    def tags(value, out):
        if isinstance(value, dict):
            if set(value) == {"key", "label", "meaning", "note"}:
                out.append(value)
            for v in value.values():
                tags(v, out)
        elif isinstance(value, list):
            for v in value:
                tags(v, out)
        return out

    for tag in tags([at.view, at.panels], []):
        assert tag["label"] == LABELS[tag["key"]] and tag["meaning"] == present_source.MEANINGS[tag["key"]]
    # a box carries the one tag all its results share; where they differ the spots carry theirs; never both
    for b in W.boxes(at.view):
        keys = {c["tag"]["key"] for c in W.checks(b) if c["tag"]}
        assert (b["tag"] or {}).get("key") == (keys.pop() if len(keys) == 1 else None)
        if b["tag"] is not None:
            assert all(s["tag"] is None for s in b["spots"])


@pytest.mark.parametrize("stage", STAGES)
def test_every_link_opens_and_nothing_is_rated(walk, stage):
    at = walk.stage(stage)
    links = W.every_link([at.view, at.panels])
    assert len(links) > 10
    for link in links:
        assert set(link) <= {"page", "item", "section", "group", "assessment_id"}
        assert W.opens(walk.known, link), link
    for text in W.texts([at.view, at.panels]):
        assert not W.NEVER.search(text), text
    assert all(b["link"] == {"page": "observatory", "item": b["key"]} for b in W.boxes(at.view))


def test_one_link_of_each_page_is_opened_through_that_pages_own_read(walk):
    at = walk.at["verified"]
    by_page: dict[str, dict] = {}
    # (the links of the first stage too: a claim is linked to Import only before Verify)
    for link in W.every_link([at.view, at.panels, walk.at["imported"].view]):
        if link["item"] is not None:
            by_page.setdefault(link["page"], link)
    assert set(by_page) == W.PAGES - {"migration/roadmap", "fixes"}  # (no test has failed yet: no fix)
    for link in by_page.values():
        assert W.really_opens(walk.lab, walk.plan, link, walk.known), link
    assert not W.really_opens(walk.lab, walk.plan, {"page": "evidence", "item": "test-999"}, walk.known)


@pytest.mark.parametrize("stage", STAGES)
def test_what_the_map_was_built_from_and_when_it_last_changed(walk, stage):
    at = walk.stage(stage)
    said = "".join("<time>" if p["t"] == "time" else p["v"] for p in at.view["built_from"])
    files = "acme-pay-cbom.json, dependencies-demo.cdx.json and the checks of this assessment"
    assert said == {
        "imported": "Built from acme-pay-cbom.json. Brought in <time>.",
        "listed": "Built from acme-pay-cbom.json and dependencies-demo.cdx.json. Last changed <time>.",
    }.get(stage, f"Built from {files}. Last changed <time>.")
    when = next(p["v"] for p in at.view["built_from"] if p["t"] == "time")
    assessment = walk.lab.assessment_for(plan_id=walk.plan.id)
    newest = {
        "imported": lambda: walk.lab.assessment_core(assessment.id)["file"]["imported_at"],
        "listed": lambda: at.dependencies["list_file"]["at"],
        "verified": lambda: at.verify["finished_at"],
        "ran": lambda: max(r["result"]["finished_at"] for r in at.lab["rows"] if r["result"]),
    }.get(stage)
    if newest is not None:
        assert when == newest()
    earlier = [walk.at[s] for s in ("imported", "listed", "verified", "ran", "measured") if s in walk.at]
    times = [next(p["v"] for p in e.view["built_from"] if p["t"] == "time") for e in earlier]
    assert times == sorted(times) and len(set(times)) == len(times)  # each stage changed it


# ---------------------------------------------------------------- a box, opened


def test_a_servers_panel_sums_up_in_the_checks_own_words_and_links_each_result(walk):
    at, plan = walk.at["verified"], walk.plan
    panel = at.panels[plan.server]
    assert (panel["title"], panel["sub"]) == (ENDPOINT, f"Server · {plan.address}")
    assert panel["part_of"] == SERVICE and panel["tag"]["key"] == "live"
    assert panel["summary"] == (
        "2 claims: 1 False, 1 True. 2 server tests: 2 Not checked yet. Post-quantum status: Not measured yet."
    )
    assert panel["last"] == {"label": "Last observed", "at": at.verify["finished_at"]}
    tls = next(s for s in panel["spots"] if s["key"] == "tls_versions")
    claim, test = tls["checks"]
    assert [x["label"] for x in claim["links"]] == ["The claim on Verify", "The result on Evidence"]
    assert claim["links"][1]["link"] == {"page": "evidence", "item": "claim-1"}
    assert claim["plain"] == "The server accepts TLS 1.2, so ‘TLS 1.3 only’ is not true."
    assert [x["label"] for x in test["links"]] == ["The test on Checks"] and test["fix"] is None
    status = next(c for s in panel["spots"] for c in s["checks"] if c["id"] == "status-kex")
    assert [x["label"] for x in status["links"]] == ["The system on Migration plan"] and panel["next"] is None
    # what the files don't say about it, and the lines of the scanner file that name it
    assert [g["key"] for g in panel["gaps"]["items"]] == ["software", "clients"]
    (lines,) = panel["file_lines"]
    assert (lines["title"], lines["filename"], lines["more"]) == ("In your scanner file", "acme-pay-cbom.json", 0)
    assert [ln["where"] for ln in lines["lines"]][:3] == ["services[0]", "dependencies[0]", "dependencies[1]"]
    assert plan.address in lines["lines"][0]["text"]
    # its Related block is the one every page shows for this system
    assert panel["related_key"] == "system:" + plan.server
    assert panel["related"] == at.related[plan.server] and set(at.related) == {plan.server, plan.program}
    assert {line["kind"] for line in panel["related"]} >= {"claim", "test"}
    assert panel["link"] == {"page": "observatory", "item": plan.server}


def test_a_programs_panel_and_an_untied_entrys_panel(walk):
    at, plan = walk.at["verified"], walk.plan
    panel = at.panels[plan.program]
    assert panel["summary"] == "1 claim: 1 True. 2 tests: 2 Not checked yet. Post-quantum status: Not measured yet."
    assert panel["last"]["label"] == "Last run" and panel["tag"]["key"] == "lab"
    assert [f["title"] for f in panel["file_lines"]] == ["In your scanner file", "In your dependency list"]
    assert panel["file_lines"][1]["lines"] == [{"where": "components", "text": "acme-sign 1.4.2 (application)"}]
    assert [g["key"] for g in panel["gaps"]["items"]] == ["libraries", "where"]
    assert (
        panel["gaps"]["items"][0]["text"] == words.GAP_NO_LIBRARIES_LISTED
    )  # the list names it, and no library under it
    assert panel["related_key"] == "system:" + plan.program
    own = at.panels["top:acme-ledger"]
    assert own["summary"] == "Nothing observed or run here." and own["tag"] is None and own["last"] is None
    assert own["spots"] == [] and own["related_key"] is None and own["related"] == [] and own["fixes"] == []
    assert own["note"] == f"Not tied to {ENDPOINT} or to acme-sign 1.4.2." and own["part_of"] == SERVICE
    assert [g["key"] for g in own["gaps"]["items"]] == ["part_of"]
    assert own["gaps"]["items"][0]["link"] == {"page": "migration/dependencies", "item": None}
    (group,) = own["libraries"]
    assert group["count"] == 8 and group["key"] == "libraries:acme-ledger"
    assert own["file_lines"][0]["lines"] == [
        {"where": "components", "text": "acme-ledger 5.1.0 (application)"},
        {"where": "dependencies", "text": "acme-ledger 5.1.0 depends on 8 components"},
    ]


@pytest.mark.slow
def test_after_the_checks_the_panels_carry_each_results_own_sentence_its_fix_and_its_next_step(walk):
    at, plan = walk.stage("measured"), walk.plan
    panel = at.panels[plan.server]
    assert panel["summary"] == (
        "2 claims: 1 False, 1 True. 2 server tests: 1 Failed, 1 Passed. Post-quantum status: Classical."
    )
    tls = next(s for s in panel["spots"] if s["key"] == "tls_versions")
    claim, test = tls["checks"]
    # (the False claim is tied to the fix too: the failed test that names this claim is what the fix came from)
    assert [x["label"] for x in claim["links"]] == ["The claim on Verify", "The result on Evidence", "The fix on Fixes"]
    certificate = next(c for s in panel["spots"] for c in s["checks"] if c["id"] == "claim-2")
    assert [x["label"] for x in certificate["links"]] == ["The claim on Verify", "The result on Evidence"]  # True
    # the failed test's own line about its fix, as Evidence shows it, and the fix a recorded link ties to it
    row = next(r for r in at.lab["rows"] if r["kind"] == "tls_versions")
    line = row["result"]["fix_line"]
    assert test["fix"] == {
        "text": f"{line['lead']} {line['rest']}",
        "label": line["button"],
        "link": {"page": "fixes", "item": line["fix_id"]},
    }
    assert test["fix"]["text"] == "Server setting change: try it on a test copy, then apply"
    assert [x["label"] for x in test["links"]] == ["The result on Evidence", "The fix on Fixes"]
    status = next(c for s in panel["spots"] for c in s["checks"] if c["id"] == "status-kex")
    assert [x["label"] for x in status["links"]] == ["The system on Migration plan", "The result on Evidence"]
    assert panel["next"] == {
        "text": "Next: hybrid key exchange · Phase 2",
        "label": "The system on Migration plan",
        "link": {"page": "migration/systems", "item": plan.server},
    }
    fixes = {f["link"]["item"]: f for f in panel["fixes"]}
    listed = {f["id"]: f for f in walk.lab.fixes_view(plan.id)["fixes"]}
    assert set(fixes) >= {"fix-tls-versions"} and set(fixes) <= set(listed)
    assert all(
        f["label"] == listed[key]["title"] and f["sub"] == listed[key]["status"]["word"] for key, f in fixes.items()
    )
    assert {line["kind"] for line in panel["related"]} >= {"claim", "test", "fix"}
    program = at.panels[plan.program]
    assert program["summary"] == "1 claim: 1 True. 2 tests: 1 Failed, 1 Measured. Post-quantum status: Classical."
    by_page: dict[tuple, dict] = {}
    for link in W.every_link([at.view, at.panels]):
        by_page.setdefault((link["page"], (link["item"] or "").split("-")[0].split(":")[0]), link)
    assert {page for page, _ in by_page} >= {"fixes", "evidence", "migration/systems"}
    for link in by_page.values():  # one link of each kind, opened through its page's own read
        assert W.really_opens(walk.lab, walk.plan, link, walk.known), link


# ---------------------------------------------------------------- from a result back to the map


def test_where_a_result_sits_on_the_map_by_the_key_of_its_related_block(walk):
    lab, plan = walk.lab, walk.plan
    rows = {r["title"]: r["item_id"] for r in walk.at["verified"].lab["rows"]}
    groups = walk.at["verified"].dependencies["groups"]
    library = next(r["id"] for g in groups for r in g["rows"] if r["label"] == "wolfssl 5.7.2")
    program = "acme-sign 1.4.2"
    wanted = {
        "claim:1": ([SERVICE, ENDPOINT, "TLS versions"], plan.server),
        "claim:2": ([SERVICE, ENDPOINT, "Certificate"], plan.server),
        "claim:3": ([SERVICE, program, "Signs"], plan.program),
        f"test:{rows['Old TLS versions']}": ([SERVICE, ENDPOINT, "TLS versions"], plan.server),
        f"test:{rows['Attacker tricks (our short list)']}": ([SERVICE, program, "Checks signatures"], plan.program),
        f"test:{rows['Speed and size']}": ([SERVICE, program, "Speed and size"], plan.program),
        "system:" + plan.server: ([SERVICE, ENDPOINT], plan.server),
        "system:" + plan.program: ([SERVICE, program], plan.program),
        f"library:{library}": ([SERVICE, "acme-ledger 5.1.0", "Libraries"], "top:acme-ledger"),
    }
    for key, (path, box) in wanted.items():
        answer = build.place_of_plan(lab, plan.id, key)
        assert answer["key"] == key and answer["place"] == {
            "label": "On your map",
            "path": path,
            "box": box,
            "link": {"page": "observatory", "item": box},
            "link_label": "Show on the map",
        }, key
        assert W.opens(walk.known, answer["place"]["link"])
    # the keys are the ones the Related block of each panel uses
    row = next(r for r in lab.ledger(plan.id)["rows"] if r["id"] == f"test-{rows['Old TLS versions']}")
    assert lab.relation_key(row) in wanted
    claim = next(r for r in lab.ledger(plan.id)["rows"] if r["id"] == "claim-1")
    assert lab.relation_key(claim) == "claim:1"
    # what is not on the map has no place: a fix, an advisory, a claim or a test that is not there, anything else
    for key in (
        "fix:fix-tls-versions",
        "advisory:CVE-2022-21449",
        "claim:999",
        "test:999",
        "system:server:nowhere:1",
        "library:row-99",
        "change:tls",
        "x",
        "claim:",
    ):
        assert build.place_of_plan(lab, plan.id, key) == {"key": key, "place": None}

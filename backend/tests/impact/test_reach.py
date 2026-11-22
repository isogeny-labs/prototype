"""Phase 4e (change impact, first half): "Where it is used". The walk through a dependency list, the rules that say two
things are the same, and the places in this assessment and elsewhere in the organization, on the demo data and on
small lists written here. Reading it changes nothing."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.dependencies.tree import build_tree, reached_from, top_keys
from app.importer.sbom import read_dependency_list
from app.impact.reach import same_version, server_part, software_match, software_part
from tests.assistant.assistant_walk import everything_kept
from tests.conftest import make_lab

REPO = Path(__file__).resolve().parents[3]
DEMO_LIST = REPO / "demo" / "dependencies-demo.cdx.json"
WORDS_NEVER = re.compile(r"\b(secure|security score|score|severity|severe|critical|time.to.hack)\b", re.I)


def _cdx(described: str, components: list[tuple[str, str, str, str | None]], edges: dict[str, list[str]]) -> bytes:
    """A small CycloneDX 1.6 list: components are (bom-ref, type, name, version), edges ref -> refs it depends on."""
    comps = [{"bom-ref": ref, "type": kind, "name": name, **({"version": version} if version else {})}
             for ref, kind, name, version in components]
    return json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
                       "metadata": {"component": {"bom-ref": described, "type": "application", "name": "Thing", "version": "1"}},
                       "components": comps,
                       "dependencies": [{"ref": k, "dependsOn": v} for k, v in edges.items()]}).encode()


SHARED = _cdx("thing", [("pay", "application", "pay-api", "2.0"), ("ledger", "application", "ledger", "3.1"),
                        ("py", "library", "python", "3.12.3"), ("ssl", "library", "openssl", "3.0.22"),
                        ("lone", "library", "zlib", "1.3")],
              {"thing": ["pay", "ledger"], "pay": ["py"], "py": ["ssl"], "ledger": ["ssl", "lone"]})


# ---------------------------------------------------------------- the walk

def test_every_top_entry_that_reaches_a_library_is_named_with_its_path():
    dl = read_dependency_list(SHARED)
    tops = top_keys(dl, [])
    assert tops == {"thing", "pay", "ledger"}
    # build_tree puts openssl under one heading only (the nearest, the first in the file on a tie) ...
    tree = build_tree(dl, [])
    assert [r.owner for r in tree.rows if r.name == "openssl"] == ["ledger"]
    # ... the walk of "Where it is used" names both programs that use it, each with its own shortest path
    assert reached_from(dl, "ssl", tops) == [("pay", ["python 3.12.3"]), ("ledger", [])]
    # it stops at the first top entry it meets: "thing" (what the whole list describes) is not named on every row
    assert reached_from(dl, "lone", tops) == [("ledger", [])]
    # a top entry is reached by what uses it directly, and never by itself
    assert reached_from(dl, "pay", tops) == [("thing", [])]
    assert reached_from(dl, "thing", tops) == []


def test_a_cycle_in_a_list_ends_the_walk():
    dl = read_dependency_list(_cdx("thing", [("app", "application", "app", "1"), ("a", "library", "a", "1"), ("b", "library", "b", "1")],
                                   {"thing": ["app"], "app": ["a"], "a": ["b"], "b": ["a"]}))
    assert reached_from(dl, "b", top_keys(dl, [])) == [("app", ["a 1"])]


# ---------------------------------------------------------------- the same thing

def test_versions_are_compared_as_the_app_reads_them():
    assert same_version("3.0.22", "3.0.22-1~deb12u2") and same_version("v1.4.2", "1.4.2") and same_version("1.4", "1.4.0")
    assert not same_version("1.4.2", "1.4.3") and not same_version(None, "1.4.2")
    # a version the app can't read matches only the same text
    assert same_version("devel", "DEVEL") and not same_version("devel", "1.0")
    # our own software is matched on the exact version text: acme-sign 1.4.3-otto is another program than 1.4.3
    sign = software_part("acme-sign", "1.4.3")
    assert software_match(sign, "acme-sign", "1.4.3-otto") is None and software_match(sign, "acme-sign", "1.4.3") == "name_version"


def test_the_rules_that_say_two_libraries_are_the_same():
    part = software_part("openssl", "3.0.22", "pkg:generic/openssl@3.0.22")
    assert part.library == "openssl" and "tls" in part.roles
    # both have a package address: it alone decides
    assert software_match(part, "libssl3", "3.0.22", "pkg:deb/debian/libssl3@3.0.22?arch=amd64") is None
    assert software_match(part, "openssl", "3.0.22", "pkg:generic/openssl@3.0.22") == "package"
    assert software_match(part, "openssl", "3.0.23", "pkg:generic/openssl@3.0.23") is None
    # one side has no package address: the knowledge base recognises both as the same library
    assert software_match(part, "openssl", "3.0.22") == "knowledge_base"
    ecdsa = software_part("python-ecdsa", "0.13.2")
    assert software_match(ecdsa, "ecdsa", "0.13.2", "pkg:pypi/ecdsa@0.13.2") == "knowledge_base"
    assert software_match(ecdsa, "ecdsa", "0.13.2", "pkg:npm/ecdsa@0.13.2") is None       # another ecosystem's "ecdsa"
    # the knowledge base knows neither: the same name and version (capital letters ignored)
    sign = software_part("acme-sign", "1.4.2")
    assert sign.library is None
    assert software_match(sign, "ACME-Sign", "1.4.2") == "name_version"
    assert software_match(sign, "acme-sign", "1.4.3") is None and software_match(sign, "acme-signer", "1.4.2") is None
    # the knowledge base knows one side only: never matched by a bare name
    assert software_match(software_part("elliptic", "6.5.6"), "elliptic-fork", "6.5.6") is None
    assert server_part("localhost:8443").label == "localhost:8443"


# ---------------------------------------------------------------- on the demo data, in a lab

@pytest.fixture
def lab(tmp_path):
    lab = make_lab(tmp_path)
    yield lab
    lab.stop()


def _acme(lab, project: str = "Acme Pay", with_list: bool = True, tie: bool = True):
    made = lab.create_project(project, None)
    imp = lab.import_demo(assessment_id=made["assessment_id"])
    lab.confirm_address(imp["id"], imp["addresses"][0]["address"], True)
    pid = lab.ensure_plan(imp["id"])["id"]
    if with_list:
        view = lab.add_dependency_list(pid, DEMO_LIST.name, DEMO_LIST.read_bytes())
        if tie:
            pay = next(g for g in view["groups"] if g["label"] == "acme-pay-server 1.0.0")
            server = next(o["key"] for o in pay["picker"]["options"] if o["key"].startswith("server:"))
            lab.tie_dependency(pid, pay["key"], server)
    return made, imp, pid


def _other(lab, address: str, project: str = "Multi", folder: int | None = None) -> dict:
    made = lab.create_project(project, folder)
    csv = (f"location,type,claim,value\n{address},tls,protocol_versions,TLS1.3\n"
           "acme-sign 1.4.2,software,signature_algorithm,ECDSA P-256\nelliptic 6.5.6,software,signature_algorithm,ECDSA P-256\n")
    lab.import_file("other.csv", csv.encode(), assessment_id=made["assessment_id"])
    return made


def _rows(view: dict) -> dict:
    return {r["label"]: r for g in view["groups"] for r in g["rows"]}


def _texts(block: dict) -> list[str]:
    out = [block["title"], block["count_line"], *block["notes"], block["here"]["none"] or "", block["elsewhere"]["none"] or ""]
    for part in ("here", "elsewhere"):
        out += [line["text"] + " " + line["sub"] for line in block[part]["lines"]]
    for extra in ("compatible", "connect"):
        if block.get(extra):
            out += [block[extra]["title"], block[extra]["text"]]
    return out


def test_a_library_names_your_software_that_reaches_it_and_the_system_it_is_tied_to(lab):
    _, imp, pid = _acme(lab)
    rows = _rows(lab.dependencies_view(pid))
    block = rows["openssl 3.0.22"]["impact"]
    assert block["title"] == "Where it is used" and block["part"] == "openssl 3.0.22"
    [user] = block["here"]["lines"]
    address = imp["addresses"][0]["address"]
    assert user["text"] == "acme-pay-server 1.0.0" and user["link"] == {"page": "migration/systems", "item": f"server:{address}"}
    assert user["sub"] == (f"Your own software, from your dependency list. Uses it, through python 3.12.3. Part of {address} "
                           "(set by you).")
    assert block["count"] == 1 and block["count_line"] == "Re-check this one if you change it."
    assert block["elsewhere"]["lines"] == [] and block["elsewhere"]["none"] == "No other assessment in your organization names it."
    # an untied entry is listed and not counted, with how to tie it
    elliptic = rows["elliptic 6.5.6"]["impact"]
    assert [line["text"] for line in elliptic["here"]["lines"]] == ["acme-ledger 5.1.0"]
    assert elliptic["here"]["lines"][0]["sub"].endswith("Not tied to a system of your file: choose one with Part of on Dependencies.")
    assert elliptic["count"] == 0
    # every line says where it came from and why it is there
    for row in rows.values():
        for line in row["impact"]["here"]["lines"] + row["impact"]["elsewhere"]["lines"]:
            assert line["tag"] == "from your file" and line["sub"].strip()
        assert not any(WORDS_NEVER.search(t) for t in _texts(row["impact"]))


def test_other_assessments_in_the_organization_are_named_and_archived_ones_are_left_out(lab):
    _, imp, pid = _acme(lab)
    address = imp["addresses"][0]["address"]
    other = _other(lab, address)
    elliptic = _rows(lab.dependencies_view(pid))["elliptic 6.5.6"]["impact"]
    [line] = elliptic["elsewhere"]["lines"]
    assert line["text"] == "Multi › Assessment 1" and line["chip"] == "Open"
    assert line["sub"] == "Names elliptic 6.5.6 as a signing program (the knowledge base recognises it as elliptic, at the same version)."
    assert line["link"]["assessment_id"] == other["assessment_id"] and line["link"]["page"] == "migration/systems"
    assert elliptic["count"] == 1
    # a second assessment in the same project is counted with it, not as a line of its own
    second = lab.create_project("Unused", None)          # (another project with nothing that matches)
    lab.import_file("x.csv", b"location,type,claim,value\nfoo 1.0,software,signature_algorithm,ECDSA P-256\n",
                    assessment_id=second["assessment_id"])
    assert len(_rows(lab.dependencies_view(pid))["elliptic 6.5.6"]["impact"]["elsewhere"]["lines"]) == 1
    # archived: the assessment, its project, or a folder above it
    lab.update_project(other["id"], {"archived": True})
    assert _rows(lab.dependencies_view(pid))["elliptic 6.5.6"]["impact"]["elsewhere"]["lines"] == []
    lab.update_project(other["id"], {"archived": False})
    folder = lab.create_folder("Old", None)
    inner = lab.create_folder("Inner", folder["id"])
    lab.update_project(other["id"], {"folder_id": inner["id"]})
    assert len(_rows(lab.dependencies_view(pid))["elliptic 6.5.6"]["impact"]["elsewhere"]["lines"]) == 1
    lab.update_folder(folder["id"], {"archived": True})
    assert _rows(lab.dependencies_view(pid))["elliptic 6.5.6"]["impact"]["elsewhere"]["lines"] == []
    lab.update_folder(folder["id"], {"archived": False})
    lab.update_assessment(other["assessment_id"], {"archived": True})
    assert _rows(lab.dependencies_view(pid))["elliptic 6.5.6"]["impact"]["elsewhere"]["lines"] == []


def test_a_closed_assessment_reads_only_its_own_file_and_list_and_a_closed_one_elsewhere_says_so(lab):
    made, imp, pid = _acme(lab)
    other = _other(lab, imp["addresses"][0]["address"])
    lab.update_assessment(other["assessment_id"], {"close": True, "signed_off_by": "Kevin"})
    [line] = _rows(lab.dependencies_view(pid))["elliptic 6.5.6"]["impact"]["elsewhere"]["lines"]
    assert line["chip"] == "Closed"
    lab.update_assessment(made["assessment_id"], {"close": True, "signed_off_by": "Kevin"})
    block = _rows(lab.dependencies_view(pid))["elliptic 6.5.6"]["impact"]
    assert block["elsewhere"]["lines"] == [] and block["elsewhere"]["none"] == (
        "This assessment is closed, so other assessments are not read: only its own scanner file and dependency list are.")
    assert [line["text"] for line in block["here"]["lines"]] == ["acme-ledger 5.1.0"]


def test_a_library_reached_by_two_programs_names_both_and_the_what_if_card_says_the_same(lab):
    made = lab.create_project("Shared", None)
    imp = lab.import_demo(assessment_id=made["assessment_id"])
    pid = lab.ensure_plan(imp["id"])["id"]
    lab.add_dependency_list(pid, "shared.cdx.json", SHARED)
    rows = _rows(lab.dependencies_view(pid))
    block = rows["openssl 3.0.22"]["impact"]
    assert [(line["text"], line["sub"].split(". ")[1]) for line in block["here"]["lines"]] == [
        ("pay-api 2.0", "Uses it, through python 3.12.3"), ("ledger 3.1", "Uses it directly")]
    # the what-if card's "Where the library is used" reads the same walk
    used = next(g for g in lab.whatif_view(pid, "openssl", "3.5.0")["facts"] if g["key"] == "used")
    assert [line["text"] for line in used["lines"]] == [
        "openssl 3.0.22 is in your dependency list, under pay-api 2.0 (through python 3.12.3). pay-api 2.0 is not tied to a system of your scanner file.",
        "openssl 3.0.22 is in your dependency list, under ledger 3.1 (direct). ledger 3.1 is not tied to a system of your scanner file."]


def test_with_no_dependency_list_only_the_scanner_file_is_read_and_it_says_so(lab):
    _, imp, pid = _acme(lab, with_list=False)
    from app.present.impact import block
    with lab.db() as db:
        facts = block(lab._impact(db, lab._plan(db, pid), software_part("acme-sign", "1.4.2")), on_fix=True)
    assert [line["text"] for line in facts["here"]["lines"]] == ["acme-sign 1.4.2"]
    assert facts["here"]["lines"][0]["sub"] == "A signing program in your scanner file."
    assert any(note.startswith("This assessment has no dependency list") for note in facts["notes"])


def test_reading_the_blocks_keeps_nothing_and_starts_nothing(lab):
    _, imp, pid = _acme(lab)
    _other(lab, imp["addresses"][0]["address"])
    before, jobs = everything_kept(lab), len(lab.jobs.live(pid))
    lab.dependencies_view(pid)
    lab.fixes_view(pid)
    lab.whatif_view(pid, "openssl", "3.5.0")
    assert everything_kept(lab) == before and len(lab.jobs.live(pid)) == jobs

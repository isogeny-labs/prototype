"""Phase 4d: the two dependency-list readers (CycloneDX JSON 1.5/1.6, SPDX JSON 2.3), their limits and refusals."""
import json
from pathlib import Path

import pytest

from app.dependencies.tree import build_tree, from_store, to_store
from app.importer.common import ImportFileError
from app.importer.sbom import MAX_COMPONENTS, READ, read_dependency_list

DEMO = Path(__file__).resolve().parents[3] / "demo"


def cdx(components, dependencies=None, version="1.6", top=None) -> bytes:
    doc = {"bomFormat": "CycloneDX", "specVersion": version, "components": components}
    if top:
        doc["metadata"] = {"component": top}
    if dependencies is not None:
        doc["dependencies"] = dependencies
    return json.dumps(doc).encode()


def lib(ref, name, version="1.0", purl=None, kind="library"):
    out = {"bom-ref": ref, "type": kind, "name": name, "version": version}
    if purl:
        out["purl"] = purl
    return out


@pytest.mark.parametrize("version", ["1.5", "1.6"])
def test_cyclonedx_both_versions(version):
    dl = read_dependency_list(cdx([lib("a", "openssl", "3.0.22", "pkg:generic/openssl@3.0.22")], version=version))
    assert dl.format == f"CycloneDX {version}" and dl.components["a"].purl == "pkg:generic/openssl@3.0.22"


@pytest.mark.parametrize("version", ["1.4", "1.7", None, 1.6])
def test_cyclonedx_other_versions_are_refused_in_one_sentence(version):
    with pytest.raises(ImportFileError) as err:
        read_dependency_list(cdx([lib("a", "x")], version=version))
    assert str(err.value).endswith(READ) and "doesn't read" in str(err.value)


def test_dependencies_of_dependencies_and_the_nearest_top_entry():
    data = cdx([lib("app", "shop", kind="application"), lib("py", "python", "3.12.3"), lib("ssl", "openssl", "3.0.22"),
                lib("z", "zlib", "1.3")],
               [{"ref": "app", "dependsOn": ["py"]}, {"ref": "py", "dependsOn": ["ssl"]}, {"ref": "ssl", "dependsOn": ["z"]}])
    tree = build_tree(read_dependency_list(data), [])
    by = {r.name: r for r in tree.rows}
    assert [t.name for t in tree.tops] == ["shop"]
    assert by["openssl"].owner == "app" and by["openssl"].via == ["python 3.12.3"]
    assert by["zlib"].via == ["python 3.12.3", "openssl 3.0.22"]


def test_a_loop_ends_and_every_row_is_listed_once():
    data = cdx([lib("app", "shop", kind="application"), lib("a", "a"), lib("b", "b")],
               [{"ref": "app", "dependsOn": ["a"]}, {"ref": "a", "dependsOn": ["b"]}, {"ref": "b", "dependsOn": ["a", "b"]}])
    tree = build_tree(read_dependency_list(data), [])
    assert sorted(r.name for r in tree.rows) == ["a", "b"] and all(r.owner == "app" for r in tree.rows)


def test_nested_components_and_a_tie_goes_to_the_first_top_entry():
    data = cdx([{"bom-ref": "one", "type": "application", "name": "one", "version": "1", "components": [lib("s", "shared")]},
                lib("two", "two", kind="application")],
               [{"ref": "two", "dependsOn": ["s"]}])
    tree = build_tree(read_dependency_list(data), [])
    assert [r.owner for r in tree.rows] == ["one"]        # both at distance 1: the one that comes first in the file


def test_a_row_no_top_entry_reaches_is_listed_on_its_own():
    tree = build_tree(read_dependency_list(cdx([lib("a", "lonely")])), [])
    assert [t.name for t in tree.tops] == ["(not under any entry)"] and tree.rows[0].owner == "(not under any entry)"


def test_a_component_equal_to_a_signing_program_of_the_file_is_a_top_entry():
    tree = build_tree(read_dependency_list(cdx([lib("p", "acme-sign", "1.4.2"), lib("e", "python-ecdsa", "0.13.2")],
                                               [{"ref": "p", "dependsOn": ["e"]}])), [("acme-sign", "1.4.2")])
    assert [t.name for t in tree.tops] == ["acme-sign"] and tree.tops[0].program == ("acme-sign", "1.4.2")


def test_not_libraries_are_counted_not_looked_up():
    data = cdx([lib("os", "debian", "12", kind="operating-system"), lib("f", "/etc/ssl/openssl.cnf", None, kind="file"), lib("a", "zlib")])
    tree = build_tree(read_dependency_list(data), [])
    assert [r.name for r in tree.rows] == ["zlib"] and tree.not_libraries == 2


def test_spdx_reads_packages_purls_and_relationships_both_ways():
    doc = {"spdxVersion": "SPDX-2.3", "SPDXID": "SPDXRef-DOCUMENT", "packages": [
        {"SPDXID": "SPDXRef-app", "name": "shop", "versionInfo": "2.0", "primaryPackagePurpose": "APPLICATION"},
        {"SPDXID": "SPDXRef-py", "name": "python", "versionInfo": "3.12.3"},
        {"SPDXID": "SPDXRef-ssl", "name": "openssl", "versionInfo": "3.0.22",
         "externalRefs": [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl", "referenceLocator": "pkg:generic/openssl@3.0.22"}]}],
        "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-app"},
                          {"spdxElementId": "SPDXRef-app", "relationshipType": "DEPENDS_ON", "relatedSpdxElement": "SPDXRef-py"},
                          {"spdxElementId": "SPDXRef-ssl", "relationshipType": "DEPENDENCY_OF", "relatedSpdxElement": "SPDXRef-py"}]}
    dl = read_dependency_list(json.dumps(doc).encode())
    tree = build_tree(dl, [])
    assert dl.format == "SPDX 2.3" and dl.described == "SPDXRef-app" and dl.components["SPDXRef-ssl"].purl == "pkg:generic/openssl@3.0.22"
    assert {r.name: r.via for r in tree.rows} == {"python": [], "openssl": ["python 3.12.3"]}


def test_spdx_other_versions_are_refused():
    with pytest.raises(ImportFileError, match="SPDX-2.2, which this version doesn't read"):
        read_dependency_list(json.dumps({"spdxVersion": "SPDX-2.2", "packages": []}).encode())


def test_the_demo_list_and_its_spdx_copy_give_the_same_tree():
    def shape(path):
        tree = build_tree(read_dependency_list(path.read_bytes()), [("acme-sign", "1.4.2")])
        tops = {t.key: f"{t.name} {t.version}" for t in tree.tops}
        return [f"{t.name} {t.version}" for t in tree.tops], [(r.name, r.version, r.purl, tops[r.owner], r.via) for r in tree.rows]
    assert shape(DEMO / "dependencies-demo.cdx.json") == shape(DEMO / "dependencies-demo.spdx.json")
    tops, rows = shape(DEMO / "dependencies-demo.cdx.json")
    assert tops == ["acme-sign 1.4.2", "acme-pay-server 1.0.0", "acme-ledger 5.1.0"] and len(rows) == 10


def test_the_real_syft_file_reads():
    dl = read_dependency_list((DEMO / "dependencies-nginx-image.syft.cdx.json").read_bytes())
    tree = build_tree(dl, [])
    assert dl.format == "CycloneDX 1.6" and len(tree.rows) == 72 and tree.not_libraries > 1000
    assert {r.name for r in tree.rows} >= {"libssl3", "libcrypto3"}


def test_what_is_stored_rebuilds_the_same_tree():
    dl = read_dependency_list((DEMO / "dependencies-demo.cdx.json").read_bytes())
    again = from_store(json.loads(json.dumps(to_store(dl))))
    assert build_tree(again, []) == build_tree(dl, [])


@pytest.mark.parametrize("name, words", [("not-json.json", "This file is not valid JSON."),
                                         ("not-a-dependency-list.json", "This JSON file is neither CycloneDX nor SPDX."),
                                         ("empty.json", "This file is empty.")])
def test_the_broken_files_are_refused_with_one_plain_sentence(name, words):
    with pytest.raises(ImportFileError) as err:
        read_dependency_list((DEMO / "dependencies-broken" / name).read_bytes())
    assert str(err.value) == f"{words} {READ}"


@pytest.mark.parametrize("data, words", [
    (b"[1, 2]", "not a dependency list"),
    (json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.6", "components": {"a": 1}}).encode(), '"components" must be a list'),
    (cdx([lib("app", "shop", kind="application")]), "names no libraries"),
    (b"\xff\xfe\x00", "not valid JSON"),
    (b"[" * 100_000, "not valid JSON"),
])
def test_other_refusals(data, words):
    with pytest.raises(ImportFileError, match=words):
        read_dependency_list(data)


def test_the_component_limit():
    with pytest.raises(ImportFileError, match="more than 10,000 components"):
        read_dependency_list(cdx([lib(f"c{i}", f"lib{i}") for i in range(MAX_COMPONENTS + 1)]))


def test_long_and_odd_text_is_cut_and_kept_as_text():
    dl = read_dependency_list(cdx([lib("a", "x" * 5000 + "\n$(rm -rf /)", "1.0\t;ls")]))
    c = dl.components["a"]
    assert len(c.name) <= 300 and "\n" not in c.name and c.version == "1.0 ;ls"

"""Reading a dependency list (phase 4d): CycloneDX JSON 1.5 or 1.6, or SPDX JSON 2.3.

The file is data. Names, versions and package addresses are kept as text, shown as text and never reach a
command line; what may run is fixed in backend/app/real_libraries.py. Every refusal is one plain sentence
(ImportFileError, shown on the screen as it is). The CSV and CBOM claim readers are not touched by this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.importer.common import ImportFileError

MAX_LIST_BYTES = 16 * 1024 * 1024
MAX_COMPONENTS = 10_000
MAX_DEPTH = 64
CYCLONEDX_VERSIONS = ("1.5", "1.6")
SPDX_VERSIONS = ("SPDX-2.3",)
READ = "Evidence Lab reads dependency lists in CycloneDX JSON (1.5 or 1.6) or SPDX JSON (2.3)."
# What the list itself marks as the customer's own software: a group heading, not a library to look up.
TOP_TYPES = ("application", "container")
# Entries that are not libraries: listed as a count, not looked up.
NOT_LIBRARIES = (
    "operating-system",
    "file",
    "cryptographic-asset",
    "data",
    "machine-learning-model",
    "device",
    "device-driver",
    "firmware",
    "OPERATING-SYSTEM",
    "FILE",
    "DEVICE",
    "FIRMWARE",
)
TEXT_LIMIT = 300


@dataclass
class Component:
    key: str
    name: str
    version: str | None
    purl: str | None
    kind: str  # the list's own word: library, application, container, operating-system, ...
    order: int


@dataclass
class DependencyList:
    format: str  # "CycloneDX 1.6", "SPDX 2.3", ...
    described: str | None  # the key of what the list describes, if it says
    components: dict[str, Component]
    edges: dict[str, list[str]] = field(default_factory=dict)  # key -> keys it depends on (or contains)


def _text(value: object) -> str | None:
    if isinstance(value, str):
        v = " ".join(value.split())
        return v[:TEXT_LIMIT] if v else None
    return None


def _said(value: object) -> str | None:
    """A short piece of what the file itself says, for a refusal: never more than 20 characters of it."""
    v = _text(value)
    return v if v is None or len(v) <= 20 else v[:20] + "…"


def read_dependency_list(data: bytes) -> DependencyList:
    if not data or not data.strip():
        raise ImportFileError(f"This file is empty. {READ}", field="file")
    if len(data) > MAX_LIST_BYTES:
        raise ImportFileError(
            "This dependency list is larger than 16 MB. Evidence Lab reads lists up to 16 MB.", field="file"
        )
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ImportFileError(f"This file is not valid JSON. {READ}", field="file") from None
    if not isinstance(doc, dict):
        raise ImportFileError(f"This JSON file is not a dependency list. {READ}", field="file")
    if doc.get("bomFormat") == "CycloneDX":
        return _cyclonedx(doc)
    if isinstance(doc.get("spdxVersion"), str):
        return _spdx(doc)
    raise ImportFileError(f"This JSON file is neither CycloneDX nor SPDX. {READ}", field="file")


# ---------------------------------------------------------------- CycloneDX


def _cyclonedx(doc: dict) -> DependencyList:
    version = doc.get("specVersion")
    if version not in CYCLONEDX_VERSIONS:
        raise ImportFileError(
            f"This is CycloneDX {_said(version) or '(no version)'}, which this version doesn't read. {READ}",
            field="specVersion",
        )
    components: dict[str, Component] = {}
    counter = [0]

    def add(raw: object, depth: int) -> str | None:
        if not isinstance(raw, dict) or depth > MAX_DEPTH:
            return None
        name = _text(raw.get("name"))
        counter[0] += 1
        if counter[0] > MAX_COMPONENTS:
            raise ImportFileError(
                f"This dependency list names more than {MAX_COMPONENTS:,} components. "
                f"Evidence Lab reads lists of up to {MAX_COMPONENTS:,}.",
                field="components",
            )
        key = _text(raw.get("bom-ref")) or f"component-{counter[0]}"
        if name and key not in components:
            components[key] = Component(
                key=key,
                name=name,
                version=_text(raw.get("version")),
                purl=_text(raw.get("purl")),
                kind=_text(raw.get("type")) or "library",
                order=counter[0],
            )
        nested = raw.get("components")
        if isinstance(nested, list):
            for child in nested:
                child_key = add(child, depth + 1)
                if child_key and name:
                    edges.setdefault(key, []).append(child_key)
        return key if name else None

    edges: dict[str, list[str]] = {}
    meta = doc.get("metadata")
    described = add(meta.get("component"), 0) if isinstance(meta, dict) else None
    listed = doc.get("components")
    if listed is not None and not isinstance(listed, list):
        raise ImportFileError('"components" must be a list.', field="components")
    for raw in listed or []:
        add(raw, 1)
    deps = doc.get("dependencies")
    if isinstance(deps, list):
        for d in deps:
            if isinstance(d, dict) and isinstance(d.get("ref"), str):
                listed_targets = d.get("dependsOn")
                targets = listed_targets if isinstance(listed_targets, list) else []
                edges.setdefault(d["ref"], []).extend(t for t in targets if isinstance(t, str))
    return _finish(f"CycloneDX {version}", described, components, edges)


# ---------------------------------------------------------------- SPDX


def _spdx(doc: dict) -> DependencyList:
    version = doc.get("spdxVersion")
    if version not in SPDX_VERSIONS:
        raise ImportFileError(f"This is {_said(version)}, which this version doesn't read. {READ}", field="spdxVersion")
    packages = doc.get("packages")
    if packages is not None and not isinstance(packages, list):
        raise ImportFileError('"packages" must be a list.', field="packages")
    if packages and len(packages) > MAX_COMPONENTS:
        raise ImportFileError(
            f"This dependency list names more than {MAX_COMPONENTS:,} components. "
            f"Evidence Lab reads lists of up to {MAX_COMPONENTS:,}.",
            field="packages",
        )
    components: dict[str, Component] = {}
    for i, raw in enumerate(packages or [], start=1):
        if not isinstance(raw, dict):
            continue
        name, key = _text(raw.get("name")), _text(raw.get("SPDXID"))
        if not name or not key or key in components:
            continue
        purl = None
        refs = raw.get("externalRefs")
        for ref in refs if isinstance(refs, list) else []:
            if isinstance(ref, dict) and ref.get("referenceType") == "purl":
                purl = _text(ref.get("referenceLocator"))
                break
        purpose = _text(raw.get("primaryPackagePurpose"))
        kind = purpose.lower() if purpose else "library"
        components[key] = Component(
            key=key, name=name, version=_text(raw.get("versionInfo")), purl=purl, kind=kind, order=i
        )
    doc_id = _text(doc.get("SPDXID")) or "SPDXRef-DOCUMENT"
    described_list = (
        [d for d in doc.get("documentDescribes", []) if isinstance(d, str)]
        if isinstance(doc.get("documentDescribes"), list)
        else []
    )
    edges: dict[str, list[str]] = {}
    rels = doc.get("relationships")
    for rel in rels if isinstance(rels, list) else []:
        if not isinstance(rel, dict):
            continue
        a, b, rel_kind = rel.get("spdxElementId"), rel.get("relatedSpdxElement"), rel.get("relationshipType")
        if not isinstance(a, str) or not isinstance(b, str):
            continue
        if rel_kind == "DESCRIBES" and a == doc_id:
            described_list.append(b)
        elif rel_kind in ("DEPENDS_ON", "CONTAINS"):
            edges.setdefault(a, []).append(b)
        elif rel_kind in ("DEPENDENCY_OF", "CONTAINED_BY"):
            edges.setdefault(b, []).append(a)
    described = next((d for d in described_list if d in components), None)
    return _finish(f"SPDX {version.removeprefix('SPDX-')}", described, components, edges)


def _finish(
    fmt: str, described: str | None, components: dict[str, Component], edges: dict[str, list[str]]
) -> DependencyList:
    edges = {
        k: list(dict.fromkeys(v for v in vs if v in components and v != k))
        for k, vs in edges.items()
        if k in components
    }
    if not any(
        c.kind not in TOP_TYPES and c.kind not in NOT_LIBRARIES and c.key != described for c in components.values()
    ):
        raise ImportFileError(
            f"This {fmt} file names no libraries, so there is nothing to look up.", field="components"
        )
    return DependencyList(format=fmt, described=described, components=components, edges=edges)

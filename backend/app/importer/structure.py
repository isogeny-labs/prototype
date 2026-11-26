"""The structure of a scanner file, for the Observatory's map (design refactor, section 5).

The claim reader (cbom.py) keeps only what the claims need. This reader takes, from the kept copy of the same
CycloneDX 1.6 file, what the map draws: the thing the file describes (its top component), each service with its
endpoints, each software component, each cryptographic asset, and which names which (the `dependencies` lines with
`dependsOn` and `provides`, a protocol's and a certificate's own references, a key's algorithm, and a component listed
inside another).

The file is data. Nothing in it is run, opened or looked up. Names are kept as text, cleaned and shortened for the
screen. The file is first held to the claim reader's own reading (`read_cbom`: the same 1 MB limit, the same depth and
count limits, the same refusals in the same words), so a file Import would refuse is refused here too; a few limits of
this reader's own then keep the walk short. Every refusal is one plain sentence (ImportFileError).

A CSV scanner file has no structure: its map is drawn from its claims alone (app/observatory).
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field

from app.importer.cbom import _endpoint, _load_json, _occurrence, _walk_components, read_cbom
from app.importer.common import ImportFileError
from app.names import clean_text, normalize_algorithm, normalize_tls_version

MAX_SERVICES = 5000
MAX_REFERENCES = 50_000  # every "this names that" in the file, counted once
MAX_STEPS = 200_000  # the most the walk from the parts to their algorithms may take, over the whole file
MAX_KEY = 255  # a longer bom-ref is not used as the name of a box: its place in the file is
MAX_LINES = 40  # the most lines of the file kept for one part
LINE_LIMIT = 200

TOP, SERVICE, SOFTWARE, ADDRESS = "top", "service", "software", "address"
ALGORITHM, PROTOCOL, CERTIFICATE, MATERIAL = "algorithm", "protocol", "certificate", "related-crypto-material"
# How a part uses an algorithm: by the last certificate or protocol on the file's own way from the part to it, else by
# a key, else (named by the part itself) by what kind of algorithm the file says it is.
THROUGH_CERTIFICATE, THROUGH_PROTOCOL, THROUGH_KEY = "certificate", "protocol", "key"
THROUGH_SIGNATURE, THROUGH_KEY_EXCHANGE, THROUGH_DIRECT = "signature", "key_exchange", "direct"
TOO_MANY = "This file names more references between its parts than Evidence Lab reads for the map."


@dataclass(frozen=True)
class Part:
    """The thing the file describes, a service, or a software component (anything that is no cryptographic asset)."""

    key: str  # its bom-ref, or its place in the file when it has none
    kind: str  # top | service | software
    name: str
    version: str | None
    type: str | None  # the file's own word for a component: application, library, ...
    where: str  # "metadata.component", "services[0]", "components[0]"
    addresses: tuple[str, ...] = ()  # a service's endpoints that are network addresses, as host:port
    endpoints: tuple[str, ...] = ()  # every endpoint as the file writes it


@dataclass(frozen=True)
class Asset:
    key: str
    kind: str  # algorithm | protocol | certificate | related-crypto-material
    name: str  # what the file calls it
    where: str
    algorithm: str | None = None  # an algorithm in the app's plain spelling ("ECDSA P-256"), or the file's own name
    primitive: str | None = None  # signature, key-agree, kem, hash, ...
    protocol: str | None = None  # "TLS 1.3", or the file's own words for another protocol
    addresses: tuple[str, ...] = ()  # where the file says it was seen (evidence.occurrences), as host:port


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    how: str  # dependsOn | provides | contains | cryptoRefArray | cipherSuites | signatureAlgorithmRef | ...
    where: str  # "dependencies[1]", "components[4]"


@dataclass(frozen=True)
class Use:
    """The file says this place uses this algorithm. `place` is the key of a service, of a software component or of
    the thing the file describes, or (kind "address") an address the file says an asset was seen at."""

    place_kind: str  # service | software | top | address
    place: str
    algorithm: str
    through: str


@dataclass
class Structure:
    top: Part | None
    services: list[Part] = field(default_factory=list)
    software: list[Part] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    uses: list[Use] = field(default_factory=list)
    # (place kind, place) -> the cryptographic assets the file's references lead to from there, nearest first
    reached: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    # for each part and asset, the short lines of the file that name it: (where, text)
    lines: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    # a bom-ref as the file writes it -> the key of the part or asset it names
    refs: dict[str, str] = field(default_factory=dict)


def _name(value: object, limit: int = 100) -> str:
    return (clean_text(value, limit) if isinstance(value, str) else "") or "(no name)"


def _word(value: object, limit: int = 50) -> str | None:
    return (clean_text(value, limit) or None) if isinstance(value, str) else None


def _props(comp: dict, name: str) -> dict:
    props = comp.get("cryptoProperties")
    inner = props.get(name) if isinstance(props, dict) else None
    return inner if isinstance(inner, dict) else {}


def _strings(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str) and v] if isinstance(value, list) else []


def _short(value: object) -> str:
    """One entry of the file as one short line of data: compact JSON, cleaned, cut to a line."""
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    except (TypeError, ValueError, RecursionError):
        text = ""
    return clean_text(text, LINE_LIMIT)


def _picked(entry: dict, names: tuple[str, ...]) -> dict:
    """The named fields of one entry that hold a short plain value (text or a number), for a line of data."""
    return {
        k: (clean_text(entry[k], 120) if isinstance(entry[k], str) else entry[k])
        for k in names
        if isinstance(entry.get(k), (str, int, float)) and not isinstance(entry.get(k), bool)
    }


def read_structure(data: bytes) -> Structure:
    """The structure of a CycloneDX 1.6 scanner file. Raises ImportFileError (one plain sentence) for a file the claim
    reader refuses, and for one with more services or references than this reader takes."""
    read_cbom(data)  # the importer's own reading first: its limits, its refusals, its words
    doc = _load_json(data)
    if not isinstance(doc, dict):  # (read_cbom has already said so; kept for the type check)
        raise ImportFileError("A CycloneDX file must be a JSON object at the top level.", line=1, field="(top level)")
    out = Structure(top=None)
    kinds: dict[str, str] = {}  # every key this reader made -> top | service | software | <asset kind>
    by_ref = out.refs  # a bom-ref as the file writes it -> the key of what it names (the first to use it)
    lines = out.lines

    def key_for(ref: object, where: str, kind: str) -> str:
        key = ref if isinstance(ref, str) and ref and len(ref) <= MAX_KEY and ref not in kinds else where
        kinds[key] = kind
        if isinstance(ref, str) and ref:
            by_ref.setdefault(ref, key)
        return key

    def note(key: str, where: str, text: str) -> None:
        found = lines.setdefault(key, [])
        if len(found) < MAX_LINES and (where, text) not in found[-3:]:
            found.append((where, text))

    # --- the services first: a `dependencies` line that names a service means the service (as the claim reader reads it)
    services = doc.get("services")
    listed = services if isinstance(services, list) else []
    if len(listed) > MAX_SERVICES:
        raise ImportFileError(f"This file lists more than {MAX_SERVICES} services.", field="services")
    for i, svc in enumerate(listed):
        if not isinstance(svc, dict):
            continue
        where = f"services[{i}]"
        key = key_for(svc.get("bom-ref"), where, SERVICE)
        given = svc.get("endpoints")
        endpoints: list = given if isinstance(given, list) else []
        addresses: list[str] = []
        for j, endpoint in enumerate(endpoints):
            try:
                hp = _endpoint(endpoint, f"{where}.endpoints[{j}]")
            except ImportFileError:
                hp = None
            if hp is not None and hp.address not in addresses:
                addresses.append(hp.address)
        written = tuple(clean_text(e, 120) for e in endpoints if isinstance(e, str))[:20]
        out.services.append(
            Part(
                key=key,
                kind=SERVICE,
                name=_name(svc.get("name")),
                version=_word(svc.get("version")),
                type=None,
                where=where,
                addresses=tuple(addresses),
                endpoints=written,
            )
        )
        note(key, where, _short({**_picked(svc, ("bom-ref", "name", "version")), "endpoints": list(written)}))

    # --- what the file describes
    meta = doc.get("metadata")
    described = meta.get("component") if isinstance(meta, dict) else None
    if isinstance(described, dict) and isinstance(described.get("name"), str) and clean_text(described["name"], 100):
        key = key_for(described.get("bom-ref"), "metadata.component", TOP)
        out.top = Part(
            key=key,
            kind=TOP,
            name=_name(described.get("name")),
            version=_word(described.get("version")),
            type=_word(described.get("type")),
            where="metadata.component",
        )
        note(key, "metadata.component", _short(_picked(described, ("type", "bom-ref", "name", "version"))))

    # --- every component: software, or a cryptographic asset
    comps: list[tuple[str, dict]] = []
    _walk_components(doc.get("components"), "components", comps)
    key_at: dict[str, str] = {}  # place in the file -> key
    raw: dict[str, dict] = {}
    for where, comp in comps:
        props = comp.get("cryptoProperties")
        if comp.get("type") != "cryptographic-asset":
            key = key_at[where] = key_for(comp.get("bom-ref"), where, SOFTWARE)
            out.software.append(
                Part(
                    key=key,
                    kind=SOFTWARE,
                    name=_name(comp.get("name")),
                    version=_word(comp.get("version")),
                    type=_word(comp.get("type")),
                    where=where,
                )
            )
            note(key, where, _short(_picked(comp, ("type", "bom-ref", "name", "version"))))
            continue
        kind = clean_text(props.get("assetType"), 40) if isinstance(props, dict) else ""
        key = key_at[where] = key_for(comp.get("bom-ref"), where, kind)
        raw[key] = comp
        algorithm = primitive = protocol = None
        shown = {**_picked(comp, ("bom-ref", "name")), "assetType": kind}
        if kind == ALGORITHM:
            ap = _props(comp, "algorithmProperties")
            name = comp.get("name")
            algorithm = (
                normalize_algorithm(name, ap.get("curve"), ap.get("parameterSetIdentifier"))
                if isinstance(name, str)
                else None
            ) or _name(name, 80)
            primitive = _word(ap.get("primitive"), 30)
            if primitive:
                shown["primitive"] = primitive
        elif kind == PROTOCOL:
            pp = _props(comp, "protocolProperties")
            ptype, version = _word(pp.get("type"), 30), pp.get("version")
            tls = normalize_tls_version(version) if ptype is not None and ptype.lower() == "tls" else None
            said = version if isinstance(version, (str, int, float)) and not isinstance(version, bool) else ""
            protocol = tls or clean_text(" ".join(str(x) for x in (ptype or "", said) if x != ""), 60) or None
            shown.update(_picked(pp, ("type", "version")))
        ev = comp.get("evidence")
        occurrences = ev.get("occurrences") if isinstance(ev, dict) else None
        seen: list[str] = []
        for j, occ in enumerate(occurrences if isinstance(occurrences, list) else []):
            if not isinstance(occ, dict) or len(seen) >= 20:
                continue
            try:
                hp = _occurrence(occ.get("location"), f"{where}.evidence.occurrences[{j}].location")
            except ImportFileError:
                hp = None
            if hp is not None and hp.address not in seen:
                seen.append(hp.address)
        out.assets.append(
            Asset(
                key=key,
                kind=kind,
                name=_name(comp.get("name"), 80),
                where=where,
                algorithm=algorithm,
                primitive=primitive,
                protocol=protocol,
                addresses=tuple(seen),
            )
        )
        note(key, where, _short(shown))

    # --- which names which
    edges = out.edges
    have: set[tuple[str, str, str]] = set()

    def link(source: str | None, named: object, how: str, where: str) -> str | None:
        """One reference of the file, kept once, between two things this reader knows. Returns the target's key."""
        target = by_ref.get(named) if isinstance(named, str) else None
        if source is None or target is None or source == target:
            return None
        if (source, target, how) not in have:
            if len(edges) >= MAX_REFERENCES:
                raise ImportFileError(TOO_MANY, field="dependencies")
            have.add((source, target, how))
            edges.append(Edge(source, target, how, where))
        return target

    for where, _comp in comps:  # a component listed inside another
        if ".components[" in where:
            parent = key_at.get(where.rsplit(".components[", 1)[0])
            child = key_at[where]
            if parent is not None and parent != child and (parent, child, "contains") not in have:
                if len(edges) >= MAX_REFERENCES:
                    raise ImportFileError(TOO_MANY, field="components")
                have.add((parent, child, "contains"))
                edges.append(Edge(parent, child, "contains", where))
    deps = doc.get("dependencies")
    for i, dep in enumerate(deps if isinstance(deps, list) else []):
        if not isinstance(dep, dict) or not isinstance(dep.get("ref"), str):
            continue
        owner, where = by_ref.get(dep["ref"]), f"dependencies[{i}]"
        targets = {how: _strings(dep.get(how)) for how in ("dependsOn", "provides")}
        if owner is None or not (targets["dependsOn"] or targets["provides"]):
            continue
        said = _short(
            {
                "ref": clean_text(dep["ref"], 80),
                **{how: [clean_text(t, 80) for t in found[:8]] for how, found in targets.items() if found},
            }
        )
        note(owner, where, said)
        for how, found in targets.items():
            for named in found:
                target = link(owner, named, how, where)
                if target is not None:
                    note(target, where, said)
    for asset in out.assets:
        comp = raw[asset.key]
        if asset.kind == PROTOCOL:
            pp = _props(comp, "protocolProperties")
            for named in _strings(pp.get("cryptoRefArray")):
                link(asset.key, named, "cryptoRefArray", asset.where)
            suites = pp.get("cipherSuites")
            for suite in suites if isinstance(suites, list) else []:
                for named in _strings(suite.get("algorithms")) if isinstance(suite, dict) else []:
                    link(asset.key, named, "cipherSuites", asset.where)
        elif asset.kind == CERTIFICATE:
            cp = _props(comp, "certificateProperties")
            for how in ("signatureAlgorithmRef", "subjectPublicKeyRef"):
                link(asset.key, cp.get(how), how, asset.where)
        elif asset.kind == MATERIAL:
            rp = _props(comp, "relatedCryptoMaterialProperties")
            link(asset.key, rp.get("algorithmRef"), "algorithmRef", asset.where)
    _walk_uses(out)
    return out


def _walk_uses(found: Structure) -> None:
    """Which place uses which algorithm, as the file's own references say: from a service, a software component or the
    thing the file describes, along `dependsOn`, `provides` and the assets' own references, through cryptographic
    assets only, to each algorithm that is reached. The walk stops at an algorithm and never passes through another
    part. An asset no service reaches, but that the file says was seen at an address (evidence.occurrences), is used at
    that address (the claim reader places it there the same way)."""
    below: dict[str, list[str]] = {}
    for e in found.edges:
        below.setdefault(e.source, []).append(e.target)
    assets = {a.key: a for a in found.assets}
    steps = 0
    have: set[tuple[str, str, str, str]] = set()

    def walk(place_kind: str, place: str, starts: list[str]) -> list[str]:
        """Record every algorithm reached from `starts`; returns every asset passed on the way, nearest first."""
        nonlocal steps
        passed: dict[str, None] = {}
        queue: deque[tuple[str, str | None]] = deque(dict.fromkeys((s, None) for s in starts if s in assets))
        seen: set[tuple[str, str | None]] = set(queue)
        while queue:
            key, carried = queue.popleft()
            steps += 1
            if steps > MAX_STEPS:
                raise ImportFileError(TOO_MANY, field="dependencies")
            asset = assets[key]
            passed.setdefault(key)
            if asset.kind == ALGORITHM:
                through = carried or (
                    THROUGH_SIGNATURE
                    if asset.primitive == "signature"
                    else THROUGH_KEY_EXCHANGE
                    if asset.primitive in ("key-agree", "kem")
                    else THROUGH_DIRECT
                )
                use = (place_kind, place, key, through)
                if use not in have:
                    have.add(use)
                    found.uses.append(Use(*use))
                continue
            carries = asset.kind if asset.kind in (CERTIFICATE, PROTOCOL) else (carried or THROUGH_KEY)
            for nxt in below.get(key, []):
                steps += 1
                if nxt in assets and (nxt, carries) not in seen:
                    seen.add((nxt, carries))
                    queue.append((nxt, carries))
        if passed:
            here = found.reached.setdefault((place_kind, place), [])
            here.extend(k for k in passed if k not in here)
        return list(passed)

    by_service: set[str] = set()
    for svc in found.services:
        by_service.update(walk(SERVICE, svc.key, below.get(svc.key, [])))
    for part in found.software:
        walk(SOFTWARE, part.key, below.get(part.key, []))
    if found.top is not None:
        walk(TOP, found.top.key, below.get(found.top.key, []))
    for asset in found.assets:
        if asset.addresses and asset.key not in by_service:
            for address in asset.addresses:
                walk(ADDRESS, address, [asset.key])


__all__ = [
    "ADDRESS",
    "ALGORITHM",
    "Asset",
    "CERTIFICATE",
    "Edge",
    "MATERIAL",
    "MAX_REFERENCES",
    "MAX_SERVICES",
    "MAX_STEPS",
    "PROTOCOL",
    "Part",
    "SERVICE",
    "SOFTWARE",
    "Structure",
    "THROUGH_CERTIFICATE",
    "THROUGH_DIRECT",
    "THROUGH_KEY",
    "THROUGH_KEY_EXCHANGE",
    "THROUGH_PROTOCOL",
    "THROUGH_SIGNATURE",
    "TOP",
    "Use",
    "read_structure",
]

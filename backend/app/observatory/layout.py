"""From the files alone to the map's boxes and lines (no results here: build.py lays the checks' words on them).

What is read: the claims of the scanner file (as Import keeps them), the structure of the same file when a copy was
kept (importer/structure.py), and the newest dependency list with its "Part of" ties as Dependencies shows them. Every
box, tie and line below names the fact in those files that it stands on; where the files say nothing, nothing is
drawn, and `Layout` keeps what is missing so the map can say so.

Boxes
- One box for each server: an address a service of the scanner file gives as an endpoint, an address the file says an
  asset was seen at, or an address a claim names. It is titled with the service's own name where the file gives one.
- One box for each signing program (and key exchange program) the claims name: the app's own list of programs
  (`research.programs`), so a box is the same thing as a group on Evidence and a system on the Migration plan.
- A software component of the scanner file that is no program is drawn only when the file ties it to something on the
  map: it uses an algorithm, or a service names it. The others are counted, not drawn.
- One box for each top entry of the dependency list (the customer's own software). A top entry tied to a server or a
  program (Dependencies' "Part of": by name and version, or set by a person) IS that server's or program's box; an
  untied one is a box of its own with nothing observed or run in it.

Lines (kind "uses": the files say one uses the other)
- A place to an algorithm: the scanner file's own references lead from the service or the component to the algorithm
  (importer/structure.py walks them); without a kept copy, the claim itself says so (a certificate claim names its
  algorithm, a program's claim names what it signs with).
- A service to a software component it names; a top entry (or the box it is tied to) to its libraries.
There is no line between an untied top entry and a server: the files do not say which software answers on an address.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.dependencies.tree import LOOSE
from app.engine import research
from app.importer import structure as S
from app.importer.common import NOT_STATED
from app.observatory.match import same_service

SCANNER, LISTED = "scanner", "dependencies"
SERVICE_BOX, LISTED_BOX = "service", "listed"  # the two containers: the scanner file's, and the dependency list's own
CLIENTS, THIS_COMPUTER = "clients", "this_computer"


@dataclass
class Box:
    key: str
    kind: str  # server | program | key_exchange_program | software | service | own_software
    title: str
    container: str
    label: str  # its real name in a sentence: the address, "acme-sign 1.4.2"
    address: str | None = None
    name: str | None = None  # a program's name and version, apart
    version: str | None = None
    files: list[str] = field(default_factory=list)
    ties: list[dict] = field(default_factory=list)  # top entries of the dependency list that are this box
    system: str | None = None  # the app's key for it as a system ("server:<address>", "software:<claim ref>")
    part: str | None = None  # its key in the scanner file's structure
    top: str | None = None  # an untied top entry: its key in the dependency list
    claims: list[dict] = field(default_factory=list)
    standing: bool = False  # the Migration plan measures it, so its post-quantum status has a place here


@dataclass
class Container:
    key: str
    title: str | None
    version: str | None
    named: str  # both | scanner | list | unnamed_scanner | claims | unnamed_list
    files: list[str]
    boxes: list[str] = field(default_factory=list)


@dataclass
class Layout:
    containers: list[Container] = field(default_factory=list)
    boxes: dict[str, Box] = field(default_factory=dict)
    algorithms: list[dict] = field(default_factory=list)  # {"key", "technical", "uses": [{"box", "through"}]}
    libraries: list[dict] = field(default_factory=list)  # {"key", "owner", "top", "top_label", "rows"}
    lines: list[dict] = field(default_factory=list)  # {"from", "to", "kind", "through" | "label"}
    unplaced: list[dict] = field(default_factory=list)  # claims the file puts on no system
    answered: set[str] = field(default_factory=set)  # servers whose software the files name
    untied: list[str] = field(default_factory=list)  # the labels of the top entries tied to nothing
    not_drawn: int = 0  # software components of the scanner file with nothing that puts them on the map
    merged: bool = False
    listed: bool = False
    index: dict[tuple, dict] = field(default_factory=dict)  # (kept while laying out: each line and each use once)

    def servers(self) -> list[Box]:
        return [b for b in self.boxes.values() if b.kind == "server"]

    def systems(self) -> list[Box]:
        """The servers and programs of the scanner file: what a top entry of the dependency list can be tied to."""
        return [b for b in self.boxes.values() if SCANNER in b.files and b.kind in ("server", "program")]

    def container_of(self, box: Box) -> Container | None:
        return next((c for c in self.containers if c.key == box.container), None)


def _label(name: object, version: object) -> str:
    return f"{name} {version}".strip() if version else str(name)


def lay_out(claims: list[dict], structure: S.Structure | None, listed: dict | None) -> Layout:
    """`claims`: the import's claims as dicts (id, ref, location, location_kind, kind, claimed_value, text, source,
    detail). `structure`: the scanner file's, or None (a CSV file, or no kept copy). `listed`: None without a
    dependency list, else {"described": (name, version) | None, "described_key", "groups"}, the groups being the
    Dependencies view's own (key, label, system, tie_source, rows)."""
    out = Layout(listed=listed is not None)
    top = structure.top if structure is not None else None
    described = listed.get("described") if listed else None
    out.merged = same_service((top.name, top.version) if top is not None else None, described)
    service = Container(
        key=SERVICE_BOX,
        title=top.name if top is not None else None,
        version=top.version if top is not None else None,
        named=(
            "both"
            if out.merged
            else "scanner"
            if top is not None
            else "unnamed_scanner"  # the file was read, and names no top component
            if structure is not None
            else "claims"  # drawn from the claims alone: what else the file names is not known here
        ),
        files=[SCANNER, LISTED] if out.merged else [SCANNER],
    )
    out.containers.append(service)
    own = service
    if listed is not None and not out.merged:
        own = Container(
            key=LISTED_BOX,
            title=str(described[0]) if described else None,
            version=str(described[1]) if described and described[1] else None,
            named="list" if described else "unnamed_list",
            files=[LISTED],
        )
        out.containers.append(own)

    def add(box: Box) -> Box:
        if box.key not in out.boxes:
            out.boxes[box.key] = box
            next(c for c in out.containers if c.key == box.container).boxes.append(box.key)
        return out.boxes[box.key]

    # ---- servers
    claim_servers = research.servers(claims)
    if structure is not None:
        for svc in structure.services:
            for address in svc.addresses:
                add(
                    Box(
                        key="server:" + address,
                        kind="server",
                        title=svc.name if svc.name != "(no name)" else address,
                        container=SERVICE_BOX,
                        label=address,
                        address=address,
                        files=[SCANNER],
                        system="server:" + address if address in claim_servers else None,
                        part=svc.key,
                        standing=address in claim_servers,
                    )
                )
            if not svc.addresses:
                add(
                    Box(
                        key="service:" + svc.key,
                        kind="service",
                        title=svc.name,
                        container=SERVICE_BOX,
                        label=svc.name,
                        files=[SCANNER],
                        part=svc.key,
                    )
                )
        seen_at = [u.place for u in structure.uses if u.place_kind == S.ADDRESS]
    else:
        seen_at = []
    for address in [*dict.fromkeys(seen_at), *claim_servers]:
        add(
            Box(
                key="server:" + address,
                kind="server",
                title=address,
                container=SERVICE_BOX,
                label=address,
                address=address,
                files=[SCANNER],
                system="server:" + address if address in claim_servers else None,
                standing=address in claim_servers,
            )
        )

    # ---- programs, and the other software the scanner file ties to something on the map
    programs = research.programs(claims)
    part_box: dict[str, str] = {}  # a part of the structure -> its box

    def program_box(p: dict, part: str | None) -> Box:
        signing = p.get("role") != "key_exchange"
        return add(
            Box(
                key="software:" + p["ref"],
                kind="program" if signing else "key_exchange_program",
                title=p["label"],
                container=SERVICE_BOX,
                label=p["label"],
                name=p["component"],
                version=p["version"],
                files=[SCANNER],
                system="software:" + p["ref"] if signing else None,
                part=part,
                standing=signing,
            )
        )

    if structure is not None:
        using = {u.place for u in structure.uses if u.place_kind == S.SOFTWARE}
        kinds = {p.key: p.kind for p in [*structure.services, *structure.software]}
        named_by_service = {
            e.target for e in structure.edges if kinds.get(e.source) == S.SERVICE and kinds.get(e.target) == S.SOFTWARE
        }
        mine: dict[str, list[dict]] = {}
        for p in programs:
            mine.setdefault(structure.refs.get(p["ref"], ""), []).append(p)
        for part in structure.software:
            if part.key in mine:
                for p in mine[part.key]:
                    part_box.setdefault(part.key, program_box(p, part.key).key)
            elif part.key in using or part.key in named_by_service:
                label = _label(part.name, part.version)
                box = add(
                    Box(
                        key="software:" + part.key,
                        kind="software",
                        title=label,
                        container=SERVICE_BOX,
                        label=label,
                        name=part.name,
                        version=part.version,
                        files=[SCANNER],
                        part=part.key,
                    )
                )
                part_box[part.key] = box.key
            else:
                out.not_drawn += 1
        if top is not None and top.key in mine:  # the file names the thing it describes as a program itself
            for p in mine[top.key]:
                part_box.setdefault(top.key, program_box(p, top.key).key)
    for p in programs:
        program_box(p, None)

    # ---- each claim on its box
    named: dict[tuple[str | None, str | None], list[Box]] = {}  # the programs, by name and version
    for b in out.boxes.values():
        if b.kind in ("program", "key_exchange_program"):
            named.setdefault((b.name, b.version), []).append(b)
    for claim in claims:
        placed: Box | None = None
        if claim.get("location_kind") == "server":
            placed = out.boxes.get("server:" + str(claim.get("location")))
        elif claim.get("location_kind") == "software":
            d = claim.get("detail") or {}
            whose = (str(d.get("component")), str(d["version"]) if d.get("version") else None)
            same = named.get(whose, [])
            wanted = "key_exchange_program" if claim.get("kind") == "key_exchange" else "program"
            exact = [b for b in same if b.key == "software:" + str(claim.get("ref")) and b.kind == wanted]
            fits = exact or [b for b in same if b.kind == wanted] or same
            placed = fits[0] if fits else None
            if placed is None and d.get("component"):
                # a claim about software that is no program of the app's (it has no test of its own): a box all the same
                label = _label(d.get("component"), d.get("version"))
                placed = add(
                    Box(
                        key="software:" + str(claim.get("ref")),
                        kind="software",
                        title=label,
                        container=SERVICE_BOX,
                        label=label,
                        name=whose[0],
                        version=whose[1],
                        files=[SCANNER],
                    )
                )
                named.setdefault(whose, []).append(placed)
        if placed is None:
            out.unplaced.append(claim)
        else:
            placed.claims.append(claim)

    # ---- the dependency list: its top entries, their ties and their libraries
    for group in (listed or {}).get("groups") or []:
        rows = group.get("rows") or []
        owner: str | None
        if group["key"] == LOOSE:
            owner = None
        elif group["key"] == (listed or {}).get("described_key"):
            owner = own.key
        else:
            tied = out.boxes.get(str(group.get("system"))) if group.get("system") else None
            if tied is not None:
                if LISTED not in tied.files:
                    tied.files.append(LISTED)
                tied.ties.append({"top": group["key"], "label": group["label"], "source": group.get("tie_source")})
                if tied.kind == "server":
                    out.answered.add(tied.key)
                owner = tied.key
            else:
                box = add(
                    Box(
                        key="top:" + group["key"],
                        kind="own_software",
                        title=group["label"],
                        container=own.key,
                        label=group["label"],
                        files=[LISTED],
                        top=group["key"],
                    )
                )
                out.untied.append(group["label"])
                owner = box.key
        if rows:
            key = "libraries:" + group["key"]
            out.libraries.append(
                {
                    "key": key,
                    "owner": owner,
                    "top": group["key"],
                    "top_label": None if group["key"] == LOOSE else group["label"],
                    "rows": rows,
                }
            )
            if owner is not None:
                out.lines.append({"from": owner, "to": key, "kind": "uses", "libraries": len(rows)})

    # ---- the cryptography lane: the algorithms, and the lines that say who uses each
    if structure is not None:
        _algorithms_from_structure(out, structure, part_box)
    else:
        _algorithms_from_claims(out)
    return out


def _line(out: Layout, source: str, target: str, through: str) -> None:
    """One "uses" line between two things on the map, kept once; a second way of using is added to the same line."""
    line = out.index.get((source, target))
    if line is None:
        line = out.index[(source, target)] = {"from": source, "to": target, "kind": "uses", "through": []}
        out.lines.append(line)
    if through not in line["through"]:
        line["through"].append(through)


def _use(out: Layout, by_key: dict[str, dict], algorithm: str, box: str, through: str) -> None:
    if (algorithm, box, through) not in out.index:
        out.index[(algorithm, box, through)] = {}
        by_key[algorithm]["uses"].append({"box": box, "through": through})
    _line(out, box, algorithm, through)


def _algorithms_from_structure(out: Layout, structure: S.Structure, part_box: dict[str, str]) -> None:
    by_key: dict[str, dict] = {}
    asset_box = {}
    for asset in structure.assets:
        if asset.kind == S.ALGORITHM:
            key = "algorithm:" + asset.key
            asset_box[asset.key] = key
            by_key[key] = {"key": key, "technical": asset.algorithm or asset.name, "part": asset.key, "uses": []}
            out.algorithms.append(by_key[key])
    services = {s.key: s for s in structure.services}
    for use in structure.uses:
        target = asset_box.get(use.algorithm)
        if target is None:
            continue
        if use.place_kind == S.SERVICE:
            svc = services[use.place]
            places = ["server:" + a for a in svc.addresses] or ["service:" + svc.key]
        elif use.place_kind == S.ADDRESS:
            places = ["server:" + use.place]
        elif use.place_kind == S.TOP:
            places = [part_box.get(use.place, SERVICE_BOX)]
        else:
            places = [part_box[use.place]] if use.place in part_box else []
        for place in places:
            if place in out.boxes or place == SERVICE_BOX:
                _use(out, by_key, target, place, use.through)
    # one part of the file names another: a service its software, software other software on the map, an algorithm
    # the algorithm it is built on
    kinds = {p.key: p.kind for p in [*structure.services, *structure.software]}
    for e in structure.edges:
        if e.source in asset_box and e.target in asset_box:
            _line(out, asset_box[e.source], asset_box[e.target], S.THROUGH_DIRECT)
            continue
        if kinds.get(e.target) != S.SOFTWARE or e.target not in part_box:
            continue
        if kinds.get(e.source) == S.SERVICE:
            svc = services[e.source]
            sources = ["server:" + a for a in svc.addresses] or ["service:" + svc.key]
            out.answered.update(s for s in sources if s.startswith("server:"))
        elif kinds.get(e.source) == S.SOFTWARE and e.source in part_box:
            sources = [part_box[e.source]]
        else:
            continue
        for source in sources:
            if source in out.boxes and source != part_box[e.target]:
                _line(out, source, part_box[e.target], S.THROUGH_DIRECT)


def _algorithms_from_claims(out: Layout) -> None:
    """Without the file's structure, a claim itself says who uses an algorithm: a certificate claim names the
    certificate's, a program's claim names what it signs or exchanges keys with."""
    by_key: dict[str, dict] = {}

    def named(technical: object) -> str | None:
        text = str(technical or "").strip()
        if not text or text == NOT_STATED:
            return None
        key = "algorithm:" + text
        if key not in by_key:
            by_key[key] = {"key": key, "technical": text, "part": None, "uses": []}
            out.algorithms.append(by_key[key])
        return key

    for box in out.boxes.values():
        for claim in box.claims:
            d = claim.get("detail") or {}
            kind = claim.get("kind")
            if kind == "certificate":
                found = [(d.get("algorithm") or claim.get("claimed_value"), S.THROUGH_CERTIFICATE)]
            elif kind == "signature_algorithm":
                found = [(d.get("algorithm") or claim.get("claimed_value"), S.THROUGH_SIGNATURE)]
            elif kind == "key_exchange" and box.kind != "server":
                found = [(d.get("algorithm") or claim.get("claimed_value"), S.THROUGH_KEY_EXCHANGE)]
            elif kind == "key_exchange":
                found = [(g, S.THROUGH_KEY_EXCHANGE) for g in d.get("groups") or []]
            else:
                found = []
            for technical, through in found:
                key = named(technical)
                if key is not None:
                    _use(out, by_key, key, box.key, through)


__all__ = [
    "Box",
    "CLIENTS",
    "Container",
    "LISTED",
    "LISTED_BOX",
    "Layout",
    "SCANNER",
    "SERVICE_BOX",
    "THIS_COMPUTER",
    "lay_out",
]

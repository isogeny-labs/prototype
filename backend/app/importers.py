"""Turn an uploaded file into a list of claims.

Pure parsing: nothing from a file is executed, used as a path, or used as a command.
Supported: CycloneDX 1.6 CBOM (JSON) and our CSV template (location,type,claim,value).
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .addresses import AddressError, HostPort, parse_address, validate_host, validate_port
from .config import MAX_CLAIMS_PER_FILE, MAX_UPLOAD_BYTES
from .names import (
    TLS_VERSIONS, clean_text, join_and, normalize_algorithm, normalize_group, normalize_tls_version,
)

KIND_ORDER = ["protocol_versions", "cipher_suites", "key_exchange", "certificate", "signature_algorithm"]
NOT_STATED = "(not stated in the file)"
CSV_HEADER = ["location", "type", "claim", "value"]
KNOWN_ASSET_TYPES = {"algorithm", "protocol", "certificate", "related-crypto-material"}


class ImportFileError(Exception):
    """The file can't be used. `line` or `field` says where the problem is."""

    def __init__(self, message: str, line: int | None = None, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.field = field


@dataclass
class ParsedClaim:
    ref: str
    location: str
    location_kind: str  # server | software | unknown
    kind: str
    claimed_value: str
    text: str
    source: str
    detail: dict = field(default_factory=dict)


@dataclass
class SkippedItem:
    """Something in the file that this version does not check. Shown under the claims, never dropped silently."""
    name: str    # what the file calls it, e.g. "SHA-256"
    what: str    # plain words, e.g. "Hash algorithm"
    source: str  # where in the file, same style as ParsedClaim.source
    reason: str


@dataclass
class ParsedFile:
    format: str  # cyclonedx-cbom | csv
    claims: list[ParsedClaim]
    skipped: list[SkippedItem] = field(default_factory=list)


# ---------------------------------------------------------------- shared helpers

def _decode(data: bytes) -> str:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImportFileError("This file is larger than 1 MB. Evidence Lab reads files up to 1 MB.")
    if not data.strip():
        raise ImportFileError("This file is empty.", line=1)
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        line = data[: exc.start].count(b"\n") + 1
        raise ImportFileError("This file is not plain UTF-8 text.", line=line) from exc


def detect_format(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".json"):
        return "cyclonedx-cbom"
    if name.endswith(".csv"):
        return "csv"
    head = data.lstrip(b"\xef\xbb\xbf \t\r\n")[:200]
    if head.startswith(b"{"):
        return "cyclonedx-cbom"
    first = head.split(b"\n", 1)[0].decode("utf-8", "replace")
    if [c.strip().lower() for c in first.split(",")] == CSV_HEADER:
        return "csv"
    raise ImportFileError(
        "We couldn't tell what kind of file this is. Upload a CycloneDX 1.6 CBOM (.json) or our CSV template (.csv).",
        field="filename",
    )


def parse_file(filename: str, data: bytes) -> ParsedFile:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImportFileError("This file is larger than 1 MB. Evidence Lab reads files up to 1 MB.")
    fmt = detect_format(filename, data)
    try:
        # A CSV row is either a claim or an error, so a CSV file never has skipped items.
        claims, skipped = read_cbom(data) if fmt == "cyclonedx-cbom" else (parse_csv(data), [])
    except RecursionError as exc:  # defensive: the depth limits should stop this first
        raise ImportFileError("This file is nested too deeply to read.", field="components") from exc
    return ParsedFile(format=fmt, claims=claims, skipped=skipped)


def _server_text(kind: str, where: str, detail: dict, claimed: str) -> str:
    if kind == "protocol_versions":
        if detail.get("unsupported_protocol"):
            return f"{where} uses {claimed}"
        return f"{where} accepts {join_and(detail['versions'])} only"
    if kind == "cipher_suites":
        return f"{where} accepts only these cipher suites: {claimed}"
    if kind == "key_exchange":
        return f"{where} uses only these key-exchange groups: {claimed}"
    if kind == "certificate":
        if not detail.get("algorithm") and claimed == NOT_STATED:
            return f"{where} has a certificate (the file does not say which algorithm)"
        return f"{where} certificate is {claimed}"
    return f"{where} signs with {claimed}"


def _sorted(claims: list[ParsedClaim]) -> list[ParsedClaim]:
    return sorted(claims, key=lambda c: KIND_ORDER.index(c.kind))  # stable: file order kept inside a kind


# ---------------------------------------------------------------- CSV template

_CSV_CLAIMS = {
    "tls": {"protocol_versions", "cipher_suites", "key_exchange", "certificate"},
    "software": {"signature_algorithm"},
}


def _split_values(value: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;|]", value) if p.strip()]


def parse_software_location(text: str) -> tuple[str, str] | None:
    """'acme-sign 1.4.2' or 'acme-sign@1.4.2' -> (name, version)."""
    m = re.fullmatch(r"\s*(\S(?:.*\S)?)(?:\s+|@)v?([0-9][^\s@]*)\s*", text)
    if not m:
        return None
    return clean_text(m.group(1), 100), clean_text(m.group(2), 50)


def parse_csv(data: bytes) -> list[ParsedClaim]:
    text = _decode(data)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    claims: list[ParsedClaim] = []
    header_seen = False
    try:
        for row in reader:
            line = reader.line_num
            cells = [c.strip() for c in row]
            if not any(cells):
                continue
            if not header_seen:
                if [c.lower() for c in cells] != CSV_HEADER:
                    raise ImportFileError(
                        "The first line must be exactly: location,type,claim,value", line=line, field="header"
                    )
                header_seen = True
                continue
            if len(cells) != 4:
                raise ImportFileError(
                    f"Line {line} has {len(cells)} columns; it needs 4 (location,type,claim,value). "
                    "Put quotes around a value that contains a comma.",
                    line=line,
                )
            if len(claims) >= MAX_CLAIMS_PER_FILE:
                raise ImportFileError(f"This file has more than {MAX_CLAIMS_PER_FILE} claims.", line=line)
            claims.append(_csv_row(line, *cells))
    except csv.Error as exc:
        raise ImportFileError(f"Line {reader.line_num} is not valid CSV ({exc}).", line=reader.line_num) from exc
    if not header_seen:
        raise ImportFileError("The first line must be exactly: location,type,claim,value", line=1, field="header")
    if not claims:
        raise ImportFileError("This file has the header line but no claims under it.", line=2)
    return _sorted(claims)


def _csv_row(line: int, location: str, type_: str, claim: str, value: str) -> ParsedClaim:
    def bad(message: str, fld: str) -> ImportFileError:
        return ImportFileError(f"Line {line}: {message}", line=line, field=fld)

    type_, claim = type_.lower(), claim.lower()
    if type_ not in _CSV_CLAIMS:
        raise bad(f"type {clean_text(type_, 40)!r} is not known. Use tls or software.", "type")
    if claim not in _CSV_CLAIMS[type_]:
        allowed = ", ".join(sorted(_CSV_CLAIMS[type_]))
        raise bad(f"claim {clean_text(claim, 40)!r} can't be used with type {type_}. Use one of: {allowed}.", "claim")
    if not value:
        raise bad("the value is empty.", "value")
    if not location:
        raise bad("the location is empty.", "location")
    ref, source = f"line-{line}", f"line {line}"

    if type_ == "software":
        parsed = parse_software_location(location)
        if not parsed:
            raise bad("a software location needs a name and a version, for example: acme-sign 1.4.2", "location")
        name, version = parsed
        algorithm = normalize_algorithm(value) or clean_text(value, 80)
        return _software_claim(ref, source, name, version, algorithm)

    try:
        hp = parse_address(location)
    except AddressError as exc:
        raise bad(f"{exc}", "location") from exc
    detail: dict = {"host": hp.host, "port": hp.port}
    if claim == "protocol_versions":
        versions = []
        for part in _split_values(value):
            v = normalize_tls_version(part)
            if not v:
                raise bad(f"{clean_text(part, 40)!r} is not a TLS version we know. Use TLS1.0, TLS1.1, TLS1.2 or TLS1.3 "
                          "(several: TLS1.2;TLS1.3).", "value")
            versions.append(v)
        detail["versions"] = [v for v in TLS_VERSIONS if v in versions]
        claimed = ", ".join(detail["versions"])
    elif claim == "cipher_suites":
        suites = [clean_text(p, 80) for p in _split_values(value)]
        for s in suites:
            if not re.fullmatch(r"[A-Za-z0-9_\-]+", s):
                raise bad(f"{s!r} is not a cipher suite name.", "value")
        detail["suites"] = list(dict.fromkeys(suites))
        claimed = ", ".join(detail["suites"])
    elif claim == "key_exchange":
        groups = []
        for part in _split_values(value):
            g = normalize_group(part)
            if not g:
                raise bad(f"{clean_text(part, 40)!r} is not a key-exchange group we can check. "
                          "Use X25519, P-256, P-384, P-521, X448, ffdhe2048 or ffdhe3072.", "value")
            groups.append(g)
        detail["groups"] = list(dict.fromkeys(groups))
        claimed = ", ".join(detail["groups"])
    else:  # certificate
        alg = normalize_algorithm(value)
        if not alg:
            raise bad(f"{clean_text(value, 40)!r} is not a certificate type we can check. "
                      "Use for example: ECDSA P-256, ECDSA P-384, RSA 2048, Ed25519.", "value")
        detail["algorithm"] = alg
        claimed = alg
    return ParsedClaim(ref, hp.address, "server", claim, claimed, _server_text(claim, hp.address, detail, claimed),
                       source, detail)


def _software_claim(ref: str, source: str, name: str, version: str, algorithm: str,
                    kind: str = "signature_algorithm") -> ParsedClaim:
    label = f"{name} {version}".strip()
    return ParsedClaim(
        ref=ref, location=label, location_kind="software", kind=kind, claimed_value=algorithm,
        text=f"signing component is {label} implementing {algorithm}" if kind == "signature_algorithm"
        else f"software component {label} uses {algorithm} for key exchange",
        source=source, detail={"component": name, "version": version, "algorithm": algorithm},
    )


# ---------------------------------------------------------------- CycloneDX 1.6 CBOM

def _load_json(data: bytes) -> object:
    text = _decode(data)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ImportFileError(f"This file is not valid JSON: {exc.msg} on line {exc.lineno}.", line=exc.lineno) from exc
    except RecursionError as exc:
        raise ImportFileError("This file is nested too deeply to read.", line=1) from exc


def _endpoint(text: object, where: str) -> HostPort | None:
    """A service endpoint ('https://host:port/path' or 'host:port') -> HostPort. None if it isn't a network address."""
    if not isinstance(text, str) or not text.strip():
        raise ImportFileError(f"{where} must be text such as https://localhost:8443", field=where)
    text = text.strip()
    try:
        if "://" in text:
            parts = urlsplit(text)
            if parts.scheme.lower() not in ("https", "tls", "wss", "tcp"):
                return None
            host = parts.hostname or ""
            try:
                port = parts.port
            except ValueError as exc:
                raise AddressError("the port must be a whole number from 1 to 65535") from exc
            return HostPort(validate_host(host), validate_port(port if port is not None else 443))
        return parse_address(text)
    except (AddressError, ValueError) as exc:
        raise ImportFileError(f"{where}: {clean_text(text, 80)!r} is not a usable address ({exc}).", field=where) from exc


def _occurrence(text: object, where: str) -> HostPort | None:
    """An evidence.occurrences location. Only host:port (or a URL) counts; file paths and the like are ignored."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    if "://" in text:
        try:
            return _endpoint(text, where)
        except ImportFileError:
            return None
    m = re.fullmatch(r"(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.\-]+):([0-9]+)", text)
    if not m:
        return None
    try:
        return parse_address(text)
    except AddressError as exc:
        raise ImportFileError(f"{where}: {clean_text(text, 80)!r} is not a usable address ({exc}).", field=where) from exc


MAX_COMPONENT_DEPTH = 50


def _walk_components(items: object, path: str, out: list, depth: int = 1) -> None:
    if items is None:
        return
    if depth > MAX_COMPONENT_DEPTH:
        where = path if len(path) <= 120 else path[:60] + "…" + path[-55:]
        raise ImportFileError(f"{where}: components are nested more than {MAX_COMPONENT_DEPTH} levels deep, "
                              "which is deeper than Evidence Lab reads.", field=where)
    if not isinstance(items, list):
        raise ImportFileError(f"{path} must be a list.", field=path)
    for i, comp in enumerate(items):
        here = f"{path}[{i}]"
        if not isinstance(comp, dict):
            raise ImportFileError(f"{here} must be an object.", field=here)
        out.append((here, comp))
        if "components" in comp:
            _walk_components(comp["components"], f"{here}.components", out, depth + 1)
        if len(out) > 5000:
            raise ImportFileError("This file lists more than 5000 components.", field=path)


def _str_list(value: object, where: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ImportFileError(f"{where} must be a list of references.", field=where)
    return value


# Kinds of algorithm this version does not check, in plain words: primitive -> (one, many).
_UNCHECKED_ALGORITHMS = {
    "hash": ("Hash algorithm", "Hash algorithms"),
    "xof": ("Hash algorithm", "Hash algorithms"),
    "block-cipher": ("Encryption algorithm", "Encryption algorithms"),
    "stream-cipher": ("Encryption algorithm", "Encryption algorithms"),
    "ae": ("Encryption algorithm", "Encryption algorithms"),
    "pke": ("Public-key encryption algorithm", "Public-key encryption algorithms"),
    "mac": ("Message authentication code (MAC)", "Message authentication codes (MACs)"),
    "kdf": ("Key derivation function", "Key derivation functions"),
    "drbg": ("Random number generator", "Random number generators"),
}
_MATERIAL_WORDS = {
    "public-key": "Public key", "private-key": "Private key", "secret-key": "Secret key", "key": "Key",
    "password": "Password", "credential": "Credential", "token": "Token", "shared-secret": "Shared secret",
    "digest": "Digest", "signature": "Signature", "nonce": "Nonce", "seed": "Seed", "salt": "Salt",
    "initialization-vector": "Initialization vector", "ciphertext": "Ciphertext", "tag": "Tag",
    "additional-data": "Additional data",
}


def _shown_name(comp: dict) -> str:
    name = comp.get("name")
    return (clean_text(name, 80) if isinstance(name, str) else "") or "(no name)"


def _skipped_asset(comp: dict, asset_type: str, props: dict, source: str) -> SkippedItem:
    """Why an asset that is in no claim was left out. Only the name is shown, never a key's value."""
    if asset_type == "algorithm":
        ap = props.get("algorithmProperties") if isinstance(props.get("algorithmProperties"), dict) else {}
        primitive = ap.get("primitive")
        if primitive in ("signature", "key-agree", "kem"):
            what = "Signature algorithm" if primitive == "signature" else "Key-exchange algorithm"
            reason = "Only named as part of a certificate or protocol in the file; not checked on its own in this version"
        elif primitive in _UNCHECKED_ALGORITHMS:
            what, many = _UNCHECKED_ALGORITHMS[primitive]
            reason = f"{many} are not checked in this version"
        else:
            what, reason = "Algorithm", "This kind of algorithm is not checked in this version"
    else:  # related-crypto-material
        rp = props.get("relatedCryptoMaterialProperties")
        what = _MATERIAL_WORDS.get(rp.get("type") if isinstance(rp, dict) else None, "Key or other crypto material")
        reason = "Keys and other crypto material are not checked in this version"
    return SkippedItem(_shown_name(comp), what, source, reason)


def parse_cbom(data: bytes) -> list[ParsedClaim]:
    return read_cbom(data)[0]


def read_cbom(data: bytes) -> tuple[list[ParsedClaim], list[SkippedItem]]:
    """The claims in a CBOM, plus every cryptographic item in it that did not become (part of) a claim."""
    doc = _load_json(data)
    if not isinstance(doc, dict):
        raise ImportFileError("A CycloneDX file must be a JSON object at the top level.", line=1, field="(top level)")
    if "bomFormat" not in doc:
        raise ImportFileError('This doesn\'t look like a CycloneDX file: the "bomFormat" field is missing.', field="bomFormat")
    if doc["bomFormat"] != "CycloneDX":
        raise ImportFileError('"bomFormat" must be "CycloneDX".', field="bomFormat")
    if "specVersion" not in doc:
        raise ImportFileError('The "specVersion" field is missing. Evidence Lab reads CycloneDX 1.6.', field="specVersion")
    if doc["specVersion"] != "1.6":
        raise ImportFileError(
            f'"specVersion" is {clean_text(doc["specVersion"], 20)!r}. Evidence Lab reads CycloneDX 1.6 only.',
            field="specVersion",
        )

    comps: list[tuple[str, dict]] = []
    _walk_components(doc.get("components"), "components", comps)
    meta = doc.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        raise ImportFileError("metadata must be an object.", field="metadata")
    meta_comp = (meta or {}).get("component")
    if isinstance(meta_comp, dict):
        comps.append(("metadata.component", meta_comp))

    by_ref: dict[str, tuple[str, dict]] = {}
    assets: list[tuple[str, dict, str, dict]] = []  # (path, component, assetType, cryptoProperties)
    for path, comp in comps:
        ref = comp.get("bom-ref")
        if ref is not None:
            if not isinstance(ref, str) or not ref:
                raise ImportFileError(f"{path}.bom-ref must be text.", field=f"{path}.bom-ref")
            if ref in by_ref:
                raise ImportFileError(f"{path}.bom-ref {clean_text(ref, 60)!r} is used twice.", field=f"{path}.bom-ref")
            by_ref[ref] = (path, comp)
        if comp.get("type") != "cryptographic-asset":
            continue
        props = comp.get("cryptoProperties")
        if not isinstance(props, dict):
            raise ImportFileError(f"{path} is a cryptographic asset but has no cryptoProperties.",
                                  field=f"{path}.cryptoProperties")
        asset_type = props.get("assetType")
        if asset_type not in KNOWN_ASSET_TYPES:
            raise ImportFileError(
                f"{path}.cryptoProperties.assetType is {clean_text(asset_type, 40)!r}. "
                "Expected algorithm, protocol, certificate or related-crypto-material.",
                field=f"{path}.cryptoProperties.assetType",
            )
        if not isinstance(ref, str):
            raise ImportFileError(f"{path} needs a bom-ref so we can tell where it is used.", field=f"{path}.bom-ref")
        assets.append((path, comp, asset_type, props))
    if not any(t != "related-crypto-material" for _, _, t, _ in assets):
        raise ImportFileError(
            "This file has no cryptographic assets (algorithms, protocols or certificates), so there is nothing to check.",
            field="components",
        )

    # --- where things are used: services (endpoints) and dependencies
    service_addr: dict[str, list[HostPort]] = {}
    services = doc.get("services")
    if services is not None and not isinstance(services, list):
        raise ImportFileError("services must be a list.", field="services")
    for i, svc in enumerate(services or []):
        if not isinstance(svc, dict):
            raise ImportFileError(f"services[{i}] must be an object.", field=f"services[{i}]")
        endpoints = svc.get("endpoints")
        if endpoints is not None and not isinstance(endpoints, list):
            raise ImportFileError(f"services[{i}].endpoints must be a list.", field=f"services[{i}].endpoints")
        found = [_endpoint(e, f"services[{i}].endpoints[{j}]") for j, e in enumerate(endpoints or [])]
        if isinstance(svc.get("bom-ref"), str):
            service_addr[svc["bom-ref"]] = [hp for hp in found if hp]

    deps = doc.get("dependencies")
    if deps is not None and not isinstance(deps, list):
        raise ImportFileError("dependencies must be a list.", field="dependencies")
    located: dict[str, list[HostPort]] = {}
    software_uses: list[tuple[str, str]] = []  # (software ref, asset ref)
    referenced: set[str] = set()
    asset_refs = {comp["bom-ref"] for _, comp, _, _ in assets}
    for i, dep in enumerate(deps or []):
        if not isinstance(dep, dict) or not isinstance(dep.get("ref"), str):
            raise ImportFileError(f"dependencies[{i}] needs a ref.", field=f"dependencies[{i}].ref")
        owner = dep["ref"]
        targets = _str_list(dep.get("dependsOn"), f"dependencies[{i}].dependsOn") + \
            _str_list(dep.get("provides"), f"dependencies[{i}].provides")
        for target in targets:
            if target not in asset_refs:
                continue
            if owner in service_addr:
                located.setdefault(target, []).extend(service_addr[owner])
            elif owner in asset_refs:
                if by_ref[owner][1]["cryptoProperties"].get("assetType") in ("certificate", "protocol"):
                    referenced.add(target)  # part of that certificate/protocol claim, not a claim of its own
            elif owner in by_ref:
                software_uses.append((owner, target))

    def add_loc(ref: str, hps: list[HostPort]) -> None:
        cur = located.setdefault(ref, [])
        for hp in hps:
            if hp not in cur:
                cur.append(hp)

    for ref in list(located):
        located[ref] = list(dict.fromkeys(located[ref]))
    # fallback: the asset's own evidence.occurrences
    for path, comp, _, _ in assets:
        if located.get(comp["bom-ref"]):
            continue
        ev = comp.get("evidence")
        occs = ev.get("occurrences") if isinstance(ev, dict) else None
        if isinstance(occs, list):
            for j, occ in enumerate(occs):
                if isinstance(occ, dict):
                    hp = _occurrence(occ.get("location"), f"{path}.evidence.occurrences[{j}].location")
                    if hp:
                        add_loc(comp["bom-ref"], [hp])
    # references between assets; a certificate named by a located protocol sits at the same address
    for path, comp, asset_type, props in assets:
        if asset_type == "protocol":
            pp = props.get("protocolProperties") if isinstance(props.get("protocolProperties"), dict) else {}
            refs = pp.get("cryptoRefArray") if isinstance(pp.get("cryptoRefArray"), list) else []
            for r in refs:
                if isinstance(r, str) and r in asset_refs:
                    referenced.add(r)
                    kind_of = by_ref[r][1]["cryptoProperties"].get("assetType")
                    if kind_of == "certificate" and not located.get(r) and located.get(comp["bom-ref"]):
                        add_loc(r, located[comp["bom-ref"]])
            for suite in pp.get("cipherSuites") if isinstance(pp.get("cipherSuites"), list) else []:
                if isinstance(suite, dict):
                    for r in suite.get("algorithms") if isinstance(suite.get("algorithms"), list) else []:
                        if isinstance(r, str):
                            referenced.add(r)
        elif asset_type == "certificate":
            cp = props.get("certificateProperties") if isinstance(props.get("certificateProperties"), dict) else {}
            for key in ("signatureAlgorithmRef", "subjectPublicKeyRef"):
                if isinstance(cp.get(key), str):
                    referenced.add(cp[key])
    for path, comp, asset_type, props in assets:
        # the algorithm of a key counts as "part of a certificate claim" only if a certificate uses that key
        if asset_type == "related-crypto-material" and comp["bom-ref"] in referenced:
            rp = props.get("relatedCryptoMaterialProperties")
            if isinstance(rp, dict) and isinstance(rp.get("algorithmRef"), str):
                referenced.add(rp["algorithmRef"])

    def algorithm_of(ref: object, size: object = None) -> str | None:
        """Plain name of an algorithm asset, e.g. 'ECDSA P-256' (or the file's own spelling if we don't know it)."""
        if not isinstance(ref, str) or ref not in by_ref:
            return None
        comp = by_ref[ref][1]
        props = comp.get("cryptoProperties") if isinstance(comp.get("cryptoProperties"), dict) else {}
        if props.get("assetType") != "algorithm":
            return None
        ap = props.get("algorithmProperties") if isinstance(props.get("algorithmProperties"), dict) else {}
        name = comp.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        return normalize_algorithm(name, ap.get("curve"), size or ap.get("parameterSetIdentifier")) \
            or clean_text(name, 80)

    claims: list[ParsedClaim] = []
    tls_by_addr: dict[str, dict] = {}
    in_a_claim: set[str] = set()  # assets that became a claim, or that a claim's value was read from
    bad_suites: dict[str, list[SkippedItem]] = {}  # protocol bom-ref -> cipher suite entries we could not use

    def src(path: str, comp: dict) -> str:
        return f"{path} (bom-ref {clean_text(comp['bom-ref'], 80)})"

    for path, comp, asset_type, props in assets:
        ref = comp["bom-ref"]
        places = located.get(ref) or []
        if asset_type in ("protocol", "certificate"):
            in_a_claim.add(ref)  # these always become a claim (or stop the import with an error)
        if asset_type == "protocol":
            pp = props.get("protocolProperties")
            if not isinstance(pp, dict):
                raise ImportFileError(f"{path} is a protocol but has no protocolProperties.",
                                      field=f"{path}.cryptoProperties.protocolProperties")
            ptype = pp.get("type")
            vfield = f"{path}.cryptoProperties.protocolProperties.version"
            if not isinstance(ptype, str) or not ptype:
                raise ImportFileError(f"{path}: the protocol type is missing.",
                                      field=f"{path}.cryptoProperties.protocolProperties.type")
            if ptype.lower() != "tls":
                label = clean_text(f"{ptype.upper()} {pp.get('version') or ''}", 60)
                detail = {"unsupported_protocol": clean_text(ptype, 30)}
                for where, kind_, d in _places(places):
                    claims.append(ParsedClaim(ref, where, kind_, "protocol_versions", label,
                                              _server_text("protocol_versions", _where_words(where, kind_), {**detail, **d}, label),
                                              src(path, comp), {**detail, **d}))
                continue
            if pp.get("version") in (None, ""):
                # Real scanners sometimes list "TLS" without a version. Keep it; Verify will say Couldn't check.
                detail = {"version_not_stated": True}
                cs = pp.get("cipherSuites")
                for k, s in enumerate(cs if isinstance(cs, list) else []):
                    bad_suites.setdefault(ref, []).append(SkippedItem(
                        _shown_name(s) if isinstance(s, dict) else "(no name)", "Cipher suite",
                        f"{path}.cryptoProperties.protocolProperties.cipherSuites[{k}] (bom-ref {clean_text(ref, 80)})",
                        "The file gives no TLS version for this cipher suite, so it is not checked"))
                for where, kind_, d in _places(places):
                    words = _where_words(where, kind_)
                    claims.append(ParsedClaim(ref, where, kind_, "protocol_versions", "TLS (version not stated)",
                                              f"{words} uses TLS (the file does not say which versions)",
                                              src(path, comp), {**detail, **d}))
                continue
            version = normalize_tls_version(pp["version"])
            if not version:
                raise ImportFileError(
                    f"{path}: {clean_text(pp['version'], 20)!r} is not a TLS version we know (1.0, 1.1, 1.2 or 1.3).",
                    field=vfield)
            suites = []
            cs = pp.get("cipherSuites")
            if cs is not None:
                if not isinstance(cs, list):
                    raise ImportFileError(f"{path}: cipherSuites must be a list.",
                                          field=f"{path}.cryptoProperties.protocolProperties.cipherSuites")
                for k, s in enumerate(cs):
                    if isinstance(s, dict) and isinstance(s.get("name"), str) and re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", s["name"]):
                        suites.append(s["name"])
                    else:
                        bad_suites.setdefault(ref, []).append(SkippedItem(
                            _shown_name(s) if isinstance(s, dict) else "(no name)", "Cipher suite",
                            f"{path}.cryptoProperties.protocolProperties.cipherSuites[{k}] (bom-ref {clean_text(ref, 80)})",
                            "This cipher suite has no name in a form this version can check"))
            for where, kind_, d in _places(places):
                key = where if kind_ == "server" else f"unknown:{ref}"
                group = tls_by_addr.setdefault(key, {"where": where, "kind": kind_, "d": d, "ref": ref,
                                                     "versions": [], "suites": [], "sources": []})
                group["versions"].append(version)
                group["suites"].extend(suites)
                group["sources"].append(src(path, comp))
        elif asset_type == "certificate":
            cp = props.get("certificateProperties") if isinstance(props.get("certificateProperties"), dict) else {}
            alg = None
            key_ref = cp.get("subjectPublicKeyRef")
            if isinstance(key_ref, str) and key_ref in by_ref:
                kprops = by_ref[key_ref][1].get("cryptoProperties")
                rp = kprops.get("relatedCryptoMaterialProperties") if isinstance(kprops, dict) else None
                if isinstance(rp, dict):
                    alg = algorithm_of(rp.get("algorithmRef"), rp.get("size"))
                    if alg:
                        in_a_claim.update((key_ref, rp["algorithmRef"]))
            if not alg:
                alg = algorithm_of(cp.get("signatureAlgorithmRef"))
                if alg:
                    in_a_claim.add(cp["signatureAlgorithmRef"])
            claimed = alg or NOT_STATED
            for where, kind_, d in _places(places):
                detail = {**d, "algorithm": normalize_algorithm(alg) if alg else None}
                claims.append(ParsedClaim(ref, where, kind_, "certificate", claimed,
                                          _server_text("certificate", _where_words(where, kind_), detail, claimed),
                                          src(path, comp), detail))
        elif asset_type == "algorithm":
            ap = props.get("algorithmProperties") if isinstance(props.get("algorithmProperties"), dict) else {}
            primitive = ap.get("primitive")
            kind = {"signature": "signature_algorithm", "key-agree": "key_exchange", "kem": "key_exchange"}.get(primitive)
            if not kind:
                continue  # hashes, ciphers etc. are not something this version checks; listed as skipped below
            alg = algorithm_of(ref)
            if not alg:
                raise ImportFileError(f"{path}: the algorithm has no name.", field=f"{path}.name")
            users = [s for s, a in software_uses if a == ref]
            for sref in users:
                spath, scomp = by_ref[sref]
                name = scomp.get("name")
                if not isinstance(name, str) or not name.strip():
                    raise ImportFileError(f"{spath}: the component has no name.", field=f"{spath}.name")
                version = scomp.get("version")
                claims.append(_software_claim(sref, f"{spath} (bom-ref {clean_text(sref, 80)}) provides {src(path, comp)}",
                                              clean_text(name, 100), clean_text(version, 50) if isinstance(version, str) else "",
                                              alg, kind))
            if users:
                in_a_claim.add(ref)
            if users or ref in referenced:
                continue
            in_a_claim.add(ref)
            for where, kind_, d in _places(places):
                words = _where_words(where, kind_)
                text = f"{words} signs with {alg}" if kind == "signature_algorithm" else f"{words} uses {alg} for key exchange"
                claims.append(ParsedClaim(ref, where, kind_, kind, alg, text, src(path, comp),
                                          {**d, "algorithm": alg, "from_algorithm_asset": True}))

    for group in tls_by_addr.values():
        versions = [v for v in TLS_VERSIONS if v in group["versions"]]
        detail = {**group["d"], "versions": versions}
        words = _where_words(group["where"], group["kind"])
        source = "; ".join(dict.fromkeys(group["sources"]))
        claimed = ", ".join(versions)
        claims.append(ParsedClaim(group["ref"], group["where"], group["kind"], "protocol_versions", claimed,
                                  _server_text("protocol_versions", words, detail, claimed), source, detail))
        suites = list(dict.fromkeys(group["suites"]))
        if suites:
            d2 = {**group["d"], "suites": suites}
            claimed = ", ".join(suites)
            claims.append(ParsedClaim(group["ref"], group["where"], group["kind"], "cipher_suites", claimed,
                                      _server_text("cipher_suites", words, d2, claimed), source, d2))

    if not claims:
        raise ImportFileError(
            "This file has cryptographic assets, but none are a kind Evidence Lab checks "
            "(TLS protocols, certificates, signature or key-exchange algorithms).", field="components")
    if len(claims) > MAX_CLAIMS_PER_FILE:
        raise ImportFileError(f"This file has more than {MAX_CLAIMS_PER_FILE} claims.", field="components")

    # Everything cryptographic that is in no claim is listed, in file order, so nothing is left out silently.
    skipped: list[SkippedItem] = []
    for path, comp, asset_type, props in assets:
        if comp["bom-ref"] not in in_a_claim:
            skipped.append(_skipped_asset(comp, asset_type, props, src(path, comp)))
        skipped.extend(bad_suites.get(comp["bom-ref"], []))
    return _sorted(claims), skipped


def _places(places: list[HostPort]) -> list[tuple[str, str, dict]]:
    """Every address an asset is used at, or one 'unknown' place. A claim is never dropped for lack of a location."""
    if not places:
        return [(NOT_STATED, "unknown", {})]
    return [(hp.address, "server", {"host": hp.host, "port": hp.port}) for hp in places]


def _where_words(where: str, kind: str) -> str:
    return where if kind == "server" else "A system the file does not name"

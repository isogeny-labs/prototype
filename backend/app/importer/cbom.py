"""CycloneDX 1.6 CBOM (JSON) -> claims, plus every cryptographic item that did not become a claim."""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from app.checks.addresses import AddressError, HostPort, parse_address, validate_host, validate_port
from app.config import MAX_CLAIMS_PER_FILE
from app.importer.common import (
    ImportFileError, NOT_STATED, ParsedClaim, SkippedItem, _places, _server_text, _sorted, _software_claim, _decode,
    _where_words,
)
from app.names import TLS_VERSIONS, clean_text, normalize_algorithm, normalize_tls_version

KNOWN_ASSET_TYPES = {"algorithm", "protocol", "certificate", "related-crypto-material"}


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


def _check_top_level(doc: object) -> None:
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


def _collect_assets(doc: dict) -> tuple[dict[str, tuple[str, dict]], list[tuple[str, dict, str, dict]]]:
    """Every component with a bom-ref, and the cryptographic assets among them."""
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
    return by_ref, assets


def _service_addresses(doc: dict) -> dict[str, list[HostPort]]:
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
    return service_addr


def _dependencies(doc: dict, assets: list, by_ref: dict, service_addr: dict) -> tuple[dict, list, set, set]:
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
    return located, software_uses, referenced, asset_refs


def _occurrences_fallback(assets: list, located: dict):
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
    return add_loc


def _references_between_assets(assets: list, by_ref: dict, asset_refs: set, located: dict, referenced: set, add_loc) -> None:
    # references between assets; a certificate named by a located protocol sits at the same address
    for path, comp, asset_type, props in assets:  # noqa: B007
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


def _algorithms_of_keys(assets: list, referenced: set) -> None:
    for path, comp, asset_type, props in assets:  # noqa: B007
        # the algorithm of a key counts as "part of a certificate claim" only if a certificate uses that key
        if asset_type == "related-crypto-material" and comp["bom-ref"] in referenced:
            rp = props.get("relatedCryptoMaterialProperties")
            if isinstance(rp, dict) and isinstance(rp.get("algorithmRef"), str):
                referenced.add(rp["algorithmRef"])


def _build_claims(assets: list, by_ref: dict, located: dict, software_uses: list, referenced: set):
    """The claims, one asset at a time. The TLS claims are only collected per address here (see _group_tls_by_address)."""
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
    return claims, tls_by_addr, in_a_claim, bad_suites, src


def _group_tls_by_address(claims: list[ParsedClaim], tls_by_addr: dict) -> None:
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


def _check_claim_count(claims: list[ParsedClaim]) -> None:
    if not claims:
        raise ImportFileError(
            "This file has cryptographic assets, but none are a kind Evidence Lab checks "
            "(TLS protocols, certificates, signature or key-exchange algorithms).", field="components")
    if len(claims) > MAX_CLAIMS_PER_FILE:
        raise ImportFileError(f"This file has more than {MAX_CLAIMS_PER_FILE} claims.", field="components")


def _skipped_items(assets: list, in_a_claim: set, bad_suites: dict, src) -> list[SkippedItem]:
    # Everything cryptographic that is in no claim is listed, in file order, so nothing is left out silently.
    skipped: list[SkippedItem] = []
    for path, comp, asset_type, props in assets:
        if comp["bom-ref"] not in in_a_claim:
            skipped.append(_skipped_asset(comp, asset_type, props, src(path, comp)))
        skipped.extend(bad_suites.get(comp["bom-ref"], []))
    return skipped


def parse_cbom(data: bytes) -> list[ParsedClaim]:
    return read_cbom(data)[0]


def read_cbom(data: bytes) -> tuple[list[ParsedClaim], list[SkippedItem]]:
    """The claims in a CBOM, plus every cryptographic item in it that did not become (part of) a claim."""
    doc = _load_json(data)
    _check_top_level(doc)

    by_ref, assets = _collect_assets(doc)

    service_addr = _service_addresses(doc)
    located, software_uses, referenced, asset_refs = _dependencies(doc, assets, by_ref, service_addr)
    add_loc = _occurrences_fallback(assets, located)
    _references_between_assets(assets, by_ref, asset_refs, located, referenced, add_loc)
    _algorithms_of_keys(assets, referenced)

    claims, tls_by_addr, in_a_claim, bad_suites, src = _build_claims(assets, by_ref, located, software_uses, referenced)
    _group_tls_by_address(claims, tls_by_addr)
    _check_claim_count(claims)

    skipped = _skipped_items(assets, in_a_claim, bad_suites, src)
    return _sorted(claims), skipped

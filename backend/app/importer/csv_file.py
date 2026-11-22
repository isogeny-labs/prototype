"""Our CSV template (location,type,claim,value) -> claims and settings."""
from __future__ import annotations

import csv
import io
import re

from app.checks.addresses import AddressError, parse_address
from app.config import MAX_CLAIMS_PER_FILE
from app.importer.common import (
    CSV_HEADER, ImportFileError, ParsedClaim, ParsedSetting, _decode, _server_text, _sorted, _software_claim,
    _split_values, parse_software_location,
)
from app.names import (
    TLS_VERSIONS, clean_text, normalize_algorithm, normalize_group, normalize_tls_version,
)


# ---------------------------------------------------------------- CSV template

_CSV_CLAIMS = {
    "tls": {"protocol_versions", "cipher_suites", "key_exchange", "certificate", "post_quantum"},
    "software": {"signature_algorithm", "key_exchange"},   # key_exchange for software since phase 4c (for example ML-KEM-768)
}
# Phase 4a: what a file may claim about a server's post-quantum key exchange, and the settings it may give a system.
POST_QUANTUM_VALUES = {"classical": "Classical", "hybrid": "Hybrid", "postquantumonly": "Post-quantum only", "pqonly": "Post-quantum only"}
_CSV_SETTINGS = {
    "data_lifespan": ("lifespan", {"short": "short", "shortlived": "short", "long": "long", "longlived": "long"}, "short or long-lived"),
    "exposure": ("exposure", {"internetfacing": "internet", "internet": "internet", "internal": "internal"}, "internet-facing or internal"),
    "can_change": ("can_change", {"yes": "yes", "no": "no"}, "yes or no"),
}


def parse_csv(data: bytes) -> list[ParsedClaim]:
    return parse_csv_rows(data)[0]


def parse_csv_rows(data: bytes) -> tuple[list[ParsedClaim], list[ParsedSetting]]:
    """(the claims, the settings rows). A settings row has type `system`; it must be about a system the file also
    makes a claim about."""
    text = _decode(data)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    claims: list[ParsedClaim] = []
    settings: list[tuple[int, ParsedSetting]] = []
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
            if len(claims) + len(settings) >= MAX_CLAIMS_PER_FILE:
                raise ImportFileError(f"This file has more than {MAX_CLAIMS_PER_FILE} claims.", line=line)
            if cells[1].lower() == "system":
                settings.append((line, _csv_setting(line, *cells)))
            else:
                claims.append(_csv_row(line, *cells))
    except csv.Error as exc:
        raise ImportFileError(f"Line {reader.line_num} is not valid CSV ({exc}).", line=reader.line_num) from exc
    if not header_seen:
        raise ImportFileError("The first line must be exactly: location,type,claim,value", line=1, field="header")
    if not claims:
        raise ImportFileError("This file has the header line but no claims under it.", line=2)
    known = {c.location for c in claims}
    seen: set[tuple[str, str]] = set()
    for line, setting in settings:
        if setting.location not in known:
            raise ImportFileError(f"Line {line}: the file sets {setting.field.replace('_', ' ')} for {setting.location}, but makes no claim "
                                  "about that system.", line=line, field="location")
        if (setting.location, setting.field) in seen:
            raise ImportFileError(f"Line {line}: this setting is given twice for {setting.location}.", line=line, field="claim")
        seen.add((setting.location, setting.field))
    return _sorted(claims), [setting for _, setting in settings]


def _csv_setting(line: int, location: str, type_: str, claim: str, value: str) -> ParsedSetting:
    def bad(message: str, fld: str) -> ImportFileError:
        return ImportFileError(f"Line {line}: {message}", line=line, field=fld)

    claim = claim.lower()
    if claim not in _CSV_SETTINGS:
        raise bad(f"setting {clean_text(claim, 40)!r} is not known. Use one of: {', '.join(sorted(_CSV_SETTINGS))}.", "claim")
    name, values, allowed = _CSV_SETTINGS[claim]
    key = re.sub(r"[\s_\-]+", "", value).lower()
    if key not in values:
        raise bad(f"{clean_text(value, 40)!r} is not a value for {claim}. Use {allowed}.", "value")
    if not location:
        raise bad("the location is empty.", "location")
    try:
        return ParsedSetting(parse_address(location).address, "server", name, values[key], f"line {line}")
    except AddressError:
        parsed = parse_software_location(location)
        if not parsed:
            raise bad("the location must be a server address (host:port) or a software name and version, for example: "
                      "acme-sign 1.4.2", "location") from None
        return ParsedSetting(f"{parsed[0]} {parsed[1]}".strip(), "software", name, values[key], f"line {line}")


def _csv_row(line: int, location: str, type_: str, claim: str, value: str) -> ParsedClaim:
    def bad(message: str, fld: str) -> ImportFileError:
        return ImportFileError(f"Line {line}: {message}", line=line, field=fld)

    type_, claim = type_.lower(), claim.lower()
    if type_ not in _CSV_CLAIMS:
        raise bad(f"type {clean_text(type_, 40)!r} is not known. Use tls, software or system.", "type")
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
        return _software_claim(ref, source, name, version, algorithm, kind=claim)

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
    elif claim == "post_quantum":
        status = POST_QUANTUM_VALUES.get(re.sub(r"[\s_\-]+", "", value).lower())
        if not status:
            raise bad(f"{clean_text(value, 40)!r} is not a post-quantum status. Use classical, hybrid or post-quantum only.", "value")
        detail["status"] = status
        claimed = status
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

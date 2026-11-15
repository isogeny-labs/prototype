"""What both file readers share: the error, the shapes they produce, and small helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.checks.addresses import HostPort
from app.config import MAX_UPLOAD_BYTES
from app.names import clean_text, join_and

KIND_ORDER = ["post_quantum", "protocol_versions", "cipher_suites", "key_exchange", "certificate", "signature_algorithm"]
NOT_STATED = "(not stated in the file)"
CSV_HEADER = ["location", "type", "claim", "value"]


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
class ParsedSetting:
    """A setting the file gives for a system (phase 4a): used by the migration plan. Not a claim: nothing checks it."""
    location: str       # the server address, or "name version" of a software component
    location_kind: str  # server | software
    field: str          # lifespan | exposure | can_change
    value: str          # short | long ; internet | internal ; yes | no
    source: str


@dataclass
class ParsedFile:
    format: str  # cyclonedx-cbom | csv
    claims: list[ParsedClaim]
    skipped: list[SkippedItem] = field(default_factory=list)
    settings: list[ParsedSetting] = field(default_factory=list)


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


def _server_text(kind: str, where: str, detail: dict, claimed: str) -> str:
    if kind == "protocol_versions":
        if detail.get("unsupported_protocol"):
            return f"{where} uses {claimed}"
        return f"{where} accepts {join_and(detail['versions'])} only"
    if kind == "cipher_suites":
        return f"{where} accepts only these cipher suites: {claimed}"
    if kind == "key_exchange":
        return f"{where} uses only these key-exchange groups: {claimed}"
    if kind == "post_quantum":
        return f"{where} key exchange is {claimed}"
    if kind == "certificate":
        if not detail.get("algorithm") and claimed == NOT_STATED:
            return f"{where} has a certificate (the file does not say which algorithm)"
        return f"{where} certificate is {claimed}"
    return f"{where} signs with {claimed}"


def _sorted(claims: list[ParsedClaim]) -> list[ParsedClaim]:
    return sorted(claims, key=lambda c: KIND_ORDER.index(c.kind))  # stable: file order kept inside a kind


def _split_values(value: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;|]", value) if p.strip()]


def parse_software_location(text: str) -> tuple[str, str] | None:
    """'acme-sign 1.4.2' or 'acme-sign@1.4.2' -> (name, version)."""
    m = re.fullmatch(r"\s*(\S(?:.*\S)?)(?:\s+|@)v?([0-9][^\s@]*)\s*", text)
    if not m:
        return None
    return clean_text(m.group(1), 100), clean_text(m.group(2), 50)


def _software_claim(ref: str, source: str, name: str, version: str, algorithm: str,
                    kind: str = "signature_algorithm") -> ParsedClaim:
    label = f"{name} {version}".strip()
    return ParsedClaim(
        ref=ref, location=label, location_kind="software", kind=kind, claimed_value=algorithm,
        text=f"signing component is {label} implementing {algorithm}" if kind == "signature_algorithm"
        else f"software component {label} uses {algorithm} for key exchange",
        source=source, detail={"component": name, "version": version, "algorithm": algorithm},
    )


def _places(places: list[HostPort]) -> list[tuple[str, str, dict]]:
    """Every address an asset is used at, or one 'unknown' place. A claim is never dropped for lack of a location."""
    if not places:
        return [(NOT_STATED, "unknown", {})]
    return [(hp.address, "server", {"host": hp.host, "port": hp.port}) for hp in places]


def _where_words(where: str, kind: str) -> str:
    return where if kind == "server" else "A system the file does not name"

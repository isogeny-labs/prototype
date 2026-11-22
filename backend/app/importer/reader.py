"""Pick the reader for an uploaded file (CycloneDX CBOM or our CSV) and run it."""
from __future__ import annotations

from app.config import MAX_UPLOAD_BYTES
from app.importer.cbom import read_cbom
from app.importer.common import CSV_HEADER, ImportFileError, ParsedFile, ParsedSetting
from app.importer.csv_file import parse_csv_rows


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
        settings: list[ParsedSetting] = []
        if fmt == "cyclonedx-cbom":
            claims, skipped = read_cbom(data)
        else:
            (claims, settings), skipped = parse_csv_rows(data), []
    except RecursionError as exc:  # defensive: the depth limits should stop this first
        raise ImportFileError("This file is nested too deeply to read.", field="components") from exc
    return ParsedFile(format=fmt, claims=claims, skipped=skipped, settings=settings)

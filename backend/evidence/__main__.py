"""cd backend && .venv/bin/python -m evidence verify file.json [--public-key HEX_OR_FILE] [--data-dir DIR]
                                                           [--previous OLDER.json] [--pack-key HEX_OR_FILE]

Since phase 5c a file may hold an Otto part (test packs, the assessment's Otto ledger, Claude's steps). It is checked
after the file's own signature held: see evidence/otto.py. --previous names an older download of the same assessment:
the older file's latest ledger entry must still be in this file's ledger. Exit codes stay 0 verified, 1 failed,
2 not confirmed (also when Otto's own audit could not be run here, or a pack's signer is not one you trust)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.canonical import loads_strict

from . import (
    FAILED,
    MAX_FILE_BYTES,
    SIGNER_NOT_CONFIRMED,
    VERIFIED,
    read_public_key,
    trusted_key_from_data_dir,
    verify_bytes,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # a wrong command line is a failure (exit 1), never mistaken for "not confirmed" (2)
        self.print_usage(sys.stderr)
        print(f"Evidence NOT verified: {message}", file=sys.stderr)
        raise SystemExit(FAILED)


def _evidence_of(raw: bytes) -> dict:
    """The evidence record inside a file whose own signature was already checked (so it has the shape of one)."""
    signed = loads_strict(raw)
    assert isinstance(signed, dict)
    return signed["evidence"]


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="python -m evidence", description="Check a downloaded Evidence Lab evidence file.")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="check an evidence .json file")
    verify.add_argument("file")
    verify.add_argument(
        "--public-key", help="the signer's public key you trust: 64 hex characters, or a file holding them"
    )
    verify.add_argument(
        "--data-dir", help="the app's data folder (its public key file is used); default: this app's own"
    )
    verify.add_argument(
        "--previous", help="an older download of the same assessment: its Otto ledger must still be inside this one"
    )
    verify.add_argument(
        "--pack-key",
        action="append",
        default=[],
        help="a test pack signing key you trust besides the app's own: 64 hex characters, or a file holding them",
    )
    args = parser.parse_args(argv)

    try:
        with open(args.file, "rb") as fh:
            raw = fh.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        print(f"Evidence NOT verified: the file could not be read ({exc.__class__.__name__}).")
        return FAILED

    where, data_dir = None, None
    if args.public_key is not None:
        trusted = read_public_key(args.public_key)
        if trusted is None:
            print("Evidence NOT verified: --public-key must be 64 hex characters, or a file holding them.")
            return FAILED
        where = "the key given with --public-key"
    else:
        if args.data_dir is not None:
            data_dir = Path(args.data_dir)
        else:
            from app.config import load_settings

            data_dir = load_settings().data_dir
        trusted = trusted_key_from_data_dir(data_dir)
        where = f"this app's own key in {data_dir}"

    outcome = verify_bytes(raw, trusted)
    # Phase 5c: the Otto part, checked only once the file's own signature held (so what is checked is what was signed).
    otto = None
    if outcome.code in (VERIFIED, SIGNER_NOT_CONFIRMED):
        evidence = _evidence_of(raw)
        previous = None
        if args.previous is not None:
            try:
                with open(args.previous, "rb") as fh:
                    older_raw = fh.read(MAX_FILE_BYTES + 1)
            except OSError as exc:
                print(f"Evidence NOT verified: the older file could not be read ({exc.__class__.__name__}).")
                return FAILED
            older = verify_bytes(older_raw, trusted)
            if older.code == FAILED or older.code != outcome.code:
                print(
                    "Evidence NOT verified: the older file given with --previous does not verify the same way as this one "
                    f"({older.message.removeprefix('Evidence NOT verified: ')})"
                )
                return FAILED
            if older.signer != outcome.signer:
                print(
                    "Evidence NOT verified: the older file given with --previous was not signed with the same key as this one, "
                    "so the two can't be downloads of the same assessment."
                )
                return FAILED
            previous = _evidence_of(older_raw)
        from .otto import check_otto, needs_otto_part, pack_keys

        if "otto" not in evidence and needs_otto_part(evidence):
            # A file from this app that holds an advisory check always has its Otto part: the packs, the lock entries
            # and the ledger that binds each run. Without it those runs are bound to nothing.
            print(
                "Evidence NOT verified: the file holds an advisory check but no Otto part (its test packs and its ledger)."
            )
            return FAILED
        if "otto" in evidence or previous is not None:
            if "otto" not in evidence:
                print("Evidence NOT verified: --previous compares Otto ledgers, and this file has no Otto part.")
                return FAILED
            extra = [key for key in (read_public_key(value) for value in args.pack_key) if key]
            if len(extra) != len(args.pack_key):
                print("Evidence NOT verified: --pack-key must be 64 hex characters, or a file holding them.")
                return FAILED
            otto = check_otto(evidence, pack_keys(data_dir, extra), previous)
    if otto is not None and otto.code == FAILED:
        print(f"Evidence NOT verified: the Otto part: {otto.problem}")
        return FAILED
    # Phase 6d: the Change watch part, checked against the runs in the file (also only once the signature held).
    watch = None
    if outcome.code in (VERIFIED, SIGNER_NOT_CONFIRMED):
        from .changewatch import check_change_watch, needs_change_watch_part

        if "change_watch" not in evidence and needs_change_watch_part(evidence):
            print(
                "Evidence NOT verified: the file lists a run made for a developer's change but has no Change watch part "
                "(the change, the watch run and its record)."
            )
            return FAILED
        if "change_watch" in evidence:
            watch = check_change_watch(evidence)
            if not watch.ok:
                print(f"Evidence NOT verified: the Change watch part: {watch.problem}")
                return FAILED
    # Sandbox research: the Watch list part, worked out again from the looks in the file (also only once the signature held).
    watch_list = None
    if outcome.code in (VERIFIED, SIGNER_NOT_CONFIRMED) and "watch_list" in evidence:
        from .watchlist import check_watch_list

        watch_list = check_watch_list(evidence)
        if not watch_list.ok:
            print(f"Evidence NOT verified: the Watch list part: {watch_list.problem}")
            return FAILED
    if outcome.ok and otto is not None and otto.code != VERIFIED:
        print("The file's own signature holds, but its Otto part could not be fully confirmed.")
    else:
        print(outcome.message)
    if outcome.fingerprint:
        print(f"  Fingerprint (SHA-256): {outcome.fingerprint}")
        print(f"  Signer key fingerprint: {outcome.signer}")
    if outcome.ok:
        print(f"  Signer confirmed against {where}.")
    elif outcome.code == SIGNER_NOT_CONFIRMED:
        print("  No trusted key was found to compare the signer with. Give one with --public-key, or point --data-dir")
        print("  at the data folder of the app that made the file. This is not a pass.")
    if watch is not None:
        for line in watch.lines:
            print(f"  Change watch: {line}")
    if watch_list is not None:
        for line in watch_list.lines:
            print(f"  Watch list: {line}")
    if otto is not None:
        for line in otto.lines:
            print(f"  Otto: {line}")
        if otto.code != VERIFIED:
            print(f"  Otto: {otto.problem} This is not a pass.")
            return SIGNER_NOT_CONFIRMED
    return outcome.code


if __name__ == "__main__":
    sys.exit(main())

"""cd backend && .venv/bin/python -m evidence verify file.json [--public-key HEX_OR_FILE] [--data-dir DIR]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import FAILED, MAX_FILE_BYTES, SIGNER_NOT_CONFIRMED, read_public_key, trusted_key_from_data_dir, verify_bytes


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # a wrong command line is a failure (exit 1), never mistaken for "not confirmed" (2)
        self.print_usage(sys.stderr)
        print(f"Evidence NOT verified: {message}", file=sys.stderr)
        raise SystemExit(FAILED)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="python -m evidence", description="Check a downloaded Evidence Lab evidence file.")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="check an evidence .json file")
    verify.add_argument("file")
    verify.add_argument("--public-key", help="the signer's public key you trust: 64 hex characters, or a file holding them")
    verify.add_argument("--data-dir", help="the app's data folder (its public key file is used); default: this app's own")
    args = parser.parse_args(argv)

    try:
        with open(args.file, "rb") as fh:
            raw = fh.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        print(f"Evidence NOT verified: the file could not be read ({exc.__class__.__name__}).")
        return FAILED

    where = None
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
    print(outcome.message)
    if outcome.fingerprint:
        print(f"  Fingerprint (SHA-256): {outcome.fingerprint}")
        print(f"  Signer key fingerprint: {outcome.signer}")
    if outcome.ok:
        print(f"  Signer confirmed against {where}.")
    elif outcome.code == SIGNER_NOT_CONFIRMED:
        print("  No trusted key was found to compare the signer with. Give one with --public-key, or point --data-dir")
        print("  at the data folder of the app that made the file. This is not a pass.")
    return outcome.code


if __name__ == "__main__":
    sys.exit(main())

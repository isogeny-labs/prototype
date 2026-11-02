#!/usr/bin/env bash
# Build a portable zip of the customer-side runner + verifier + fixtures.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/data/iel_runner_portable.zip}"
TMP=$(mktemp -d)
mkdir -p "$TMP/iel_tools"
cp "$ROOT"/iel_tools/*.py "$ROOT"/iel_tools/README.md "$ROOT"/iel_tools/Dockerfile "$TMP/iel_tools/"
mkdir -p "$TMP/iel_tools/fixtures" && cp "$ROOT"/backend/fixtures/*.py "$TMP/iel_tools/fixtures/"
(cd "$TMP" && zip -qr "$OUT" iel_tools)
rm -rf "$TMP"
echo "wrote $OUT"

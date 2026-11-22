#!/usr/bin/env bash
# Constant-time check of ctcrypto on the compiled release binary.
#   1. valgrind memcheck with secrets marked undefined (branches, addresses);
#   2. disassembly scan for hardware division inside ctcrypto code.
# Writes ctcheck-report.json; exits non-zero on any unexpected result.
set -euo pipefail
cd "$(dirname "$0")"
ITERS="${CTCHECK_ITERS:-6}"
FEATURES="${CTCHECK_FEATURES-aes,mlkem,mldsa}"
OUT="${CTCHECK_REPORT:-ctcheck-report.json}"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-target}"
cargo build --release --no-default-features --features "$FEATURES" >&2
BIN="$CARGO_TARGET_DIR/release/ctcheck"
fail=0
rows=()
for case in $("$BIN" list); do
  log="$(mktemp)"
  set +e
  valgrind -q --error-exitcode=97 --track-origins=no "$BIN" "$case" "$ITERS" >"$log" 2>&1
  rc=$?
  set -e
  grep -q "valgrind=true" "$log" || { echo "FAIL $case: not running under valgrind" >&2; fail=1; }
  errs=$(grep -c "depends on uninitialised value\|Use of uninitialised value" "$log" || true)
  if [[ "$case" == control-* ]]; then
    expect=flagged; [[ $rc -eq 97 ]] && got=flagged || got="rc=$rc"
  else
    expect=clean; [[ $rc -eq 0 ]] && got=clean || got=flagged
  fi
  status=ok; [[ "$expect" == "$got" ]] || { status=FAIL; fail=1; { grep -A12 "uninitialised" "$log" || true; } | head -60 >&2; }
  printf '%-16s expect=%-8s got=%-8s reports=%-3s %s\n' "$case" "$expect" "$got" "$errs" "$status" >&2
  rows+=("{\"case\":\"$case\",\"expect\":\"$expect\",\"got\":\"$got\",\"valgrind_reports\":$errs,\"status\":\"$status\"}")
  rm -f "$log"
done
# Hardware division is variable-time on most CPUs and invisible to memcheck.
divs=$(objdump -d --no-show-raw-insn "$BIN" | awk '
  /^[0-9a-f]+ <.*>:$/ { sym=$2 }
  /[ \t](div|idiv)[a-z]*[ \t]/ && sym ~ /ctcrypto|ctcheck/ { print sym }' | sort | uniq -c || true)
ndiv=$(printf '%s' "$divs" | grep -c . || true)
if [[ "$ndiv" -ne 0 ]]; then
  echo "division instructions inside ctcrypto (review each: must not touch secrets):" >&2
  printf '%s\n' "$divs" >&2
  [[ "${CTCHECK_ALLOW_DIV:-0}" == 1 ]] || fail=1
fi
{
  printf '{"schema":"ctcheck.report/v1","iterations":%s,"features":"%s",' "$ITERS" "$FEATURES"
  printf '"rustc":"%s","valgrind":"%s","target":"%s",' "$(rustc --version)" "$(valgrind --version)" "$(rustc -vV | sed -n 's/^host: //p')"
  printf '"binary_sha256":"%s","division_sites_in_ctcrypto":%s,' "$(sha256sum "$BIN" | cut -d' ' -f1)" "$ndiv"
  printf '"cases":[%s],"pass":%s}\n' "$(IFS=,; echo "${rows[*]}")" "$([[ $fail -eq 0 ]] && echo true || echo false)"
} > "$OUT"
echo "report: $OUT (pass=$([[ $fail -eq 0 ]] && echo true || echo false))" >&2
exit $fail

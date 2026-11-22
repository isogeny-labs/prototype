#!/usr/bin/env bash
# Starts the Isogeny Evidence Lab demo on this computer.
#   ./run-demo.sh
# Then open http://127.0.0.1:8000 in your browser. Press Ctrl+C here to stop.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
URL="http://127.0.0.1:8000"

say() { printf '\n== %s\n' "$1"; }
fail() { printf '\nCould not start: %s\n' "$1" >&2; exit 1; }

# 1. Python 3.12. The app keeps its own private Python environment in backend/.venv. When that is there and
#    works, no other Python is needed. Otherwise it is made (in step 3) with the first Python 3.12 on this
#    computer that can make one: it must be version 3.12 and have the two parts that make an environment with pip
#    in it ("venv" and "ensurepip"; Ubuntu and Debian keep them in a separate package, python3.12-venv). A
#    Python 3.12 without them is passed over, never picked: making an environment with it stops halfway.
python_candidates() {            # where to look, best first, one per line
  type -aP python3.12 2>/dev/null || true
  printf '%s\n' /usr/local/bin/python3.12 /usr/bin/python3.12
  type -aP python3 2>/dev/null || true
}
environment_works() {            # backend/.venv is whole: its Python starts and its pip answers
  [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -m pip --version >/dev/null 2>&1
}
PY=""                            # the Python picked to make the environment; empty while none is needed
LOOKED_AT=""                     # the candidates already looked at, so that none is looked at twice
SAW_312=0                        # 1 once any Python 3.12 was seen, usable or not
pick_python() {                  # puts the next usable Python 3.12 into PY; fails when there is none left
  local candidate
  while IFS= read -r candidate; do
    [ -n "$candidate" ] && [ -x "$candidate" ] || continue
    case "$candidate" in "$VENV"/*) continue ;; esac                    # never the environment's own Python
    case "$LOOKED_AT" in *$'\n'"$candidate"$'\n'*) continue ;; esac
    LOOKED_AT="$LOOKED_AT"$'\n'"$candidate"$'\n'
    "$candidate" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))' >/dev/null 2>&1 || continue
    SAW_312=1
    "$candidate" -c 'import venv, ensurepip' >/dev/null 2>&1 || continue
    PY="$candidate"
    return 0
  done < <(python_candidates)
  PY=""
  return 1
}
if ! environment_works && ! pick_python; then
  if [ "$SAW_312" = 0 ]; then
    fail "Python 3.12 is not installed. Install Python 3.12, then run ./run-demo.sh again."
  elif [ "${CODESPACES:-}" = "true" ]; then
    fail "This Codespace's Python 3.12 cannot make the app's private Python environment (its venv part is missing). Make a new Codespace, or rebuild this one (see README.md, \"In a Codespace\"), then run ./run-demo.sh again."
  else
    fail "Python 3.12 is installed, but it cannot make the app's private Python environment (its venv part is missing). Install that part (on Ubuntu or Debian: sudo apt install python3.12-venv), then run ./run-demo.sh again."
  fi
fi

# 2. Large files. Since phase 4c+ new test-set files are kept in Git LFS (large-file storage). A copy made
#    without Git LFS holds small pointer files in their place: fetch the real ones (demo/vectors only; the
#    screenshots are not needed to run the app). Nothing happens when every file is already there.
if grep -rlq "^version https://git-lfs.github.com/spec/v1" "$ROOT/demo/vectors" 2>/dev/null; then
  if git -C "$ROOT" lfs version >/dev/null 2>&1; then
    say "Fetching the test-set files from Git LFS (first run only)"
    git -C "$ROOT" lfs pull --include="demo/vectors/**" \
      || fail "The test-set files could not be fetched from Git LFS. Check the internet connection, then run ./run-demo.sh again."
    if grep -rlq "^version https://git-lfs.github.com/spec/v1" "$ROOT/demo/vectors" 2>/dev/null; then
      fail "Some test-set files in demo/vectors are still Git LFS pointers after fetching. Run: git lfs pull, then run ./run-demo.sh again."
    fi
  else
    fail "Some test-set files in demo/vectors are Git LFS pointers and Git LFS is not installed. Install Git LFS, run: git lfs pull, then run ./run-demo.sh again."
  fi
fi

# 3. Backend: private Python environment + packages, exact versions with their fingerprints from
#    requirements.lock (only when missing or the lock changed). An environment that is only half made (its
#    Python or its pip does not work, for example after a first try that stopped halfway) is thrown away and
#    made again. A try that fails leaves nothing behind, and the next usable Python 3.12 is tried.
make_environment() {             # backend/.venv made new with the Python given: whole on success, gone on failure
  rm -rf "$VENV"
  if PYTHON_SAID="$("$1" -m venv "$VENV" 2>&1)" && environment_works; then
    return 0
  fi
  rm -rf "$VENV"
  return 1
}
if [ -n "$PY" ]; then
  if [ -e "$VENV" ]; then
    say "Setting up Python again (what was there was only half made; about a minute)"
  else
    say "Setting up Python (first run only, about a minute)"
  fi
  until make_environment "$PY"; do
    if ! pick_python; then
      [ -z "$PYTHON_SAID" ] || printf '   Python said: %s\n' "${PYTHON_SAID##*$'\n'}" >&2
      fail "Python 3.12 could not make the app's private Python environment (backend/.venv). Check that the disk is not full and that this folder can be written to, then run ./run-demo.sh again."
    fi
  done
fi
if [ ! -f "$VENV/.requirements-installed" ] || [ "$BACKEND/requirements.lock" -nt "$VENV/.requirements-installed" ]; then
  say "Installing the backend packages"
  "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check --require-hashes -r "$BACKEND/requirements.lock"
  touch "$VENV/.requirements-installed"
fi

# 4. Frontend: build the screens when they are missing or older than their source
needs_build=0
if [ ! -f "$FRONTEND/dist/index.html" ]; then
  needs_build=1
elif [ -n "$(find "$FRONTEND/src" "$FRONTEND/index.html" "$FRONTEND/package.json" "$FRONTEND/vite.config.ts" \
              "$FRONTEND/tsconfig.json" -newer "$FRONTEND/dist/index.html" -print -quit)" ]; then
  needs_build=1
fi
if [ "$needs_build" = 1 ]; then
  command -v npm >/dev/null 2>&1 || fail "Node.js (npm) is not installed. Install Node.js 20 or newer, then run ./run-demo.sh again."
  say "Building the screens (first run, or after a change)"
  if [ ! -d "$FRONTEND/node_modules" ] || [ "$FRONTEND/package-lock.json" -nt "$FRONTEND/node_modules" ]; then
    (cd "$FRONTEND" && npm install --no-fund --no-audit --loglevel=error)
  fi
  (cd "$FRONTEND" && npm run build --silent)
fi

# 4b. Otto (phase 5c, optional). Fetch Adam's Otto harness at the one commit pinned in backend/otto.lock.json and check
#     its fingerprint. It needs read access to its repository once, and no Docker. It can never stop the start: without
#     it the app works as before and says that Otto is not installed.
(cd "$BACKEND" && "$VENV/bin/python" -m app.prepare --otto) \
  || echo "   Otto could not be fetched. The app will run without it and say so."

# 5. Isolated mode (optional). If Docker is running, prepare our test images once. This is the only place
#    anything is downloaded or built for containers; the app itself never does. It can never stop the start:
#    no Docker, no internet or a slow download just means the app runs in demo mode and says so.
if command -v docker >/dev/null 2>&1; then
  say "Checking isolated mode (Docker)"
  echo "   The first time, with internet, this can take several minutes (the real libraries are a few hundred MB). Without Docker or internet it is skipped."
  if command -v timeout >/dev/null 2>&1; then
    (cd "$BACKEND" && timeout 2400 "$VENV/bin/python" -m app.prepare) \
      || echo "   Isolated mode could not be prepared. The app will run in demo mode."
  else
    (cd "$BACKEND" && "$VENV/bin/python" -m app.prepare) \
      || echo "   Isolated mode could not be prepared. The app will run in demo mode."
  fi
else
  echo
  echo "== Docker is not installed, so the app will run in demo mode (our demo software runs as normal local programs)."
fi

# 6. Is something already using the app's port?
if ! "$VENV/bin/python" - <<'PYEOF'
import socket, sys
s = socket.socket()
try:
    s.bind(("127.0.0.1", 8000))
except OSError:
    sys.exit(1)
finally:
    s.close()
PYEOF
then
  fail "Port 8000 is already in use. The app may already be running: try opening $URL. Otherwise close the other program and run ./run-demo.sh again."
fi

# 7. Start. The app also starts its own demo TLS server on localhost:8443.
say "Isogeny Evidence Lab is starting"
echo "   Open this in your browser:  $URL"
echo "   The first time, it asks you to create a password."
echo "   To stop the app, press Ctrl+C in this window."
echo
cd "$BACKEND"
exec "$VENV/bin/python" -m app

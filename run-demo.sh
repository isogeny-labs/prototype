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

# 1. Python 3.12
if [ -x /usr/bin/python3.12 ]; then
  PY=/usr/bin/python3.12
elif command -v python3.12 >/dev/null 2>&1; then
  PY="$(command -v python3.12)"
elif command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))'; then
  PY="$(command -v python3)"
else
  fail "Python 3.12 is not installed. Install Python 3.12, then run ./run-demo.sh again."
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
#    requirements.lock (only when missing or the lock changed)
if [ ! -x "$VENV/bin/python" ]; then
  say "Setting up Python (first run only, about a minute)"
  "$PY" -m venv "$VENV"
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

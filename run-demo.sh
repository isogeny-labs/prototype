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
else
  fail "Python 3.12 is not installed. Install Python 3.12, then run ./run-demo.sh again."
fi

# 2. Backend: private Python environment + packages (only when missing or the list changed)
if [ ! -x "$VENV/bin/python" ]; then
  say "Setting up Python (first run only, about a minute)"
  "$PY" -m venv "$VENV"
fi
if [ ! -f "$VENV/.requirements-installed" ] || [ "$BACKEND/requirements.txt" -nt "$VENV/.requirements-installed" ]; then
  say "Installing the backend packages"
  "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -r "$BACKEND/requirements.txt"
  touch "$VENV/.requirements-installed"
fi

# 3. Frontend: build the screens when they are missing or older than their source
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

# 4. Is something already using the app's port?
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

# 5. Start. The app also starts its own demo TLS server on localhost:8443.
say "Isogeny Evidence Lab is starting"
echo "   Open this in your browser:  $URL"
echo "   The first time, it asks you to create a password."
echo "   To stop the app, press Ctrl+C in this window."
echo
cd "$BACKEND"
exec "$VENV/bin/python" -m app

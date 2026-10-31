#!/usr/bin/env bash
# Start/stop/restart the development server (uvicorn, port ${PORT:-8008}).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8008}"
PIDFILE="${IEL_PIDFILE:-$ROOT/data/dev_server.pid}"
LOG="${IEL_LOG:-$ROOT/data/dev_server.log}"
mkdir -p "$ROOT/data"
stop() { if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then kill "$(cat "$PIDFILE")"; sleep 1; fi; rm -f "$PIDFILE"; }
start() {
  cd "$ROOT/backend"
  nohup python3 -m uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "$PORT" > "$LOG" 2>&1 &
  echo $! > "$PIDFILE"
  for i in $(seq 1 80); do curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && { echo "server up on http://127.0.0.1:$PORT (pid $(cat "$PIDFILE"))"; return; }; sleep 0.5; done
  echo "server failed to start; see $LOG"; tail -20 "$LOG"; exit 1
}
case "${1:-start}" in start) start;; stop) stop;; restart) stop; start;; *) echo "usage: $0 start|stop|restart";; esac

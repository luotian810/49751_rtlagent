#!/usr/bin/env bash
# Adapted from RTL fc8e26a example/serve/run_api.sh for this stdlib HTTP server.
# The submission API is detached and restarted after exit; inference is separate.
# Start serve/start.sh first, then this script, then rc-tunnel expose.
# Deliberately no set -u: AMD settings may contain unset environment variables.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/defaults.sh"
PORT="${API_PORT:-7860}"
STATE="${AGENT_TMP:-/var/tmp}/run_api"
PIDFILE="$STATE/run_api.pid"
LOG="$STATE/serve_api.log"
mkdir -p "$STATE" || exit 1

running() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }

case "${1:-}" in
start)
    if running; then
        echo "run_api.sh: already running (pid $(cat "$PIDFILE")), log $LOG"
        exit 0
    fi
    [ -n "$FPGACHINA_TOKEN" ] || { echo "run_api.sh: FPGACHINA_TOKEN is not set" >&2; exit 1; }
    command -v setsid >/dev/null 2>&1 || { echo "run_api.sh: setsid is required" >&2; exit 1; }
    setsid bash "$0" _loop </dev/null >>"$LOG" 2>&1 &
    sleep 1
    running || { echo "run_api.sh: supervisor failed to start; see $LOG" >&2; exit 1; }
    echo "run_api.sh: started (pid $(cat "$PIDFILE" 2>/dev/null)), log $LOG"
    ;;
_loop)
    echo $$ > "$PIDFILE"
    trap 'kill "$child" 2>/dev/null; wait "$child" 2>/dev/null; rm -f "$PIDFILE"; exit 0' TERM INT
    cd "$HERE/.." || exit 1
    while :; do
        echo "$(date '+%F %T') run_api.sh: starting serve_api on 127.0.0.1:$PORT"
        "${PYTHON_EXE:-python3}" -m serve.serve_api --port "$PORT" &
        child=$!
        wait "$child"
        rc=$?
        echo "$(date '+%F %T') run_api.sh: serve_api exited (rc=$rc), restarting in 2 s"
        sleep 2
    done
    ;;
stop)
    if running; then
        kill "$(cat "$PIDFILE")"
        for _ in 1 2 3 4 5 6 7 8 9 10; do running || break; sleep 1; done
        echo "run_api.sh: stopped"
    else
        echo "run_api.sh: not running"
    fi
    ;;
status)
    if running; then echo "run_api.sh: running (pid $(cat "$PIDFILE")), log $LOG"
    else echo "run_api.sh: not running"; exit 1; fi
    ;;
*)
    echo "usage: bash $0 start|stop|status" >&2
    exit 2
    ;;
esac

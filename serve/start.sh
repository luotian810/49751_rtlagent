#!/usr/bin/env bash
# Start resident inference once and return only when the selected model is ready.
# HTTP submission starts serve_api separately; container fallback needs no HTTP API.
set -eo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/defaults.sh"
PYTHON_COMMAND="${PYTHON_EXE:-python3}"
if [[ -z "$MODEL_NAME" || "$MODEL_NAME" != "$LLM_MODEL" ]]; then
    printf 'Set MODEL_NAME and LLM_MODEL to the same local served model name.\n' >&2
    exit 2
fi
export LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:$PORT/v1}"
case "$LLM_BASE_URL" in
    "http://127.0.0.1:$PORT/v1"|"http://localhost:$PORT/v1") ;;
    *) printf 'start.sh requires the local inference URL matching PORT.\n' >&2; exit 2 ;;
esac
LOG_DIR="${SERVE_LOG_DIR:-$AGENT_TMP/serve-logs}"
case "$INFERENCE_BACKEND" in
    vllm|llamacpp) INFERENCE_SCRIPT="$HERE/$INFERENCE_BACKEND.sh" ;;
    *) printf 'INFERENCE_BACKEND must be vllm or llamacpp.\n' >&2; exit 2 ;;
esac
INFERENCE_LOG="$LOG_DIR/$INFERENCE_BACKEND.log"
START_TIMEOUT_S="${START_TIMEOUT_S:-900}"
if ! [[ "$START_TIMEOUT_S" =~ ^[0-9]+$ ]]; then
    printf 'START_TIMEOUT_S must be a nonnegative integer.\n' >&2
    exit 2
fi
mkdir -p "$AGENT_TMP" "$EDA_TMP" "$LOG_DIR"

model_ready() {
    "$PYTHON_COMMAND" - "$LLM_BASE_URL/models" "$MODEL_NAME" <<'PY'
import json
import sys
import urllib.request
try:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(sys.argv[1], timeout=3) as response:
        models = json.load(response).get("data", [])
    ready = any(isinstance(item, dict) and item.get("id") == sys.argv[2] for item in models)
except (OSError, ValueError, TypeError, AttributeError):
    ready = False
raise SystemExit(0 if ready else 1)
PY
}

if model_ready; then
    printf 'start.sh: model %s is already ready.\n' "$MODEL_NAME" >&2
    exit 0
fi
command -v setsid >/dev/null || { printf 'start.sh requires setsid (Linux util-linux).\n' >&2; exit 2; }

# Detach only resident inference. Per-task scripts must remain in their job group.
setsid bash "$INFERENCE_SCRIPT" >"$INFERENCE_LOG" 2>&1 </dev/null &
SERVICE_PID=$!
# A failed attempt owns this session only; never kill an already-running model.
cleanup_failed_start() {
    local status=$?
    if (( status != 0 )); then
        kill -TERM -- "-$SERVICE_PID" 2>/dev/null || true
        sleep 1
        kill -KILL -- "-$SERVICE_PID" 2>/dev/null || true
        wait "$SERVICE_PID" 2>/dev/null || true
    fi
}
trap cleanup_failed_start EXIT
SECONDS=0
while ! model_ready; do
    if ! kill -0 "$SERVICE_PID" 2>/dev/null; then
        wait "$SERVICE_PID" || true
        printf 'start.sh: inference exited; inspect %s.\n' "$INFERENCE_LOG" >&2
        exit 1
    fi
    if (( SECONDS >= START_TIMEOUT_S )); then
        printf 'start.sh: model not ready after %ss; inspect %s.\n' "$START_TIMEOUT_S" "$INFERENCE_LOG" >&2
        exit 1
    fi
    sleep 1
done
printf 'start.sh: model %s is ready.\n' "$MODEL_NAME" >&2

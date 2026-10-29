#!/usr/bin/env bash
# Competition directory contract. Use Python env vars for the selected model.
set -eo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_ARG="${1:?usage: run.sh <task_dir> <out_dir>}"
OUT_ARG="${2:?usage: run.sh <task_dir> <out_dir>}"

TASK_DIR="$(cd "$TASK_ARG" && pwd)"
mkdir -p "$OUT_ARG"
OUT_DIR="$(cd "$OUT_ARG" && pwd)"
PYTHON_COMMAND="${PYTHON_EXE:-python3}"

# Defaults for the competition container; explicitly supplied settings win.
export XILINXD_LICENSE_FILE="${XILINXD_LICENSE_FILE:-2100@vivado-lic.fpgachina.svc.cluster.local}"
export FLEXLM_TIMEOUT="${FLEXLM_TIMEOUT:-300000000}"
export AGENT_TMP="${AGENT_TMP:-/var/tmp}"
export EDA_TMP="${EDA_TMP:-/var/tmp/eda}"
export LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:${PORT:-8000}/v1}"
export LLM_API_KEY="${LLM_API_KEY:-dummy}"
if [[ -z "${MODEL_NAME:-}" && -n "${MODEL:-}" ]]; then
    export MODEL_NAME="$(basename "$MODEL")"
fi
export LLM_MODEL="${LLM_MODEL:-${MODEL_NAME:-}}"
export MODEL_NAME="${MODEL_NAME:-$LLM_MODEL}"
if [[ -z "$MODEL_NAME" || "$MODEL_NAME" != "$LLM_MODEL" ]]; then
    printf 'Set MODEL_NAME and LLM_MODEL to the same served model name.\n' >&2
    exit 2
fi
mkdir -p "$AGENT_TMP" "$EDA_TMP"

cd "$ROOT_DIR"
status=0
"$PYTHON_COMMAND" -m agent.main \
    --input "$TASK_DIR" \
    --output "$OUT_DIR" \
    --backend "${RTL_SIMULATOR:-vivado}" \
    --max-rounds "${AGENT_MAX_ROUNDS:-3}" \
    --deadline "${AGENT_DEADLINE_S:-900}" || status=$?

# The output contract requires both files even when solving fails.
[[ -f "$OUT_DIR/solution.v" ]] || : > "$OUT_DIR/solution.v"
[[ -f "$OUT_DIR/trace.jsonl" ]] || : > "$OUT_DIR/trace.jsonl"
if [[ "$status" -ne 0 ]]; then
    printf 'run.sh: agent exited with status %s; inspect trace and output.\n' "$status" >&2
fi
exit 0

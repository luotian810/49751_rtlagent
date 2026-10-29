#!/usr/bin/env bash
# Local, single-GPU inference template. Validate against the official ROCm image.
set -eo pipefail

if [[ -z "${MODEL:-}" || ! -d "$MODEL" ]]; then
    printf 'Set MODEL to an existing local open-weight model directory.\n' >&2
    exit 2
fi

MODEL_NAME="${MODEL_NAME:-${LLM_MODEL:-$(basename "$MODEL")}}"
PORT="${PORT:-8000}"
MAX_LEN="${MAX_LEN:-32768}"
VRAM_BUDGET_GB="${VRAM_BUDGET_GB:-30}"
PYTHON_COMMAND="${PYTHON_EXE:-python3}"

export HIP_VISIBLE_DEVICES="${HIP_VISIBLE_DEVICES:-0}"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1

# A 48 GB validation card must still stay within the competition's 32 GB cap.
# Derive the allocation fraction from actual capacity; never assume 0.90 fits.
if [[ -z "${GPU_UTIL:-}" ]]; then
    GPU_UTIL="$("$PYTHON_COMMAND" - "$VRAM_BUDGET_GB" <<'PY'
import math
import sys
import torch
budget = float(sys.argv[1])
if not math.isfinite(budget) or not 0 < budget <= 32:
    raise SystemExit("VRAM_BUDGET_GB must be greater than 0 and at most 32")
total = torch.cuda.get_device_properties(0).total_memory / 2**30
print(f"{min(0.95, budget / total):.6f}")
PY
)" || { printf 'Cannot read VRAM size; check the inference runtime or set GPU_UTIL explicitly.\n' >&2; exit 1; }
fi

exec "$PYTHON_COMMAND" -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --served-model-name "$MODEL_NAME" \
    --host 127.0.0.1 \
    --port "$PORT" \
    --tensor-parallel-size 1 \
    --max-model-len "$MAX_LEN" \
    --gpu-memory-utilization "$GPU_UTIL" \
    --no-enable-log-requests

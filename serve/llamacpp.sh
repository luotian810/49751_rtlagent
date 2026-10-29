#!/usr/bin/env bash
# Optional local GGUF backend; configuration is an initial value, not a VRAM measurement.
set -eo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_COMMAND="${PYTHON_EXE:-python3}"
LLAMA_SERVER="${LLAMA_SERVER:-/opt/llamacpp/llama-server}"

if [[ -z "${MODEL:-}" || ! -f "$MODEL" ]]; then
    printf 'Set MODEL to an existing local GGUF model file.\n' >&2
    exit 2
fi
if [[ ! -x "$LLAMA_SERVER" ]]; then
    printf 'Set LLAMA_SERVER to an executable llama-server path.\n' >&2
    exit 2
fi

MODEL_NAME="${MODEL_NAME:-${LLM_MODEL:-$(basename "$MODEL")}}"
PORT="${PORT:-8000}"
MAX_LEN="${MAX_LEN:-32768}"
if ! [[ "$MAX_LEN" =~ ^[0-9]+$ ]] || (( MAX_LEN <= 16384 )); then
    printf 'MAX_LEN must exceed the baseline output budget of 16384 tokens.\n' >&2
    exit 2
fi

export HIP_VISIBLE_DEVICES="${HIP_VISIBLE_DEVICES:-0}"
if ! [[ "$HIP_VISIBLE_DEVICES" =~ ^[0-9]+$ ]]; then
    printf 'HIP_VISIBLE_DEVICES must select one GPU index.\n' >&2
    exit 2
fi
# Official FPGA-CHINA image FAQ: required for the bundled rocBLAS kernels.
export ROCBLAS_TENSILE_LIBPATH="${ROCBLAS_TENSILE_LIBPATH:-/opt/llamacpp/rocblas/library}"

# Read the same manifest as the agent and unchanged official baseline. Pass JSON
# as one quoted argument; shell evaluation of manifest text is never needed.
CHAT_TEMPLATE_KWARGS="$("$PYTHON_COMMAND" - "$HERE/../manifest.json" <<'PY'
import json
import sys
from pathlib import Path

try:
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    generation = manifest.get("generation") or {}
    if not isinstance(generation, dict):
        raise ValueError("generation must be an object")
    kwargs = generation.get("chat_template_kwargs") or {}
    if not isinstance(kwargs, dict):
        raise ValueError("chat_template_kwargs must be an object")
    kwargs = {key: value for key, value in kwargs.items()
              if isinstance(key, str) and isinstance(value, (bool, int, float, str))}
    kwargs.setdefault("enable_thinking", False)
    print(json.dumps(kwargs, ensure_ascii=True, allow_nan=False))
except (OSError, ValueError, AttributeError, TypeError) as exc:
    raise SystemExit(f"Cannot read manifest generation settings: {exc}")
PY
)"

exec "$LLAMA_SERVER" \
    -m "$MODEL" \
    --host 127.0.0.1 \
    --port "$PORT" \
    --alias "$MODEL_NAME" \
    -ngl 999 \
    --ctx-size "$MAX_LEN" \
    --parallel 1 \
    --jinja \
    --chat-template-kwargs "$CHAT_TEMPLATE_KWARGS" \
    --no-context-shift

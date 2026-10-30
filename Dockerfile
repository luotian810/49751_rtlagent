# Official platform image, pinned by the current RTL reference repository.
# Private registry: fallback rebuilding is performed by the organisers.
ARG BASE_IMAGE=fpgachina-rtlhls@sha256:a7cf627e11708e8a6dcd9de689ff934f7b450b79369ebc7bb0217e8b54d81e56
FROM ${BASE_IMAGE}

WORKDIR /opt/agent

# Core Python code and the preserved official baseline use the standard library.
COPY requirements.txt ./
COPY agent/ ./agent/
COPY skill/ ./skill/
COPY scripts/ ./scripts/
COPY demos/ ./demos/
COPY serve/ ./serve/
COPY model/ ./model/
COPY docs/ ./docs/
COPY vendor/ ./vendor/
COPY LICENSES/ ./LICENSES/
COPY THIRD_PARTY_NOTICES.md ./
COPY run.sh run_baseline.sh baseline.py manifest.json REPORT.md README.md ./

RUN chmod +x run.sh run_baseline.sh serve/vllm.sh serve/llamacpp.sh serve/start.sh serve/run_api.sh

# Prepare the verified GGUF at this path before running offline. These defaults
# also reach the unchanged official baseline in a fresh container process.
ENV INFERENCE_BACKEND=llamacpp \
    MODEL=/workspace/models/Qwen3-14B-Q4_K_M.gguf \
    MODEL_NAME=Qwen3-14B-Q4_K_M \
    LLM_MODEL=Qwen3-14B-Q4_K_M \
    LLAMA_SERVER=/opt/llamacpp/llama-server \
    LLM_BASE_URL=http://127.0.0.1:8000/v1 \
    LLM_API_KEY=local-placeholder \
    MAX_LEN=32768 \
    LLM_MAX_TOKENS=16384 \
    LLM_TEMPERATURE=0.2 \
    HIP_VISIBLE_DEVICES=0 \
    ROCBLAS_TENSILE_LIBPATH=/opt/llamacpp/rocblas/library \
    OMP_NUM_THREADS=16 \
    RTL_SIMULATOR=vivado \
    NO_PROXY=127.0.0.1,localhost \
    no_proxy=127.0.0.1,localhost \
    AGENT_TMP=/var/tmp \
    EDA_TMP=/var/tmp/eda \
    SELFTEST_TMP=/var/tmp \
    XILINXD_LICENSE_FILE=2100@vivado-lic.fpgachina.svc.cluster.local \
    FLEXLM_TIMEOUT=300000000 \
    RTL_PART=xczu3eg-sbva484-1-e

EXPOSE 7860 8000

CMD ["/bin/bash"]

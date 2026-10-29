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
COPY run.sh run_baseline.sh baseline.py manifest.json REPORT.md README.md ./

RUN chmod +x run.sh run_baseline.sh serve/vllm.sh serve/llamacpp.sh serve/start.sh serve/run_api.sh

# Local weights and the compatible inference runtime must be prepared separately.
# No weights are downloaded at container startup. Set MODEL to the prepared local
# directory (vLLM) or GGUF file (llama.cpp), and use the same MODEL_NAME /
# LLM_MODEL for both agent and baseline.
ENV LLM_BASE_URL=http://127.0.0.1:8000/v1 \
    LLM_API_KEY=dummy \
    AGENT_TMP=/var/tmp \
    EDA_TMP=/var/tmp/eda \
    XILINXD_LICENSE_FILE=2100@vivado-lic.fpgachina.svc.cluster.local \
    FLEXLM_TIMEOUT=300000000 \
    RTL_PART=xczu3eg-sbva484-1-e

EXPOSE 7860 8000

CMD ["/bin/bash"]

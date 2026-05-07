FROM node:22-bookworm@sha256:9059d9d7db987b86299e052ff6630cd95e5a770336967c21110e53289a877433

ARG CODEX_NPM_VERSION=0.128.0
ARG PI_NPM_VERSION=0.73.0
ARG PI_WEB_ACCESS_NPM_VERSION=0.10.7

ENV DEBIAN_FRONTEND=noninteractive
LABEL org.eda-bench.kicad_source="Debian bookworm apt kicad package captured in run provenance"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        jq \
        kicad \
        ngspice \
        python3 \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g \
        @openai/codex@${CODEX_NPM_VERSION} \
        @mariozechner/pi-coding-agent@${PI_NPM_VERSION} \
        pi-web-access@${PI_WEB_ACCESS_NPM_VERSION} \
    && node --version > /image-tool-versions.txt \
    && npm --version >> /image-tool-versions.txt \
    && codex --version >> /image-tool-versions.txt \
    && pi --version >> /image-tool-versions.txt \
    && (kicad-cli --version || echo "kicad-cli unavailable") >> /image-tool-versions.txt \
    && ngspice --version | head -1 >> /image-tool-versions.txt

WORKDIR /workspace

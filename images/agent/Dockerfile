FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        jq \
        kicad \
        ngspice \
        procps \
        python3 \
        python3-venv \
        ripgrep \
        sudo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

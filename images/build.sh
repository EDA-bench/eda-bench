#!/bin/bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
docker build -t ghcr.io/eda-bench/eda-bench-agent:harbor-v1 "$repo/images/agent"
docker build -t ghcr.io/eda-bench/eda-bench-verifier:harbor-v1 -f "$repo/images/verifier.Dockerfile" "$repo"

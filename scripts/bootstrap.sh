#!/usr/bin/env bash
set -euo pipefail

python3.13 -m pip install --user uv==0.11.33
python3.13 -m uv sync --locked --extra dev
echo "Environment ready. Run ./scripts/verify.sh"

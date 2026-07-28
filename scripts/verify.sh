#!/usr/bin/env bash
set -euo pipefail

.venv/bin/python -m compileall -q src tests migrations
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m pytest -q
.venv/bin/python -m quantagent.health


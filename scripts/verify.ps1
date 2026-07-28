$ErrorActionPreference = "Stop"

$python = ".\.venv\Scripts\python.exe"
& $python -m compileall -q src tests migrations
& $python -m ruff check .
& $python -m ruff format --check .
& $python -m pytest -q
& $python -m quantagent.health

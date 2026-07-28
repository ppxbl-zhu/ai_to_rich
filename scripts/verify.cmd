@echo off
setlocal
.\.venv\Scripts\python.exe -m compileall -q src tests migrations || exit /b 1
.\.venv\Scripts\python.exe -m ruff check . || exit /b 1
.\.venv\Scripts\python.exe -m ruff format --check . || exit /b 1
.\.venv\Scripts\python.exe -m pytest -q || exit /b 1
.\.venv\Scripts\python.exe -m quantagent.health || exit /b 1

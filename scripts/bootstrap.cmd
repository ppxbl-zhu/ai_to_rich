@echo off
setlocal
py -3.13 -m pip install --user uv==0.11.33 || exit /b 1
py -3.13 -m uv sync --locked --extra dev || exit /b 1
echo Environment ready. Run scripts\verify.cmd

# QuantAgent

QuantAgent is an A-share research and paper-trading system. It starts with a
100,000 CNY simulated portfolio and will support swing-trend and closing-auction
research strategies. Live order submission is intentionally out of scope.

The product baseline is documented in
[`docs/PRODUCT_REQUIREMENTS.md`](docs/PRODUCT_REQUIREMENTS.md), and milestone
status is maintained in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Requirements

- Python 3.13
- Windows PowerShell or WSL/Linux
- Docker only when a local PostgreSQL service is needed

## Bootstrap

Windows:

```bat
scripts\bootstrap.cmd
scripts\verify.cmd
```

The `.cmd` entry points work when the Windows PowerShell execution policy blocks
local scripts. Equivalent `.ps1` scripts are also provided for environments
that permit them.

WSL/Linux:

```bash
chmod +x scripts/*.sh
./scripts/bootstrap.sh
./scripts/verify.sh
```

The verification command compiles the source, runs Ruff, executes all offline
tests, and prints a JSON health report. Bootstrap installs the pinned
`uv==0.11.33` resolver and synchronizes the committed `uv.lock`. Verification
requires no API token and no network.

## Configuration

Copy `.env.example` to `.env` only when local credentials are required.
Milestone 0 works without `.env`. The application rejects execution modes other
than `paper`.

For PostgreSQL development:

```powershell
docker compose up -d postgres
$env:QUANTAGENT_DATABASE_URL = "postgresql+psycopg://quantagent:local-development-only@localhost:5432/quantagent"
.\.venv\Scripts\alembic.exe upgrade head
```

Do not store a real database password or Tushare token in Git.

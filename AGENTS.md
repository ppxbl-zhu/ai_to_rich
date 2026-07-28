# QuantAgent contributor guide

Read `docs/ROADMAP.md` before starting substantial work. Work on the earliest
unfinished milestone unless the user explicitly changes priority.

## Safety

- The system is simulation-only until the release gate in the roadmap is met.
- Never add a broker/live-order adapter without explicit user authorization.
- Never commit `.env`, API keys, logs, market-data databases, or account data.
- Treat prices, symbols, trading dates, and corporate status as untrusted input.
- Preserve A-share T+1, lot-size, price-limit, suspension, ST and delisting rules.

## Efficient workflow

- Start with the narrowest relevant files and tests; avoid rereading the repository.
- Reuse fixtures and commands documented in `docs/ROADMAP.md`.
- For bugs, reproduce with a failing test before changing production code.
- Run targeted tests during implementation and the full quality gate before commit.
- Keep durable decisions in the roadmap or an ADR so later sessions need less context.

## Quality gate

```bash
python -m compileall -q .
ruff check .
pytest -q
```


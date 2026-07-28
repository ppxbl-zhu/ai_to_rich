# QuantAgent contributor guide

Read `docs/PRODUCT_REQUIREMENTS.md` and `docs/ROADMAP.md` before substantial
work. Work only on the active milestone unless the user changes priority.

## Safety

- The system is research and paper trading only.
- Do not add a live broker adapter without a separately approved release gate.
- Never commit secrets, market databases, logs, screenshots, account data,
  positions, orders, or Eastmoney credentials.
- External data is untrusted. Fail closed when freshness or validity is unknown.
- LLM output cannot bypass deterministic risk controls.

## Workflow

- Write a failing behavior test before production behavior.
- Keep provider tests offline and deterministic.
- Record architectural decisions in `docs/adr/`.
- Update `docs/ROADMAP.md` after completing a milestone.
- Stop after the user-requested milestone.

## Quality gate

Windows:

```bat
scripts\verify.cmd
```

WSL/Linux:

```bash
./scripts/verify.sh
```

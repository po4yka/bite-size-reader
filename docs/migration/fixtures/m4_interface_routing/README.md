# M4 Interface Routing Fixtures

This fixture corpus validates parity for M4 interface routing decisions:

- Mobile API route classification (`mobile_route`)
- Telegram command routing classification (`telegram_command`)

## Regenerate expected baselines

```bash
PYTHONPATH=. .venv/bin/python scripts/migration/generate_m4_interface_fixtures.py
```

## Verify fixtures are up to date

```bash
PYTHONPATH=. .venv/bin/python scripts/migration/generate_m4_interface_fixtures.py --check
```

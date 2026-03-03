# M2 Summary Contract Fixtures

Fixture corpus used to verify Python ↔ Rust summary contract parity for milestone M2.

- `input/*.json`: canonical fixture payloads
- `expected/*.json`: generated Python baselines (shape + deterministic subset)

Regenerate/update baselines:

```bash
PYTHONPATH=. .venv/bin/python scripts/migration/generate_m2_contract_fixtures.py
```

Validate baselines are fresh:

```bash
PYTHONPATH=. .venv/bin/python scripts/migration/generate_m2_contract_fixtures.py --check
```

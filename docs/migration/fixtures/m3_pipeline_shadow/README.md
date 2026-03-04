# M3 Pipeline Shadow Fixtures

This fixture corpus validates parity for the M3 shadow slices:

- `extraction_adapter`
- `chunking_preprocess`
- `content_cleaner`
- `llm_wrapper_plan`

## Regenerate expected baselines

```bash
PYTHONPATH=. .venv/bin/python scripts/migration/generate_m3_shadow_fixtures.py
```

## Verify fixtures are up to date

```bash
PYTHONPATH=. .venv/bin/python scripts/migration/generate_m3_shadow_fixtures.py --check
```

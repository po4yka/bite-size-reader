# Processing Orchestrator Fixtures

This fixture corpus validates end-to-end parity for the processing orchestrator
planning slice:

- `url_plan`
- `forward_plan`

The expected baselines are generated from the Python orchestration builders and
consumed by both the Rust crate tests and the Python real-binary bridge tests.

## Regenerate expected baselines

```bash
PYTHONPATH=. .venv/bin/python scripts/migration/generate_processing_orchestrator_fixtures.py
```

## Verify fixtures are up to date

```bash
PYTHONPATH=. .venv/bin/python scripts/migration/generate_processing_orchestrator_fixtures.py --check
```

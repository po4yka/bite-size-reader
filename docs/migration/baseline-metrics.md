# Python Baseline Metrics (M0)

Use this guide to capture and interpret baseline runtime metrics before comparing Rust implementations.

## Commands

```bash
# Run parity suite only
bash scripts/migration/run_parity_suite.sh

# Capture baseline snapshot + append history
python scripts/migration/capture_python_baseline.py
```

## Artifacts

- Latest snapshot: `docs/migration/baseline_metrics.json`
- Append-only history: `docs/migration/baseline_metrics_history.jsonl`

## Snapshot fields

- `captured_at_utc`: UTC timestamp of the run
- `git_commit`: commit SHA associated with captured run
- `exit_code`: parity suite exit status (`0` means passing)
- `wall_time_seconds`: total elapsed runtime
- `cpu_user_seconds` / `cpu_system_seconds`: CPU usage
- `max_rss_kb`: peak resident memory usage
- `environment.*`: Python and machine context for comparability

## Notes

- Run on stable hardware profile for trend comparisons.
- Compare medians over multiple runs instead of a single sample.

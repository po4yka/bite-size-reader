# Rust Pre-Migration Hardening Checklist

This checklist operationalizes the recommendations from `docs/audits/rust-migration-audit.md` into repeatable gates that can be run before each migration slice.

## Phase 1: Lock behavior on critical user flows

- [ ] `/summarize <url>` happy path characterization test stays green.
- [ ] YouTube transcript fallback characterization test stays green.
- [ ] `/search` unread/read/unread transition characterization test stays green.
- [ ] gRPC `SubmitUrl` stream ordering + terminal state characterization test stays green.
- [ ] API auth and sync response shape characterization tests stay green.

Command:

```bash
uv run pytest tests/characterization/test_immediate_backlog.py tests/characterization/test_auth_sync_characterization.py -v
```

## Phase 2: Code-quality debt burn down (desloppify)

- [ ] Run a fresh scan and capture baseline score.
- [ ] Resolve security findings or document explicit justifications.
- [ ] Reduce broad/silent exception findings in production paths.
- [ ] Remove or justify orphaned modules.

Commands:

```bash
desloppify scan --path .
desloppify status
desloppify next --cluster auto/smells-broad_except --count 10
desloppify next --cluster auto/smells-silent_except --count 10
desloppify next --cluster auto/orphaned --count 10
```

## Phase 3: Migration readiness gates

- [ ] Strict score above 60.
- [ ] Security findings closed or explicitly justified.
- [ ] Broad/silent exceptions reduced to intentional boundary handlers.
- [ ] Characterization suite for top flows is green.

## Suggested execution cadence

1. Run characterization tests on every PR touching core request processing.
2. Run full desloppify scan at least once daily during hardening sprint.
3. Log score movement and blockers in PR descriptions.
4. Only start a Rust slice when all migration readiness gates are met.


## Current hardening status (last verified)

- Characterization suite: ✅ `6 passed` on the two pre-migration characterization modules.
- `desloppify` security cluster: ✅ clean in latest scan.
- Broad/silent exception clusters: ⚠ still open (reduced but not yet at intentional-boundary-only target).
- Orphaned module cluster: ✅ no open orphaned findings reported in focused queue checks.
- Strict score > 60 gate: ❌ not yet met (strict score remains in the 30s while subjective review is unscored in this environment).

### Operational caveats

- This repository uses `uv` for reproducible test execution; prefer `uv run ...` commands in PR validation notes.
- If `desloppify` is unavailable in CI/containers, install with:

```bash
python -m pip install --upgrade git+https://github.com/peteromallet/desloppify.git
```

- Subjective score import may fail in environments without a `codex` runner binary on `PATH`; record that blocker explicitly in PR notes when it occurs.

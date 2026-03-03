# Project Audit & Rust Migration Assessment

## Current architecture snapshot

- **Primary product**: Async Telegram bot that summarizes web pages and YouTube videos into strict JSON, with SQLite persistence.
- **Feature surface** includes Telegram handling, URL extraction/summarization, channel digests, optional Redis caching, optional Chroma vector search, MCP server exposure, and a FastAPI mobile API.
- **Scale indicator**: 625 Python files (178 test files).

## Code health observations (desloppify)

Latest local scan highlights:

- Strict score: **33.5/100**.
- Open findings: **1424** (T2: 118, T3: 928, T4: 378).
- Detector highlights include orphaned modules, broad/silent exception patterns, and test coverage debt.

## Rust migration feasibility

### Why migration is plausible

- The system already has **clean external boundaries**:
  - gRPC contract (`processing.proto`) for request submission + progress streaming.
  - HTTP-based integrations (OpenRouter, Firecrawl, Karakeep).
  - SQLite + Redis + optional Chroma as infrastructure dependencies available in Rust ecosystems.
- Several domains are CPU/latency sensitive (content parsing, queueing, heavy async orchestration), where Rust could improve memory safety and predictability.

### Why full rewrite is high risk now

- Broad functional scope (bot + API + MCP + optional integrations) creates a large parity matrix.
- Current quality debt suggests behavior is still being stabilized; translating unstable behavior can freeze accidental complexity into a new language.
- Python-specific ecosystem usage (spaCy pipeline + many optional packages) means non-trivial replacement/FFI decisions.

## How to reduce critical debt before migration

Treat debt burn-down as a **pre-migration hardening sprint** with explicit gates.

### 1) Triage by risk, not by count

Prioritize findings that most affect production safety and migration ambiguity:

1. Security findings first
2. Broad/silent exception patterns in production paths
3. Orphaned/unused modules that blur ownership
4. High-complexity modules on critical user flows
5. Coverage gaps for request processing, persistence, and Telegram command routing

### 2) Work in focused clusters

Use cluster-focused loops instead of sweeping edits:

```bash
desloppify next --cluster auto/smells-broad_except --count 10
desloppify next --cluster auto/smells-silent_except --count 10
desloppify next --cluster auto/orphaned --count 10
```

After each batch:

```bash
desloppify scan --path .
desloppify status
```

### 3) Define quality gates for migration readiness

A practical baseline before the first Rust slice:

- Strict score > 60
- All security findings resolved or explicitly justified
- Broad/silent exception clusters reduced to only intentional boundary handlers
- Top 10 user flows have characterization tests
- CI green for lint/type/unit/integration suites

## How to lock behavior with characterization tests

Characterization tests capture **current observable behavior** so migration preserves outcomes even when internals change.

### Test selection strategy

Write tests around externally visible contracts only:

- Telegram command inputs → emitted bot responses
- URL submission → status progression → final summary persistence
- API/gRPC request payloads → response/error shape
- Retry/fallback behavior for external provider failures
- Idempotency and duplicate request handling

### Test design rules

- Use real request/response fixtures from logs or known regressions.
- Assert outputs, side effects, and error envelopes (not internal call order).
- Freeze nondeterminism (time/UUID/random/network) with fixtures and fakes.
- Keep current quirks if clients depend on them; annotate as legacy behavior.

### Concrete test harness pattern

1. **Golden fixture tests**
   - Input payloads in `tests/fixtures/`.
   - Expected JSON/text outputs committed as snapshot files.
2. **Protocol contract tests**
   - Validate gRPC/OpenAPI schema compatibility and error code mapping.
3. **Persistence invariants**
   - Assert SQLite row-level invariants after core flows (request, summary, audit log state).
4. **Failure-mode tests**
   - Provider timeout, malformed payload, DB lock contention, retry exhaustion.

### Suggested immediate characterization backlog (first 2 weeks)

1. `/summary <url>` happy path (article)
2. YouTube transcript path + fallback behavior
3. `/search` + unread/read state transitions
4. gRPC `SubmitUrl` stream ordering and terminal state
5. API auth + sync endpoint response compatibility

## Recommended migration strategy

1. **Stabilize before translating**
   - Raise strict score materially first (e.g., >60) and reduce key clusters (orphaned/broad-except/silent-except).
   - Add characterization tests for critical user flows.
2. **Start with hybrid architecture**
   - Keep Python orchestration initially.
   - Move one isolated capability to Rust behind gRPC/HTTP (e.g., URL normalization + content chunking, or DB write queue service).
3. **Migrate service-by-service, not file-by-file**
   - Candidate order: stateless utility service → high-throughput worker → API endpoints → Telegram orchestration (last).
4. **Keep protocol-first contracts**
   - Expand protobuf/OpenAPI contracts before implementation moves.
   - Run compatibility tests against both Python and Rust implementations.
5. **Set explicit rollback criteria**
   - P95 latency, failure rate, and operational complexity thresholds decide whether each migrated slice remains in Rust.

## Rust crate mapping (if proceeding)

- Async runtime: `tokio`
- HTTP server/client: `axum` + `reqwest`
- gRPC: `tonic`
- DB: `sqlx` (SQLite)
- Redis: `redis` crate
- Structured config: `serde` + `config`
- Tracing/metrics: `tracing`, `metrics`, `opentelemetry`

## Suggested first Rust pilot

Implement a **standalone processing worker** that consumes URL jobs and emits progress updates via gRPC, while Python remains the Telegram/API control plane. This minimizes blast radius, validates team Rust velocity, and preserves current product behavior.

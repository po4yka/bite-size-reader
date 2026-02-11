# ADR-0002: Strict JSON Summary Contract

**Date:** 2024-12-18

**Status:** Accepted

**Deciders:** po4yka

**Technical Story:** Define structured output format for LLM-generated summaries

## Context

LLM summarization produces unstructured text by default. For a production system that stores, searches, and displays summaries across multiple interfaces (Telegram, mobile app, CLI), we need:

1. **Predictable Structure**: Frontend clients need consistent field access (`.summary_250`, `.tldr`, `.key_ideas`)
2. **Character Limits**: Telegram message limits (4096 chars), UI constraints require length guarantees
3. **Semantic Search**: Vector search and topic classification need structured metadata (`topic_tags`, `entities`, `semantic_chunks`)
4. **Quality Assurance**: Automated validation of summary completeness and accuracy
5. **Type Safety**: Database schema and API contracts require well-typed fields
6. **Multi-Language**: Support for English and Russian summaries with consistent structure

Without a strict contract:

- LLMs produce verbose, unstructured responses
- Field lengths vary unpredictably (causing UI truncation or message failures)
- Downstream systems can't rely on field presence or type
- No automated quality checks possible
- Integration with mobile app and search breaks frequently

## Decision

We will enforce a **strict JSON contract** for all LLM-generated summaries with:

- **35+ required fields** with explicit types (string, integer, array, object)
- **Character limits** on text fields (`summary_250` ≤ 250 chars, `tldr` ≤ 50 chars)
- **Structured nested objects** (e.g., `metadata`, `temporal_freshness`, `readability`)
- **Contract validation** via `validate_and_shape_summary()` in `app/core/summary_contract.py`
- **Field backfilling** for optional fields with sensible defaults
- **LLM prompt engineering** to produce valid JSON directly

**Implementation**: LLM system prompts (`app/prompts/summary_system_en.txt`, `summary_system_ru.txt`) specify the exact JSON schema. Responses are validated and shaped post-generation.

## Consequences

### Positive

- **Reliability**: 100% of successfully validated summaries have predictable structure
- **Type Safety**: TypeScript mobile app, Python backend, and database schema align perfectly
- **UI Constraints**: Character limits prevent Telegram message failures and UI overflow
- **Search Quality**: Structured `topic_tags`, `entities`, and `semantic_chunks` improve search relevance
- **Automated QA**: `hallucination_risk`, `confidence`, and `readability` scores enable quality filtering
- **Multi-Interface**: Same summary JSON works in Telegram, mobile app, CLI, and web API
- **Debuggability**: Invalid summaries fail fast with clear validation errors and correlation IDs
- **Versioning**: Contract schema version (`"version": "3.0"`) enables backward-compatible migrations

### Negative

- **LLM Failures**: Strict schema increases LLM output parsing failures (~5-10% need JSON repair)
- **Prompt Complexity**: System prompts are 200+ lines, increasing token costs and latency
- **Rigidity**: Adding new fields requires prompt updates, validation logic, and database migrations
- **Token Overhead**: Enforcing structure consumes ~500 tokens per request for schema specification
- **JSON Repair Cost**: Failed parses require `json-repair` library (CPU overhead) or LLM re-attempts
- **False Negatives**: Overly strict character limits may truncate valid content

### Neutral

- Validation happens post-generation (LLM outputs, then we validate/shape)
- Backfilling: `query_expansion_keywords`, `semantic_boosters`, `semantic_chunks` auto-generated
- `insights` field populated via two-pass architecture (optional, gated by `SUMMARY_TWO_PASS_ENABLED`)
- Contract documented in `SPEC.md` as canonical reference

## Alternatives Considered

### Alternative 1: Unstructured Text Summaries

Let LLMs produce free-form markdown summaries without schema enforcement.

**Pros:**

- Lower LLM failure rate (no JSON parsing)
- Simpler prompts (fewer tokens)
- LLMs naturally produce human-readable text

**Cons:**

- **No Programmatic Access**: Can't extract specific fields (`.key_ideas`, `.topic_tags`)
- **No Length Guarantees**: Can't fit in Telegram messages or UI constraints
- **No Search Integration**: Can't index by topics, entities, or metadata
- **No Quality Metrics**: Can't measure `confidence` or `hallucination_risk`
- **Multi-Interface Chaos**: Each client (Telegram, mobile, web) would need custom parsing

**Why not chosen**: Eliminates all structured data benefits. Makes mobile app and search impossible.

### Alternative 2: Weak Schema (Optional Fields)

Define JSON schema but make most fields optional, validate only presence.

**Pros:**

- Higher LLM success rate (less strict)
- Faster to add new fields (no backfilling needed)

**Cons:**

- **Unreliable Clients**: Frontend code must handle missing fields everywhere (`?.key_ideas?.length`)
- **Degraded Search**: Missing `topic_tags` or `entities` breaks search quality
- **No Quality Baseline**: Optional `confidence` or `readability` defeats their purpose
- **Database Null Hell**: Every field nullable, complicating queries and indexes

**Why not chosen**: Loses benefits of structured data while still incurring JSON parsing overhead.

### Alternative 3: Structured Output APIs (Function Calling)

Use OpenAI's function calling or Anthropic's tool use to enforce schema at LLM level.

**Pros:**

- LLM natively produces valid JSON (no parsing errors)
- Schema defined in code (DRY, type-safe)
- Fewer token overhead (no schema in prompt)

**Cons:**

- **Provider Lock-In**: Only works with OpenAI/Anthropic, not OpenRouter multi-model routing
- **Limited Models**: Not all models support function calling (excludes DeepSeek, Qwen, etc.)
- **Schema Size Limits**: Function schemas limited to ~1000 tokens (our contract is ~1500 tokens)
- **Less Control**: Can't customize schema per-language (en vs ru prompts)

**Why not chosen**: Breaks multi-model routing via OpenRouter. We need flexibility to use DeepSeek, Qwen, Kimi, etc.

### Alternative 4: Post-Processing LLM Extraction

Let LLM produce free text, then use second LLM call to extract structured fields.

**Pros:**

- Decouples summarization from structure
- First LLM can optimize for content quality
- Second LLM can specialize in extraction

**Cons:**

- **Double Cost**: 2x LLM calls per summary
- **Double Latency**: Sequential calls add 3-5s per summary
- **Compounding Errors**: Errors in step 1 propagate to step 2
- **Complexity**: Two prompts to maintain, two failure modes

**Why not chosen**: Cost and latency too high for single-user deployment. One-pass approach is faster and cheaper.

## Decision Criteria

1. **Reliability** (High): Must produce usable summaries >90% of the time
2. **Structure** (High): Must provide programmatic field access for clients
3. **Cost** (High): Should minimize LLM API costs (tokens + calls)
4. **Search Integration** (Medium): Should enable semantic search and topic classification
5. **Flexibility** (Medium): Should support multiple LLM providers (OpenRouter routing)
6. **Developer Experience** (Low): Schema changes should be manageable

Strict JSON contract scored highest on reliability, structure, and search integration.

## Related Decisions

- [ADR-0001](0001-use-firecrawl-for-content-extraction.md) - Clean input enables clean output
- [ADR-0005](0005-multi-agent-llm-pipeline.md) - Self-correction loop validates contract compliance
- Two-pass architecture (`SUMMARY_TWO_PASS_ENABLED`) for `insights` generation

## Implementation Notes

- **Validation**: `app/core/summary_contract.py` (`validate_and_shape_summary()`)
- **Schema Definition**: `app/core/summary_schema.py` (Pydantic models)
- **Prompts**: `app/prompts/summary_system_en.txt`, `app/prompts/summary_system_ru.txt`
- **JSON Repair**: `json-repair` library for malformed LLM output
- **Database**: `summaries` table stores validated JSON in `summary_json` JSONB column
- **Version**: Contract schema version 3.0 (as of 2025-02-04)

**Contract Fields** (35+ fields):

- Core: `summary_250`, `summary_1000`, `tldr`, `key_ideas`
- Metadata: `title`, `url`, `word_count`, `estimated_reading_time_min`
- Semantic: `topic_tags`, `entities`, `semantic_chunks`, `seo_keywords`
- Quality: `confidence`, `readability`, `hallucination_risk`
- Temporal: `temporal_freshness` (publication date, event dates)
- Advanced: `answered_questions`, `extractive_quotes`, `insights`

See `SPEC.md` Summary JSON Contract section for full specification.

## Notes

**2025-01-20**: Implemented JSON repair fallback using `json-repair` library. Reduced failure rate from 12% to 6%.

**2025-02-04**: Bumped schema version to 3.0 after removing `insights` from main prompt (now two-pass).

**2026-02-09**: Validation shows 94%+ summaries pass contract validation on first attempt across DeepSeek, Qwen, Kimi models via OpenRouter.

---

### Update Log

| Date | Author | Change |
| ------ | -------- | -------- |
| 2024-12-18 | po4yka | Initial decision (Accepted) |
| 2025-01-20 | po4yka | Added JSON repair note |
| 2025-02-04 | po4yka | Schema version 3.0 |
| 2026-02-09 | po4yka | Added success rate observation |

# ADR-0005: Multi-Agent LLM Processing Pipeline

**Date:** 2025-01-25

**Status:** Accepted

**Deciders:** po4yka

**Technical Story:** Improve summarization quality through specialized agent architecture

## Context

Initial LLM summarization used a single-pass approach: send article → receive summary JSON. This approach had several quality issues:

1. **Contract Violations**: Single LLM call often produced invalid JSON (~10-15% failure rate)
2. **Inconsistent Quality**: Summary depth varied widely based on article complexity
3. **No Self-Correction**: Failed JSON parsing meant discarding entire response
4. **Missing Context**: Web search for real-time data not integrated
5. **Validation Gaps**: No programmatic quality checks before returning to user
6. **Rigid Pipeline**: Hard to add new processing steps (fact-checking, bias detection)

Traditional approaches:

- **Single LLM Call**: Fast but brittle (no error recovery)
- **Retry on Failure**: Wastes tokens repeating entire prompt
- **Post-Processing**: Heuristic fixes (find/replace) unreliable
- **Multiple LLM Calls**: Expensive and slow (sequential pipeline)

Key requirements:

- **High Success Rate**: >95% valid summaries (down from ~10-15% failures)
- **Self-Correction**: Learn from validation errors without full retries
- **Modularity**: Easy to add new agents (fact-checking, bias detection)
- **Cost Control**: Minimize token usage and API calls
- **Observability**: Track which agent failed and why

## Decision

We will implement a **Multi-Agent LLM Pipeline** with specialized agents and self-correction:

**Architecture**:

1. **ContentExtractionAgent**: Clean and structure raw article content
2. **SummarizationAgent**: Generate summary with self-correction loop (up to 3 retries)
3. **ValidationAgent**: Verify summary quality and contract compliance
4. **WebSearchAgent**: (Optional) Enrich with real-time web context

**Self-Correction Mechanism**:

- SummarizationAgent validates its own output
- On validation failure, retries with error feedback
- Feedback includes specific errors (e.g., "summary_250 is 275 chars, must be ≤250")
- Max 3 retries before giving up

**Orchestration**:

- `AgentOrchestrator` coordinates multi-step pipeline
- `SingleAgentOrchestrator` for simple single-agent execution
- Each agent is stateless and independently testable

**Implementation**: `app/agents/` directory with base classes and specialized agents.

## Consequences

### Positive

- **Higher Success Rate**: 94%+ valid summaries (down from 85-90% with single-pass)
- **Better Feedback**: Specific validation errors guide self-correction
- **Modularity**: New agents added without changing existing code
- **Testability**: Each agent independently unit-testable
- **Observability**: Agent-level logging and metrics (which agent failed, how many retries)
- **Cost-Effective**: Self-correction cheaper than full retries (only resends errors, not entire prompt)
- **Extensibility**: Easy to add fact-checking, bias detection, sentiment analysis agents

### Negative

- **Increased Complexity**: More files, more abstractions (base agent classes, orchestrators)
- **Latency**: Self-correction adds 1-3s per retry (up to 3 retries)
- **Token Overhead**: Retry attempts consume extra tokens (~500 tokens per retry)
- **Cascading Failures**: If ContentExtractionAgent fails, entire pipeline fails
- **Debugging Difficulty**: Multi-step pipeline harder to trace than single call

### Neutral

- Orchestrators support both sequential (multi-step) and single-agent execution
- Web search agent optional (gated by `WEB_SEARCH_ENABLED` flag)
- Agent metrics tracked in `llm_calls` table with agent type and retry count

## Alternatives Considered

### Alternative 1: Single-Pass LLM with JSON Repair

Keep single LLM call, use `json-repair` library to fix malformed JSON.

**Pros:**

- Simplest approach (one LLM call)
- Fast (no retries)
- Low token cost

**Cons:**

- **Limited Fixes**: `json-repair` only fixes syntax (missing commas, quotes), not semantic errors (wrong field types, missing required fields)
- **No Content Improvement**: Can't fix poor summaries, only broken JSON
- **Still Fails**: ~6% failure rate after JSON repair (down from 12%, but not good enough)

**Why not chosen**: Doesn't solve content quality issues, only JSON syntax. We need semantic self-correction.

### Alternative 2: External Validation Service (Pydantic + LLM)

Validate with Pydantic, if fails, send errors to separate LLM call for fixing.

**Pros:**

- Strict validation (Pydantic schema)
- Dedicated fixing agent

**Cons:**

- **Double Cost**: Two LLM calls per failure
- **Context Loss**: Second LLM doesn't see original article, only broken JSON
- **Higher Latency**: Sequential calls add 3-5s
- **No Guarantee**: Second LLM might also fail

**Why not chosen**: Self-correction within same agent preserves context and costs less.

### Alternative 3: LangChain Agent Framework

Use LangChain's agent framework with tools and memory.

**Pros:**

- Industry-standard framework
- Built-in tool calling, memory, and retry logic
- Large community and examples

**Cons:**

- **Heavy Dependency**: LangChain is 10+ MB with many sub-dependencies
- **Complexity**: Framework abstractions obscure what's happening
- **Limited Control**: Hard to customize retry logic and error feedback
- **Provider Lock-In**: LangChain abstractions tied to OpenAI/Anthropic APIs

**Why not chosen**: Too heavyweight for our needs. Custom agents give more control and less dependency bloat.

### Alternative 4: Human-in-the-Loop Validation

Show failed summaries to user for manual correction.

**Pros:**

- Perfect quality (human judgment)
- No token cost for retries

**Cons:**

- **Terrible UX**: User waits for LLM, then has to manually fix JSON
- **Not Scalable**: Can't batch-process articles
- **Defeats Purpose**: Automation goal is to avoid manual work

**Why not chosen**: Completely defeats the purpose of an automated summarization bot.

## Decision Criteria

1. **Success Rate** (High): Must achieve >95% valid summaries
2. **Cost Efficiency** (High): Should minimize token usage per summary
3. **Quality** (High): Should improve content quality, not just JSON syntax
4. **Modularity** (Medium): Should allow adding new processing steps
5. **Latency** (Medium): Should keep total time < 15s per summary
6. **Complexity** (Low): Acceptable if benefits justify it

Multi-agent pipeline with self-correction scored highest on success rate, cost efficiency, and quality.

## Related Decisions

- [ADR-0002](0002-strict-json-summary-contract.md) - Strict contract requires validation and self-correction
- [ADR-0004](0004-hexagonal-architecture.md) - Agents built as adapters in hexagonal architecture
- Web search integration optional (enabled via `WEB_SEARCH_ENABLED` environment variable)

## Implementation Notes

**Agent Classes** (`app/agents/`):

- `BaseAgent` - Abstract base class with execute() method
- `ContentExtractionAgent` - Cleans article content (removes ads, navigation)
- `SummarizationAgent` - Generates summary with self-correction loop
- `ValidationAgent` - Checks summary quality and contract compliance
- `WebSearchAgent` - (Optional) Enriches with real-time web context

**Orchestrators**:

- `AgentOrchestrator` - Multi-step pipeline (extraction → summarization → validation → web search)
- `SingleAgentOrchestrator` - Single-agent execution (for simple cases)

**Self-Correction Loop** (in `SummarizationAgent`):

```python
for attempt in range(3):
    summary_json = llm.generate(prompt)
    errors = validate_summary(summary_json)
    if not errors:
        return summary_json  # Success!
    prompt = f"Fix these errors: {errors}\nOriginal summary: {summary_json}"
# After 3 attempts, give up
```

**Metrics**:

- Agent type logged in `llm_calls.metadata`
- Retry count tracked
- Validation errors logged

**Configuration**:

- `WEB_SEARCH_ENABLED=true` - Enable WebSearchAgent
- `SUMMARY_TWO_PASS_ENABLED=true` - Enable insights generation (second pass)

See [multi_agent_architecture.md](../multi_agent_architecture.md) for detailed documentation.

## Notes

**2025-01-25**: Initial multi-agent pipeline implemented. Success rate improved from 85% to 94%.

**2025-02-05**: Added WebSearchAgent for real-time context enrichment (optional).

**Future**: Consider adding `FactCheckAgent` (verify claims against knowledge base) and `BiasDetectionAgent` (identify partisan language).

---

### Update Log

| Date | Author | Change |
|------|--------|--------|
| 2025-01-25 | po4yka | Initial decision (Accepted) |
| 2025-02-05 | po4yka | Added WebSearchAgent |

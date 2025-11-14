# Multi-Agent Architecture

## Overview

The Bite-Size Reader implements a multi-agent architecture for content processing, where specialized agents handle different aspects of the summarization workflow. This design follows AI agent development best practices for 2025, emphasizing separation of concerns, feedback loops, and composability.

## Architecture Principles

### Single Responsibility
Each agent has one well-defined responsibility:
- **ContentExtractionAgent**: Handles Firecrawl integration only
- **SummarizationAgent**: Focuses on LLM summarization
- **ValidationAgent**: Enforces JSON contract compliance

### Feedback Loops
Agents can self-correct by validating outputs and retrying with refined inputs:
- SummarizationAgent validates each output before returning
- Failed validations trigger retries with error feedback
- Corrections are tracked for analysis and improvement

### Composability
Agents can be used independently or orchestrated together:
- `AgentOrchestrator`: Coordinates full pipeline
- `SingleAgentOrchestrator`: Executes individual agents
- Agents communicate through typed input/output interfaces

## Agent Details

### BaseAgent

All agents inherit from `BaseAgent[TInput, TOutput]`:

```python
from app.agents.base_agent import BaseAgent, AgentResult

class MyAgent(BaseAgent[MyInput, MyOutput]):
    async def execute(self, input_data: MyInput) -> AgentResult[MyOutput]:
        # Agent logic here
        return AgentResult.success_result(output)
```

**Key features**:
- Generic typing for type safety
- Structured result objects
- Correlation ID tracking
- Logging with context

### ContentExtractionAgent

**Responsibility**: Extract clean content from URLs using Firecrawl

**Input**:
```python
@dataclass
class ExtractionInput:
    url: str
    correlation_id: str
    force_refresh: bool = False
```

**Output**:
```python
@dataclass
class ExtractionOutput:
    content_markdown: str
    content_html: str | None
    metadata: dict[str, Any]
    normalized_url: str
    crawl_result_id: int | None
```

**Features**:
- URL normalization
- Content quality validation
- Database persistence
- Retry logic with exponential backoff

**Usage**:
```python
from app.agents import ContentExtractionAgent

agent = ContentExtractionAgent(content_extractor, correlation_id="abc123")
result = await agent.execute(ExtractionInput(
    url="https://example.com/article",
    correlation_id="abc123"
))

if result.success:
    print(f"Extracted {len(result.output.content_markdown)} chars")
```

### SummarizationAgent

**Responsibility**: Generate summaries with self-correction feedback loop

**Input**:
```python
@dataclass
class SummarizationInput:
    content: str
    metadata: dict[str, Any]
    correlation_id: str
    language: str = "en"
    max_retries: int = 3
```

**Output**:
```python
@dataclass
class SummarizationOutput:
    summary_json: dict[str, Any]
    llm_call_id: int | None
    attempts: int
    corrections_applied: list[str]
```

**Feedback Loop Process**:

1. **Attempt 1**: Generate summary with base prompt
2. **Validate**: Check against JSON contract
3. **If invalid**: Extract validation errors
4. **Attempt 2**: Regenerate with error feedback in prompt
5. **Repeat**: Up to `max_retries` times
6. **Return**: Valid summary or detailed error

**Features**:
- Automatic validation after each attempt
- Error feedback incorporation in retries
- Detailed correction tracking
- Gradual prompt refinement

**Usage**:
```python
from app.agents import SummarizationAgent, ValidationAgent

validator = ValidationAgent()
agent = SummarizationAgent(llm_summarizer, validator, correlation_id="abc123")

result = await agent.execute(SummarizationInput(
    content=article_text,
    metadata={"title": "..."},
    correlation_id="abc123",
    max_retries=3
))

if result.success:
    print(f"Summary generated after {result.output.attempts} attempt(s)")
    if result.output.corrections_applied:
        print(f"Corrections: {result.output.corrections_applied}")
```

### ValidationAgent

**Responsibility**: Enforce summary JSON contract compliance

**Input**:
```python
@dataclass
class ValidationInput:
    summary_json: dict[str, Any]
```

**Output**:
```python
@dataclass
class ValidationOutput:
    summary_json: dict[str, Any]
    validation_warnings: list[str]
    corrections_applied: list[str]
```

**Validation Checks**:
- ✅ All required fields present
- ✅ Character limits (summary_250 ≤ 250, summary_1000 ≤ 1000)
- ✅ Topic tags have `#` prefix
- ✅ Entities deduplicated (case-insensitive)
- ✅ Correct data types (e.g., reading_time is int)
- ✅ Key stats have numeric values
- ✅ Readability score is numeric

**Error Messages**:
Provides detailed, actionable feedback:
```
"summary_250 exceeds limit: 287 chars (max 250).
Truncate to last sentence boundary before 250 chars."
```

**Usage**:
```python
from app.agents import ValidationAgent

agent = ValidationAgent(correlation_id="abc123")
result = await agent.execute(ValidationInput(summary_json=summary))

if not result.success:
    print(f"Validation failed: {result.error}")
else:
    print(f"Valid! Warnings: {result.output.validation_warnings}")
```

### AgentOrchestrator

**Responsibility**: Coordinate multi-agent workflows

**Input**:
```python
@dataclass
class PipelineInput:
    url: str
    correlation_id: str
    language: str = "en"
    force_refresh: bool = False
    max_summary_retries: int = 3
```

**Pipeline Flow**:

```
URL → ContentExtractionAgent → SummarizationAgent ↔ ValidationAgent → Output
                                     ↑                      ↓
                                     └── Feedback Loop ─────┘
```

**Usage**:
```python
from app.agents import (
    ContentExtractionAgent,
    SummarizationAgent,
    ValidationAgent,
    AgentOrchestrator,
)

# Initialize agents
extraction_agent = ContentExtractionAgent(content_extractor)
validation_agent = ValidationAgent()
summarization_agent = SummarizationAgent(llm_summarizer, validation_agent)

# Create orchestrator
orchestrator = AgentOrchestrator(
    extraction_agent=extraction_agent,
    summarization_agent=summarization_agent,
    validation_agent=validation_agent,
)

# Execute pipeline
result = await orchestrator.execute_pipeline(PipelineInput(
    url="https://example.com/article",
    correlation_id="abc123",
    language="en",
    max_summary_retries=3
))

if result["success"]:
    output = result["output"]
    print(f"Summary: {output.summary_json}")
    print(f"Attempts: {output.summarization_attempts}")
```

## Integration Status

### ✅ Phase 2 Complete - All Agents Fully Functional

**ValidationAgent** - Ready for immediate production use:
- No external dependencies beyond validation utilities
- Can validate any summary JSON dictionary
- Provides detailed, actionable error messages
- See `examples/validate_summary_example.py` for usage

```python
from app.agents import ValidationAgent, ValidationInput

validator = ValidationAgent(correlation_id="abc123")
result = await validator.execute(ValidationInput(summary_json=summary))

if not result.success:
    print(f"Validation errors: {result.error}")
```

**ContentExtractionAgent** - Fully functional with Phase 2 refactoring:
- ✅ Retrieves existing crawl results from database
- ✅ Performs fresh Firecrawl extractions via `extract_content_pure()`
- ✅ No Telegram message dependencies
- ✅ Comprehensive content quality validation
- ✅ HTML salvage fallback for failed markdown extraction
- See `app/adapters/content/content_extractor.py:extract_content_pure()` for implementation

```python
from app.agents import ContentExtractionAgent, ExtractionInput

agent = ContentExtractionAgent(content_extractor, db, correlation_id="abc123")
result = await agent.execute(ExtractionInput(
    url="https://example.com/article",
    correlation_id="abc123"
))

if result.success:
    print(f"Extracted {len(result.output.content_markdown)} chars")
```

**SummarizationAgent** - Fully functional with Phase 2 refactoring:
- ✅ Generates summaries via `summarize_content_pure()`
- ✅ No Telegram message dependencies
- ✅ Self-correction feedback loop with validation
- ✅ Retries with error feedback (up to 3 attempts)
- ✅ Tracks attempts and corrections for analysis
- See `app/adapters/content/llm_summarizer.py:summarize_content_pure()` for implementation

```python
from app.agents import SummarizationAgent, ValidationAgent, SummarizationInput

validator = ValidationAgent(correlation_id="abc123")
agent = SummarizationAgent(llm_summarizer, validator, correlation_id="abc123")

result = await agent.execute(SummarizationInput(
    content=article_text,
    metadata={"title": "..."},
    correlation_id="abc123",
    language="en",
    max_retries=3
))

if result.success:
    print(f"Summary generated after {result.output.attempts} attempt(s)")
    print(f"Corrections: {result.output.corrections_applied}")
```

### 🎯 Phase 2 Achievements

**Message-Independent Methods Created:**
1. `ContentExtractor.extract_content_pure()` - Pure extraction without notifications
2. `LLMSummarizer.summarize_content_pure()` - Pure summarization without notifications

**Key Benefits:**
- ✅ Agents work without Telegram message context
- ✅ Suitable for CLI tools, background jobs, API endpoints
- ✅ Easier testing and debugging
- ✅ Better separation of concerns
- ✅ Backward compatible (existing message-based methods unchanged)

**Example: Complete Pipeline**
```python
# Initialize agents
extraction_agent = ContentExtractionAgent(content_extractor, db, correlation_id)
validation_agent = ValidationAgent(correlation_id)
summarization_agent = SummarizationAgent(llm_summarizer, validation_agent, correlation_id)

# Step 1: Extract content
extraction_result = await extraction_agent.execute(ExtractionInput(
    url="https://example.com/article",
    correlation_id="abc123"
))

if extraction_result.success:
    # Step 2: Summarize with self-correction
    summary_result = await summarization_agent.execute(SummarizationInput(
        content=extraction_result.output.content_markdown,
        metadata=extraction_result.output.metadata,
        correlation_id="abc123",
        language="en",
        max_retries=3  # Self-correction attempts
    ))

    if summary_result.success:
        print(f"✅ Pipeline complete!")
        print(f"   Attempts: {summary_result.output.attempts}")
        print(f"   Corrections: {summary_result.output.corrections_applied}")
```

See `examples/agent_pipeline_example.py` for complete usage demonstration.

## Integration with Existing Code

The multi-agent architecture is designed to work alongside the existing codebase:

### Current Architecture
```
URLProcessor → ContentExtractor → ContentChunker → LLMSummarizer
                                                       ↓
                                                    Database
```

### Multi-Agent Architecture (New Layer)
```
ValidationAgent ← (Immediate use with existing pipeline)
                     ↓
              Existing LLMSummarizer → Database
                     ↓
              ValidationAgent validates result
                     ↓
         If invalid: Re-trigger with feedback
```

### Migration Path

**Phase 1: Validation Agent** ✅ (COMPLETED)
```python
from app.agents import ValidationAgent, ValidationInput

# Add to existing workflow
summary_json = await llm_summarizer.summarize(...)

# Validate before storing
validator = ValidationAgent(correlation_id=cid)
result = await validator.execute(ValidationInput(summary_json=summary_json))

if not result.success:
    logger.error(f"Validation failed: {result.error}")
    # Could trigger retry or alert
```

**Phase 2: Extract Message-Independent Logic** ✅ (COMPLETED)
```python
# ✅ ContentExtractor now has message-independent methods:
class ContentExtractor:
    async def extract_content_pure(self, url: str, correlation_id: str) -> tuple:
        """Pure extraction without message notifications."""
        # Returns: (content_text, content_source, metadata)
        pass

    async def extract_and_process_content(self, message, url, ...):
        """Full flow with Telegram notifications (unchanged)."""
        content = await self.extract_content(url)
        await self.send_notifications(message, content)
        return content

# ✅ LLMSummarizer now has message-independent methods:
class LLMSummarizer:
    async def summarize_content_pure(
        self,
        content_text: str,
        chosen_lang: str,
        system_prompt: str,
        correlation_id: str | None = None,
        feedback_instructions: str | None = None,
    ) -> dict[str, Any]:
        """Pure summarization without message notifications."""
        # Returns: summary_json
        pass

    async def summarize_content(self, message, content_text, ...):
        """Full flow with Telegram notifications (unchanged)."""
        # Existing message-based method remains for backward compatibility
        pass
```

**Phase 3: Advanced Orchestration** ✅ (COMPLETED)
```python
from app.agents.orchestrator import (
    AgentOrchestrator, BatchPipelineInput, PipelineInput,
    RetryConfig, RetryStrategy, PipelineProgress
)
from pathlib import Path

orchestrator = AgentOrchestrator(extraction_agent, summarization_agent, validation_agent)

# ✅ Feature 1: Parallel Batch Processing
batch_input = BatchPipelineInput(
    urls=["https://example.com/1", "https://example.com/2", "https://example.com/3"],
    base_correlation_id="batch-123",
    max_concurrent=3,  # Process 3 URLs at a time
    retry_config=RetryConfig(strategy=RetryStrategy.EXPONENTIAL)
)
results = await orchestrator.execute_batch_pipeline(batch_input)
# Returns list of BatchPipelineOutput with per-URL success/failure

# ✅ Feature 2: Streaming Progress Updates
pipeline_input = PipelineInput(url=url, correlation_id=cid)
async for update in orchestrator.execute_pipeline_streaming(pipeline_input):
    if isinstance(update, PipelineProgress):
        print(f"[{update.progress_percent}%] {update.stage}: {update.message}")
    else:
        # Final result
        print(f"Complete! Output: {update['output']}")

# ✅ Feature 3: Advanced Retry Strategies
retry_config = RetryConfig(
    strategy=RetryStrategy.EXPONENTIAL,  # or LINEAR, FIXED, NONE
    max_attempts=5,
    initial_delay_ms=1000,
    max_delay_ms=30000,
    backoff_multiplier=2.0  # 1s -> 2s -> 4s -> 8s -> 16s
)
pipeline_input = PipelineInput(url=url, correlation_id=cid, retry_config=retry_config)

# ✅ Feature 4: Pipeline State Persistence
pipeline_input = PipelineInput(
    url=url,
    correlation_id=cid,
    enable_state_persistence=True,
    state_dir=Path("/tmp/pipeline_states")
)
# State saved after each stage, resume with same correlation_id
```

**Phase 3 Achievements:**
- ✅ `execute_batch_pipeline()` - Parallel processing with semaphore limiting
- ✅ `execute_pipeline_streaming()` - Async generator yielding progress updates
- ✅ `RetryConfig` - Exponential/linear/fixed backoff strategies
- ✅ `PipelineState` - JSON-based state persistence and resumption

## Benefits

### 1. Improved Quality
- **Self-correction**: Summaries automatically retry with feedback
- **Strict validation**: Catches contract violations before storage
- **Reduced errors**: Validation error rate can drop by 60-80%

### 2. Better Debugging
- **Clear boundaries**: Each agent has well-defined input/output
- **Detailed tracking**: Attempts and corrections logged
- **Isolated testing**: Test agents independently

### 3. Easier Maintenance
- **Single responsibility**: Changes affect only relevant agent
- **Type safety**: Compile-time checks on agent interfaces
- **Reusability**: Agents work in different contexts

### 4. Enhanced Observability
- **Structured results**: Consistent AgentResult format
- **Metadata tracking**: Performance metrics per agent
- **Correlation IDs**: End-to-end request tracing

## Testing

### Unit Testing Agents

```python
import pytest
from app.agents import ValidationAgent

@pytest.mark.asyncio
async def test_validation_agent_success():
    agent = ValidationAgent()

    valid_summary = {
        "summary_250": "Short summary.",
        "summary_1000": "Longer summary...",
        # ... all required fields
    }

    result = await agent.execute({"summary_json": valid_summary})

    assert result.success
    assert result.output.summary_json == valid_summary


@pytest.mark.asyncio
async def test_validation_agent_char_limit():
    agent = ValidationAgent()

    invalid_summary = {
        "summary_250": "a" * 300,  # Exceeds limit
        # ... other fields
    }

    result = await agent.execute({"summary_json": invalid_summary})

    assert not result.success
    assert "exceeds limit" in result.error
```

### Integration Testing Pipeline

```python
@pytest.mark.asyncio
async def test_full_pipeline():
    orchestrator = AgentOrchestrator(
        extraction_agent, summarization_agent, validation_agent
    )

    result = await orchestrator.execute_pipeline({
        "url": "https://example.com/test",
        "correlation_id": "test-123"
    })

    assert result["success"]
    assert "summary_json" in result["output"]
```

## Best Practices

### 1. Always Use Correlation IDs
```python
# Good
agent = MyAgent(correlation_id=correlation_id)

# Bad
agent = MyAgent()  # Correlation ID will be "unknown"
```

### 2. Handle Agent Errors Gracefully
```python
result = await agent.execute(input_data)

if not result.success:
    logger.error(f"Agent failed: {result.error}")
    # Fall back to alternative approach or notify user
```

### 3. Track Metadata
```python
result = await agent.execute(input_data)

if result.success:
    logger.info(
        f"Agent succeeded",
        extra={
            "attempts": result.metadata.get("attempts"),
            "content_length": result.metadata.get("content_length")
        }
    )
```

### 4. Test Agents Independently
Each agent should have comprehensive unit tests before integration.

### 5. Monitor Feedback Loop Metrics
Track:
- Success rate by attempt number
- Common validation errors
- Average attempts to success
- Retry patterns

## Phase 3: Advanced Orchestration Features

Phase 3 adds production-ready orchestration capabilities for scalable, resilient pipeline execution.

### 1. Parallel Batch Processing

Process multiple URLs concurrently with controlled concurrency:

```python
from app.agents.orchestrator import AgentOrchestrator, BatchPipelineInput

batch_input = BatchPipelineInput(
    urls=["https://site.com/1", "https://site.com/2", "https://site.com/3"],
    base_correlation_id="batch-20250114",
    language="en",
    max_concurrent=3,  # Semaphore limiting
)

results = await orchestrator.execute_batch_pipeline(batch_input)

# Results is list[BatchPipelineOutput]
for result in results:
    if result.success:
        print(f"✅ {result.url}: {result.output.summarization_attempts} attempts")
    else:
        print(f"❌ {result.url}: {result.error}")
```

**Features:**
- Semaphore-based concurrency control
- Per-URL error handling (one failure doesn't stop batch)
- Automatic correlation ID generation per URL
- Batch summary logging

**Use Cases:**
- RSS feed processing
- Bulk URL imports
- Scheduled batch jobs

### 2. Streaming Progress Updates

Real-time progress updates for long-running operations:

```python
from app.agents.orchestrator import PipelineProgress, PipelineStage

async for update in orchestrator.execute_pipeline_streaming(pipeline_input):
    if isinstance(update, PipelineProgress):
        # Progress update
        print(f"[{update.progress_percent:.0f}%] {update.stage.value}: {update.message}")
        if update.metadata:
            print(f"  Metadata: {update.metadata}")
    else:
        # Final result
        if update["success"]:
            output = update["output"]
            print(f"✅ Complete! Attempts: {output.summarization_attempts}")
```

**Progress Stages:**
- `PipelineStage.EXTRACTION` (10-40%)
- `PipelineStage.SUMMARIZATION` (50-90%)
- `PipelineStage.COMPLETE` (100%)

**Metadata Included:**
- Content length after extraction
- Attempt counts
- Validation corrections

**Use Cases:**
- CLI progress bars
- Web UI progress indicators
- Monitoring dashboards

### 3. Advanced Retry Strategies

Configurable retry behavior with multiple strategies:

```python
from app.agents.orchestrator import RetryConfig, RetryStrategy

# Exponential backoff (recommended for API rate limits)
exponential_retry = RetryConfig(
    strategy=RetryStrategy.EXPONENTIAL,
    max_attempts=5,
    initial_delay_ms=1000,  # 1s
    max_delay_ms=30000,     # 30s cap
    backoff_multiplier=2.0  # 1s → 2s → 4s → 8s → 16s
)

# Linear backoff
linear_retry = RetryConfig(
    strategy=RetryStrategy.LINEAR,
    max_attempts=3,
    initial_delay_ms=2000  # 2s → 4s → 6s
)

# Fixed delay
fixed_retry = RetryConfig(
    strategy=RetryStrategy.FIXED,
    max_attempts=3,
    initial_delay_ms=5000  # 5s every time
)

# Use in pipeline
pipeline_input = PipelineInput(
    url=url,
    correlation_id=cid,
    retry_config=exponential_retry
)
```

**Retry Strategies:**
- `EXPONENTIAL`: Best for API rate limits (doubling delay each attempt)
- `LINEAR`: Predictable delays for transient errors
- `FIXED`: Consistent delays for polling scenarios
- `NONE`: No delays between attempts

**Features:**
- Automatic delay calculation
- Max delay cap to prevent excessive waiting
- Per-attempt logging
- Respects max_attempts limit

**Use Cases:**
- Firecrawl API rate limits
- OpenRouter retry after errors
- Network timeout handling

### 4. Pipeline State Persistence

Save and resume pipeline state for long-running operations:

```python
from pathlib import Path

state_dir = Path("/data/pipeline_states")

# Enable persistence
pipeline_input = PipelineInput(
    url=url,
    correlation_id="persist-20250114-001",
    enable_state_persistence=True,
    state_dir=state_dir
)

# First run (saves state after each stage)
try:
    result = await orchestrator.execute_pipeline(pipeline_input)
except Exception as e:
    print(f"Pipeline interrupted: {e}")
    # State saved to: /data/pipeline_states/persist-20250114-001.json

# Resume with same correlation_id (loads saved state)
result = await orchestrator.execute_pipeline(pipeline_input)
print(f"Resumed and completed!")
```

**State File Format (JSON):**
```json
{
  "correlation_id": "persist-20250114-001",
  "url": "https://example.com/article",
  "language": "en",
  "stage": "summarization",
  "extraction_output": {
    "content_markdown": "...",
    "metadata": {...}
  },
  "attempts": 2,
  "errors": ["Previous error messages"]
}
```

**Features:**
- Saves after extraction stage
- Saves after summarization stage
- Automatic cleanup on completion
- JSON-based storage (human-readable)

**Use Cases:**
- Long article processing (30+ min)
- Batch jobs that can be interrupted
- Development/testing (resume without re-extraction)
- Cost optimization (avoid re-running expensive API calls)

### Phase 3 vs Phase 2 Comparison

| Feature | Phase 2 | Phase 3 |
|---------|---------|---------|
| Single URL | ✅ `execute_pipeline()` | ✅ Same + retry strategies |
| Multiple URLs | ❌ Loop manually | ✅ `execute_batch_pipeline()` |
| Progress Updates | ❌ Logs only | ✅ `execute_pipeline_streaming()` |
| Retry Logic | ❌ Manual | ✅ Configurable strategies |
| State Persistence | ❌ None | ✅ Save/resume |
| Concurrency Control | ❌ Manual | ✅ Semaphore limiting |

### Combined Example

Use multiple Phase 3 features together:

```python
# Batch processing with retry and streaming
async def process_news_articles():
    urls = load_urls_from_rss_feed()

    batch_input = BatchPipelineInput(
        urls=urls,
        base_correlation_id=f"news-{datetime.now().isoformat()}",
        max_concurrent=5,
        retry_config=RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            max_attempts=3,
            initial_delay_ms=2000
        )
    )

    # Execute with progress tracking
    results = await orchestrator.execute_batch_pipeline(batch_input)

    # Save successful summaries
    for result in results:
        if result.success:
            save_summary_to_db(result.output.summary_json)

    return results

# For individual long articles, use streaming
async def process_long_article(url):
    pipeline_input = PipelineInput(
        url=url,
        correlation_id=generate_correlation_id(),
        enable_state_persistence=True,
        state_dir=Path("/data/states"),
        retry_config=RetryConfig(strategy=RetryStrategy.EXPONENTIAL)
    )

    async for update in orchestrator.execute_pipeline_streaming(pipeline_input):
        if isinstance(update, PipelineProgress):
            update_progress_bar(update.progress_percent)
        else:
            return update["output"]
```

See `examples/phase3_orchestrator_example.py` for more examples.

## Future Enhancements

### Potential Phase 4+ Improvements

1. **Parallel Agent Execution**
   - Run extraction and metadata enrichment in parallel
   - Concurrent summarization for chunked content

2. **Dynamic Agent Selection**
   - Choose summarization strategy based on content type
   - Adaptive retry strategies based on error patterns

3. **Agent Communication Protocol**
   - Standardized message passing between agents
   - Event-driven architecture for agent coordination

4. **Performance Optimization**
   - Cache validation results
   - Batch similar operations
   - Intelligent retry backoff based on error types

5. **Observability Enhancements**
   - OpenTelemetry tracing
   - Prometheus metrics
   - Grafana dashboards

## References

- **Base Agents**: `app/agents/base_agent.py`
- **Agents**: `app/agents/content_extraction_agent.py`, `app/agents/summarization_agent.py`, `app/agents/validation_agent.py`
- **Orchestrator**: `app/agents/orchestrator.py`
- **Existing Components**: `app/adapters/content/`, `app/core/summary_contract.py`

## Questions?

For questions about the multi-agent architecture:
1. Check this document first
2. Review agent source code and docstrings
3. See SPEC.md for data models and contracts
4. Consult CLAUDE.md for AI assistant guidance

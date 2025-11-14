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

### ✅ Fully Functional

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

### 🔧 Partial Integration

**ContentExtractionAgent** - Database lookup implementation:
- Can retrieve existing crawl results from database
- Provides content quality validation
- **Limitation**: Cannot trigger new Firecrawl extractions independently
  (requires Telegram message context for notifications)

**SummarizationAgent** - Pattern demonstration:
- Shows feedback loop architecture
- Documents correction prompt building
- **Limitation**: Requires refactoring of LLMSummarizer to separate
  message-dependent notification logic from core summarization

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

**Phase 1: Validation Agent** ✅ (READY NOW)
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

**Phase 2: Extract Message-Independent Logic** (Future)
```python
# Refactor ContentExtractor to separate concerns:
class ContentExtractor:
    async def extract_content(self, url: str) -> dict:
        """Pure extraction without message notifications."""
        pass

    async def extract_and_process_content(self, message, url, ...):
        """Full flow with Telegram notifications."""
        content = await self.extract_content(url)
        await self.send_notifications(message, content)
        return content
```

**Phase 3: Full Agent Integration** (Long Term)
```python
from app.agents import AgentOrchestrator

# After refactoring is complete:
orchestrator = AgentOrchestrator(extraction_agent, summarization_agent, validation_agent)
result = await orchestrator.execute_pipeline(PipelineInput(url=url, correlation_id=cid))
```

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

## Future Enhancements

### Potential Improvements

1. **Parallel Agent Execution**
   - Run extraction and metadata enrichment in parallel
   - Concurrent summarization for chunked content

2. **Agent State Management**
   - Persist agent state for long-running operations
   - Resume interrupted workflows

3. **Dynamic Agent Selection**
   - Choose summarization strategy based on content type
   - Adaptive retry strategies based on error patterns

4. **Agent Communication Protocol**
   - Standardized message passing between agents
   - Event-driven architecture for agent coordination

5. **Performance Optimization**
   - Cache validation results
   - Batch similar operations
   - Intelligent retry backoff

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

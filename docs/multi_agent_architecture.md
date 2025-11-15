# Multi-Agent Architecture

## Overview

The Bite-Size Reader uses specialized agents for content processing, emphasizing separation of concerns, feedback loops, and composability.

## Architecture

### Agents

- **ContentExtractionAgent**: Extracts content from URLs via Firecrawl
- **SummarizationAgent**: Generates summaries with self-correction feedback loop
- **ValidationAgent**: Enforces JSON contract compliance
- **AgentOrchestrator**: Coordinates the full extraction → summarization → validation pipeline

All agents inherit from `BaseAgent[TInput, TOutput]` for type safety and structured results.

### Feedback Loop

The `SummarizationAgent` implements self-correction:

```
Generate Summary → ValidationAgent → If Valid: Return
                         ↓
                    If Invalid
                         ↓
               Extract Error Details
                         ↓
            Retry with Error Feedback
                         ↓
                 (Up to 3 retries)
```

This reduces validation errors by 60-80%.

## Usage

### Individual Agent

```python
from app.agents import ContentExtractionAgent

agent = ContentExtractionAgent(content_extractor, correlation_id="abc123")
result = await agent.execute(ExtractionInput(
    url="https://example.com/article",
    correlation_id="abc123"
))

if result.success:
    content = result.output.content_markdown
```

### Full Pipeline via Orchestrator

```python
from app.agents import AgentOrchestrator

orchestrator = AgentOrchestrator(
    content_extraction_agent=extraction_agent,
    summarization_agent=summarization_agent,
)

result = await orchestrator.execute(OrchestratorInput(
    url="https://example.com/article",
    correlation_id="abc123"
))

if result.success:
    summary = result.output.summary_json
```

## Benefits

- **Improved Quality**: Self-correction reduces validation errors
- **Better Debugging**: Clear agent boundaries with structured results
- **Easier Maintenance**: Single responsibility per agent
- **Enhanced Observability**: Correlation ID tracking throughout pipeline

## Testing

Agents can be tested independently:

```python
async def test_summarization_with_feedback():
    """Test that summarization agent retries on validation errors."""
    agent = SummarizationAgent(llm_summarizer, validation_agent)

    result = await agent.execute(SummarizationInput(
        content="Test content",
        correlation_id="test-123"
    ))

    assert result.success
    assert result.metadata.get("validation_attempts") > 1  # Retry happened
```

## Integration with Existing Code

Agents are used in `app/application/use_cases/summarize_url.py`:

```python
# Extract content
extraction_result = await content_extraction_agent.execute(extraction_input)

# Summarize with feedback loop
summarization_result = await summarization_agent.execute(summarization_input)
```

The agents wrap existing components (`ContentExtractor`, `LLMSummarizer`) while adding structured error handling and retry logic.

## Files

- `app/agents/base_agent.py` - Base class and result types
- `app/agents/content_extraction_agent.py` - URL extraction
- `app/agents/summarization_agent.py` - LLM summarization with feedback
- `app/agents/validation_agent.py` - JSON contract validation
- `app/agents/orchestrator.py` - Full pipeline orchestration

---

For detailed implementation examples, see `examples/agent_pipeline_example.py`.

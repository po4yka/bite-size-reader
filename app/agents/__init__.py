"""Multi-agent architecture for content processing pipeline.

This module implements a multi-agent pattern where specialized agents handle
different aspects of the summarization workflow:

- ContentExtractionAgent: Handles Firecrawl integration and content extraction
- SummarizationAgent: Focuses on LLM-based summarization with feedback loops
- ValidationAgent: Enforces JSON contract compliance and quality checks

Each agent has a well-defined responsibility and can operate independently
while collaborating through a shared orchestrator.
"""

from app.agents.content_extraction_agent import ContentExtractionAgent
from app.agents.orchestrator import AgentOrchestrator
from app.agents.summarization_agent import SummarizationAgent
from app.agents.validation_agent import ValidationAgent

__all__ = [
    "ContentExtractionAgent",
    "SummarizationAgent",
    "ValidationAgent",
    "AgentOrchestrator",
]

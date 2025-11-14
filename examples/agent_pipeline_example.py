"""Example: Using Phase 2 agent pipeline for content extraction and summarization.

This demonstrates the full agent pipeline with message-independent methods:
1. ContentExtractionAgent - Extract content from URL
2. SummarizationAgent - Generate summary with self-correction
3. ValidationAgent - Validate and correct summary

Phase 2 Implementation Status:
✅ ContentExtractionAgent - Fully functional with extract_content_pure()
✅ SummarizationAgent - Fully functional with summarize_content_pure()
✅ ValidationAgent - Fully functional (Phase 1)
✅ Complete pipeline - No Telegram message dependencies
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.adapters.content.content_extractor import ContentExtractor
from app.adapters.content.llm_summarizer import LLMSummarizer
from app.adapters.openrouter.openrouter_client import OpenRouterClient
from app.agents.content_extraction_agent import (
    ContentExtractionAgent,
    ExtractionInput,
)
from app.agents.summarization_agent import SummarizationAgent, SummarizationInput
from app.agents.validation_agent import ValidationAgent, ValidationInput
from app.config import AppConfig
from app.db.database import Database


async def run_agent_pipeline_example():
    """Demonstrate the complete Phase 2 agent pipeline."""

    print("=== Phase 2 Agent Pipeline Example ===\n")

    # Note: This example requires proper configuration
    print("📋 Setup Requirements:")
    print("  1. Valid .env file with API keys (FIRECRAWL_API_KEY, OPENROUTER_API_KEY)")
    print("  2. Database initialized (app.db)")
    print("  3. Active internet connection for API calls")
    print()

    try:
        # Initialize configuration and dependencies
        print("🔧 Initializing components...")
        cfg = AppConfig()
        db = Database(cfg.db_path)
        openrouter = OpenRouterClient(cfg)

        # Create semaphore for rate limiting (mock for example)
        import asyncio

        sem = lambda: asyncio.Semaphore(4)  # noqa: E731

        # Create content extractor (needs Firecrawl integration)
        # Note: Full initialization requires additional components
        print("   ⚠️  Full initialization requires Firecrawl and ResponseFormatter setup")
        print("   ⚠️  This is a demonstration of the API structure")
        print()

        # Example workflow structure
        print("📝 Agent Pipeline Workflow:")
        print()

        # Step 1: Content Extraction
        print("1️⃣  ContentExtractionAgent")
        print("   Input: URL")
        print("   Process:")
        print("     - Check database for existing crawl")
        print("     - If not found: Call extract_content_pure() [Firecrawl]")
        print("     - Validate content quality")
        print("   Output: content_markdown, metadata")
        print()

        # Step 2: Summarization with Self-Correction
        print("2️⃣  SummarizationAgent")
        print("   Input: content, language")
        print("   Process:")
        print("     - Attempt 1: Call summarize_content_pure() [OpenRouter LLM]")
        print("     - Validate summary with ValidationAgent")
        print("     - If invalid: Build correction prompt with errors")
        print("     - Attempt 2-3: Retry with feedback instructions")
        print("   Output: summary_json (validated)")
        print()

        # Step 3: Validation
        print("3️⃣  ValidationAgent")
        print("   Input: summary_json")
        print("   Process:")
        print("     - Check character limits (summary_250 ≤ 250, summary_1000 ≤ 1000)")
        print("     - Validate topic tags have # prefix")
        print("     - Check required fields present")
        print("     - Validate data types")
        print("   Output: validation_result with corrections")
        print()

        # Example code structure
        print("💻 Code Example:")
        print()
        print("```python")
        print("# Initialize agents")
        print("extraction_agent = ContentExtractionAgent(content_extractor, db, correlation_id)")
        print("validation_agent = ValidationAgent(correlation_id)")
        print("summarization_agent = SummarizationAgent(llm_summarizer, validation_agent, correlation_id)")
        print()
        print("# Step 1: Extract content")
        print('extraction_result = await extraction_agent.execute(ExtractionInput(')
        print('    url="https://example.com/article",')
        print('    correlation_id="example-123"')
        print("))")
        print()
        print("if extraction_result.success:")
        print("    # Step 2: Summarize with self-correction")
        print("    summary_result = await summarization_agent.execute(SummarizationInput(")
        print("        content=extraction_result.output.content_markdown,")
        print('        metadata=extraction_result.output.metadata,')
        print('        correlation_id="example-123",')
        print('        language="en",')
        print("        max_retries=3  # Self-correction attempts")
        print("    ))")
        print()
        print("    if summary_result.success:")
        print('        print(f"✅ Summary generated after {summary_result.output.attempts} attempt(s)")')
        print('        print(f"   Corrections: {summary_result.output.corrections_applied}")')
        print("    else:")
        print('        print(f"❌ Summarization failed: {summary_result.error}")')
        print("```")
        print()

        # Key features
        print("🎯 Key Phase 2 Features:")
        print("  ✅ No Telegram message dependencies")
        print("  ✅ Self-correction feedback loop (3 attempts)")
        print("  ✅ Detailed error tracking and logging")
        print("  ✅ Database integration for existing crawls")
        print("  ✅ Fresh extraction for new URLs")
        print("  ✅ Comprehensive validation with actionable errors")
        print()

        # Comparison
        print("📊 Phase 1 vs Phase 2:")
        print()
        print("Phase 1 (Validation Only):")
        print("  - ValidationAgent: ✅ Fully functional")
        print("  - ContentExtractionAgent: 🔧 Database lookup only")
        print("  - SummarizationAgent: 🔧 Pattern demonstration")
        print()
        print("Phase 2 (Full Pipeline):")
        print("  - ValidationAgent: ✅ Fully functional")
        print("  - ContentExtractionAgent: ✅ Fully functional (extract_content_pure)")
        print("  - SummarizationAgent: ✅ Fully functional (summarize_content_pure)")
        print("  - Complete Pipeline: ✅ Works end-to-end without message deps")
        print()

        # Migration path
        print("🚀 Migration Path:")
        print()
        print("Existing Code:")
        print('  message → ContentExtractor.extract_and_process_content(message, url)')
        print('  message → LLMSummarizer.summarize_content(message, content, ...)')
        print()
        print("New Agent API:")
        print("  No message → ContentExtractionAgent.execute(ExtractionInput(url))")
        print("  No message → SummarizationAgent.execute(SummarizationInput(content))")
        print()
        print("Both APIs coexist - agents use the new *_pure() methods internally")
        print()

        # Next steps
        print("📚 Next Steps:")
        print("  1. See examples/validate_summary_example.py for ValidationAgent usage")
        print("  2. Review docs/multi_agent_architecture.md for full documentation")
        print("  3. Check CLAUDE.md for integration guidance")
        print()

        print("=== Example Complete ===")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("   This example requires proper environment setup")
        print("   See README.md for configuration instructions")


if __name__ == "__main__":
    # Run the example
    asyncio.run(run_agent_pipeline_example())

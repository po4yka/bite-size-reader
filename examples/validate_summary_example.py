"""Example: Using ValidationAgent to validate summary JSON contracts.

The ValidationAgent is fully functional and can be used standalone to validate
any summary JSON against the strict contract requirements.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agents.validation_agent import ValidationAgent, ValidationInput


async def validate_summary_example():
    """Demonstrate ValidationAgent usage with various test cases."""

    # Create validation agent
    validator = ValidationAgent(correlation_id="example-001")

    print("=== Summary Validation Examples ===\n")

    # Example 1: Valid summary
    print("1. Testing VALID summary...")
    valid_summary = {
        "summary_250": "A well-crafted summary that fits within 250 characters limit.",
        "summary_1000": "This is a longer summary that provides more details about the content. "
        * 10,  # Make it longer
        "tldr": "Brief overview of the main points",
        "key_ideas": ["idea1", "idea2", "idea3", "idea4", "idea5"],
        "topic_tags": ["#technology", "#ai", "#summary"],
        "entities": {"people": ["John Doe"], "organizations": ["OpenAI"], "locations": ["SF"]},
        "estimated_reading_time_min": 5,
        "key_stats": [
            {"label": "Market Size", "value": 100.5, "unit": "billion", "source_excerpt": "..."}
        ],
        "answered_questions": ["What is this about?"],
        "readability": {"method": "Flesch-Kincaid", "score": 10.5, "level": "Grade 10"},
        "seo_keywords": ["keyword1", "keyword2"],
    }

    result = await validator.execute(ValidationInput(summary_json=valid_summary))

    if result.success:
        print("✓ Validation PASSED")
        print(f"  Warnings: {len(result.output.validation_warnings)}")
        for warning in result.output.validation_warnings:
            print(f"    - {warning}")
    else:
        print(f"✗ Validation FAILED: {result.error}")

    print("\n" + "-" * 60 + "\n")

    # Example 2: Invalid - character limit exceeded
    print("2. Testing INVALID summary (character limit exceeded)...")
    invalid_char_limit = {
        **valid_summary,
        "summary_250": "a" * 300,  # Exceeds 250 char limit
    }

    result = await validator.execute(ValidationInput(summary_json=invalid_char_limit))

    if result.success:
        print("✓ Validation PASSED")
    else:
        print("✗ Validation FAILED (as expected):")
        print(f"  {result.error}")

    print("\n" + "-" * 60 + "\n")

    # Example 3: Invalid - missing required fields
    print("3. Testing INVALID summary (missing required fields)...")
    missing_fields = {
        "summary_250": "Short summary",
        "summary_1000": "Longer summary",
        # Missing other required fields
    }

    result = await validator.execute(ValidationInput(summary_json=missing_fields))

    if result.success:
        print("✓ Validation PASSED")
    else:
        print("✗ Validation FAILED (as expected):")
        error_lines = result.error.split("\n")
        for line in error_lines[:5]:  # Show first 5 lines
            print(f"  {line}")
        if len(error_lines) > 5:
            print(f"  ... and {len(error_lines) - 5} more errors")

    print("\n" + "-" * 60 + "\n")

    # Example 4: Invalid - topic tags without #
    print("4. Testing INVALID summary (topic tags missing #)...")
    invalid_tags = {
        **valid_summary,
        "topic_tags": ["technology", "ai", "#summary"],  # First two missing #
    }

    result = await validator.execute(ValidationInput(summary_json=invalid_tags))

    if result.success:
        print("✓ Validation PASSED")
    else:
        print("✗ Validation FAILED (as expected):")
        print(f"  {result.error}")

    print("\n" + "-" * 60 + "\n")

    # Example 5: Invalid - key_stats with wrong value type
    print("5. Testing INVALID summary (key_stats with non-numeric value)...")
    invalid_stats = {
        **valid_summary,
        "key_stats": [{"label": "Size", "value": "not-a-number", "unit": "GB"}],
    }

    result = await validator.execute(ValidationInput(summary_json=invalid_stats))

    if result.success:
        print("✓ Validation PASSED")
    else:
        print("✗ Validation FAILED (as expected):")
        print(f"  {result.error}")

    print("\n=== Examples Complete ===\n")


async def validate_from_database_example():
    """Example: Validate a summary from database.

    This shows how to use ValidationAgent with existing summaries
    stored in the database.
    """
    print("=== Database Validation Example ===\n")

    # In a real scenario, you would:
    # 1. Query the database for a summary
    # 2. Parse the json_payload
    # 3. Validate it

    print("To validate a summary from database:")
    print("""
    from app.db.database import Database
    from app.agents.validation_agent import ValidationAgent, ValidationInput
    import json

    db = Database("/data/app.db")

    # Get summary from database
    summary_row = db.get_summary_by_request("correlation-id-here")
    summary_json = json.loads(summary_row["json_payload"])

    # Validate it
    validator = ValidationAgent(correlation_id="db-validation")
    result = await validator.execute(ValidationInput(summary_json=summary_json))

    if not result.success:
        print(f"Summary validation failed: {result.error}")
        # Could trigger re-summarization or manual review
    """)

    print("\n=== Database Example Complete ===\n")


if __name__ == "__main__":
    # Run validation examples
    asyncio.run(validate_summary_example())

    # Show database validation pattern
    asyncio.run(validate_from_database_example())

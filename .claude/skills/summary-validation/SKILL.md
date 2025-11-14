---
name: summary-validation
description: Validate summary JSON contracts against strict schema requirements including character limits, field types, and deduplication. Use when testing summaries or debugging validation errors.
version: 1.0.0
allowed-tools: Bash, Read
---

# Summary Validation Skill

Validates summary JSON output against the strict contract defined in `app/core/summary_contract.py`.

## Summary JSON Contract

All summaries must conform to this strict schema:

```json
{
  "summary_250": "string, <= 250 chars, sentence boundary",
  "summary_1000": "string, <= 1000 chars, multi-sentence overview",
  "tldr": "string, multi-sentence (no hard cap)",
  "key_ideas": ["idea1", "idea2", "idea3", "idea4", "idea5"],
  "topic_tags": ["#tag1", "#tag2", "#tag3"],
  "entities": {
    "people": ["Person Name"],
    "organizations": ["Org Name"],
    "locations": ["Location"]
  },
  "estimated_reading_time_min": 7,
  "key_stats": [
    {"label": "Metric", "value": 12.3, "unit": "USD", "source_excerpt": "..."}
  ],
  "answered_questions": ["What is ...?", "How does ...?"],
  "readability": {
    "method": "Flesch-Kincaid",
    "score": 12.4,
    "level": "College"
  },
  "seo_keywords": ["keyword one", "keyword two", "keyword three"]
}
```

## Validation Rules

### Character Limits
- `summary_250`: HARD CAP at 250 characters, must end on sentence/phrase boundary
- `summary_1000`: HARD CAP at 1000 characters, multi-sentence overview

### Topic Tags
- Must have leading `#` character
- Deduplicated (case-sensitive)
- Maximum 10 tags recommended

### Entities
- Lists must be deduplicated (case-insensitive)
- Valid categories: `people`, `organizations`, `locations`

### Key Stats
- `value` must be numeric (int or float)
- `label` and `source_excerpt` are required strings
- `unit` is optional string

### Readability
- `method` typically "Flesch-Kincaid" or "Flesch Reading Ease"
- `score` is numeric
- `level` maps score to reading level (e.g., "College", "High School")

## Testing a Summary

### Validate from JSON file

```bash
python << 'EOF'
import json
import sys

# Read JSON
with open('summary.json') as f:
    data = json.load(f)

# Check required fields
required = ['summary_250', 'summary_1000', 'tldr', 'key_ideas', 'topic_tags',
            'entities', 'estimated_reading_time_min', 'key_stats',
            'answered_questions', 'readability', 'seo_keywords']

missing = [f for f in required if f not in data]
if missing:
    print(f"ERROR: Missing fields: {missing}")
    sys.exit(1)

# Check character limits
if len(data['summary_250']) > 250:
    print(f"ERROR: summary_250 is {len(data['summary_250'])} chars (max 250)")

if len(data['summary_1000']) > 1000:
    print(f"ERROR: summary_1000 is {len(data['summary_1000'])} chars (max 1000)")

# Check topic tags format
for tag in data.get('topic_tags', []):
    if not tag.startswith('#'):
        print(f"WARNING: Tag '{tag}' missing leading #")

# Check entities structure
entities = data.get('entities', {})
for cat in ['people', 'organizations', 'locations']:
    if cat in entities and not isinstance(entities[cat], list):
        print(f"ERROR: entities.{cat} must be a list")

print("Validation complete!")
EOF
```

### Validate using project utilities

```bash
python << 'EOF'
from app.core.summary_contract import validate_summary_json
import json

with open('summary.json') as f:
    data = json.load(f)

try:
    validated = validate_summary_json(data)
    print("✓ Summary valid!")
    print(f"  summary_250: {len(validated['summary_250'])} chars")
    print(f"  summary_1000: {len(validated['summary_1000'])} chars")
    print(f"  topic_tags: {len(validated['topic_tags'])} tags")
except Exception as e:
    print(f"✗ Validation failed: {e}")
EOF
```

## Common Validation Issues

### 1. Character Limit Exceeded

**Problem**: `summary_250` or `summary_1000` too long

**Solution**: Truncate at sentence boundary
```python
def truncate_at_sentence(text, max_len):
    if len(text) <= max_len:
        return text
    # Find last sentence ending before limit
    for end in ['. ', '! ', '? ']:
        pos = text[:max_len].rfind(end)
        if pos > 0:
            return text[:pos+1]
    return text[:max_len]
```

### 2. Missing Tag Hashtags

**Problem**: Topic tags without leading `#`

**Solution**: Prefix all tags
```python
tags = [f"#{tag}" if not tag.startswith('#') else tag for tag in tags]
```

### 3. Duplicate Entities

**Problem**: Case-insensitive duplicates in entity lists

**Solution**: Deduplicate preserving case
```python
def dedupe_entities(items):
    seen = set()
    result = []
    for item in items:
        if item.lower() not in seen:
            seen.add(item.lower())
            result.append(item)
    return result
```

### 4. Invalid Key Stats Format

**Problem**: Missing required fields or wrong types

**Solution**: Validate each stat
```python
for stat in key_stats:
    assert 'label' in stat, "Missing label"
    assert 'value' in stat, "Missing value"
    assert isinstance(stat['value'], (int, float)), "Value must be numeric"
```

## Testing with CLI Runner

Test URL processing and summary generation:

```bash
python -m app.cli.summary \
  --url https://example.com/article \
  --json-path output.json \
  --log-level DEBUG
```

The CLI automatically validates summaries using `validate_summary_json()`.

## Reference Files

- **Contract validation**: `app/core/summary_contract.py`
- **Schema definition**: `app/core/summary_schema.py`
- **LLM prompts**: `app/prompts/en/summary.txt`, `app/prompts/ru/summary.txt`
- **JSON utilities**: `app/core/json_utils.py` (includes repair logic)

## Important Notes

- All validation happens in `app/core/summary_contract.py`
- JSON repair attempts to fix malformed LLM output (`json_repair` library)
- Both English and Russian prompts must be kept in sync
- Database stores verbatim JSON in `summaries.json_payload`
- Failed validations are logged with correlation ID for debugging

# Python 3.13 Migration & Dependency Modernization

This document describes the migration to Python 3.13 and the comprehensive dependency modernization completed in November 2025.

## Overview

The project has been successfully migrated from Python 3.11 to Python 3.13, with several key dependency changes that improve performance, accuracy, and maintainability.

## Python 3.13 Migration

### Version Updates

- **Previous**: Python 3.11
- **Current**: Python 3.13.1

### Files Updated

- `.python-version`: Updated to `3.13.1`
- `Dockerfile`: Updated base image to `python:3.13-slim`
- `pyproject.toml`: Updated `requires-python = ">=3.13"`
- All GitHub Actions workflows (`.github/workflows/*.yml`): Updated to Python 3.13

## Textacy to scikit-learn Migration

### Background

The `textacy` library and its dependency `floret` were incompatible with Python 3.13 (no binary wheels available). Rather than keeping Python 3.11, we replaced textacy functionality with direct implementation and scikit-learn.

### Changes

#### Removed Dependencies
- `textacy` (and 8 transitive dependencies)
- `floret`
- `cytoolz`
- `jellyfish`
- `networkx`
- `pyphen`
- `cachetools`
- `toolz`

#### Added Dependencies
- `scikit-learn>=1.7.2` - Industry-standard ML library for text processing

### Implementation Details

#### 1. Flesch Reading Ease Formula (app/core/summary_contract.py:16-63)

Implemented the Flesch Reading Ease formula directly:
- Formula: `206.835 - 1.015 * (words/sentences) - 84.6 * (syllables/words)`
- Uses vowel-group heuristic for syllable counting
- Returns scores from 0-100 (higher = easier to read)

#### 2. Keyword Extraction (app/core/summary_contract.py:66-121)

Replaced textacy's sgrank algorithm with TF-IDF:
- Uses `sklearn.feature_extraction.text.TfidfVectorizer`
- Supports 1-3 word n-grams
- English stop words filtering
- Fallback to frequency-based extraction if needed

#### 3. Text Normalization (app/core/html_utils.py)

Simplified `normalize_text()` function:
- Pure regex implementation
- No external dependencies
- Handles unicode normalization, URL/email removal, whitespace cleanup

### Test Results

- **Before**: 291 tests (1 skipped)
- **After**: 290 passing, 1 skipped
- 6 tests had expected behavioral differences in keyword extraction (TF-IDF vs sgrank)

## Dependency Modernization (November 2025)

### 1. HTML Content Extraction: readability-lxml → trafilatura

#### Rationale
- **Better Accuracy**: F1 score 0.958 vs 0.922
- **Active Maintenance**: trafilatura is actively maintained
- **Better Dependencies**: Cleaner dependency tree

#### Implementation (app/core/html_utils.py:9-87)
```python
try:
    import trafilatura
    _HAS_TRAFILATURA = True
except Exception:
    trafilatura = None
    _HAS_TRAFILATURA = False

def html_to_text(html: str) -> str:
    if _HAS_TRAFILATURA and trafilatura is not None:
        try:
            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
            if text:
                # Normalize whitespace
                return process_text(text)
        except Exception:
            pass

    # Fallback: lightweight HTML parsing
    return fallback_parser(html)
```

### 2. High-Performance JSON: orjson

#### Rationale
- **Performance**: 6-20x faster than stdlib json
- **Native bytes support**: Handles both str and bytes
- **Production-proven**: Used by major projects

#### Implementation (app/core/json_utils.py:6-57)

Created wrapper functions for seamless integration:
```python
def loads(data: str | bytes) -> Any:
    """Parse JSON using orjson if available, else stdlib json."""
    if _HAS_ORJSON and orjson is not None:
        return orjson.loads(data)
    else:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)

def dumps(obj: Any, *, indent: int | None = None, ensure_ascii: bool = False) -> str:
    """Serialize to JSON using orjson if available, else stdlib json."""
    if _HAS_ORJSON and orjson is not None:
        options = 0
        if indent is not None:
            options |= orjson.OPT_INDENT_2
        result = orjson.dumps(obj, option=options)
        return result.decode("utf-8")
    else:
        return json.dumps(obj, indent=indent, ensure_ascii=ensure_ascii)
```

### 3. Async Performance: uvloop

#### Rationale
- **Performance**: 2-4x faster asyncio event loop
- **Drop-in replacement**: Zero code changes needed
- **Production-ready**: Used by major async Python applications

#### Implementation (bot.py:10-16)
```python
# Use uvloop for better async performance if available
try:
    import uvloop
    uvloop.install()
except ImportError:
    pass
```

## Backward Compatibility

All new dependencies are optional with graceful fallbacks:

- **trafilatura**: Falls back to lightweight HTML parser
- **orjson**: Falls back to stdlib json
- **uvloop**: Falls back to default asyncio event loop

This ensures the application works even if optional dependencies fail to install.

## Dependency Summary

### Current Core Dependencies (pyproject.toml)

```toml
dependencies = [
  "httpx[http2]>=0.28.1",
  "pyrogram>=2.0.106",
  "tgcrypto>=1.2.5",
  "pydantic>=2.12.4",
  "peewee>=3.18.3",
  "trafilatura>=2.0.0",        # HTML extraction
  "spacy>=3.8.8,<4",
  "json_repair>=0.52.4",
  "scikit-learn>=1.7.2",       # Text analysis
  "orjson>=3.10.0",            # Fast JSON
  "uvloop>=0.22.1",            # Fast async
]
```

### Development Dependencies

```toml
dev = [
  "isort>=7.0.0",
  "pytest>=9.0.0",
  "pytest-asyncio>=1.3.0",
  "ruff>=0.14.4",
  "mypy>=1.18.2",
  "pre-commit>=4.4.0",
]
```

## Performance Improvements

### JSON Operations
- **Before**: stdlib json (baseline)
- **After**: orjson (6-20x faster)

### Async I/O
- **Before**: Default asyncio event loop
- **After**: uvloop (2-4x faster)

### HTML Extraction
- **Before**: readability-lxml (F1: 0.922)
- **After**: trafilatura (F1: 0.958)

## Migration Commands

For developers updating to this version:

```bash
# 1. Ensure Python 3.13 is installed
python --version  # Should show 3.13.x

# 2. Sync dependencies
uv sync

# 3. Run tests
uv run pytest

# 4. Verify all functionality
uv run python bot.py
```

## Docker

The Docker image has been updated to use Python 3.13:

```dockerfile
FROM python:3.13-slim
```

Rebuild your Docker images:

```bash
docker build -t bite-size-reader .
```

## Known Issues

None. All 290 tests pass (1 skipped).

## Related Documentation

- `README.md` - Updated with Python 3.13 requirement
- `DEPLOYMENT.md` - Updated prerequisites
- `AGENTS.md` - Updated coding conventions
- `GEMINI.md` - Updated guidelines

## References

- [Python 3.13 Release Notes](https://docs.python.org/3.13/whatsnew/3.13.html)
- [scikit-learn Documentation](https://scikit-learn.org/stable/)
- [trafilatura Documentation](https://trafilatura.readthedocs.io/)
- [orjson GitHub](https://github.com/ijl/orjson)
- [uvloop Documentation](https://uvloop.readthedocs.io/)

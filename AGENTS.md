# AGENTS.md for Python PyroTGFork Firecrawl OpenRouter Summary Service

## Overview

This repository contains a Python service using PyroTGFork (a Telegram MTProto API framework fork), Firecrawl, and OpenRouter to provide article and forwarded message summarization. The service listens for either:

- A URL to an article, which Firecrawl parses and OpenRouter (via ChatGPT) summarizes.
- A forwarded message from a Telegram channel, which is summarized via OpenRouter.

The summary is sent back to the requesting client through the Telegram bot. All parsed and summarized data is saved in a SQLite database for persistence and auditing.

The entire service is containerized using Docker for easy deployment and environment consistency.

This repository is private and intended solely for the service owner's use.

---

## Coding and Style Conventions

- Python 3.11+ with asyncio and async/await syntax.
- Follow PEP8 style guidelines for code readability.
- Use type hints and docstrings for all public functions and classes.
- Separation of concerns: Telegram bot client, Firecrawl parsing, OpenRouter calls, and database operations should be modularized.
- Error handling and logging must be robust, with retries for transient OpenRouter or Firecrawl failures.

---

## Deployment & Infrastructure

- The code is wrapped inside a Docker container defined by `Dockerfile` at the root.
- Use environment variables for all secrets such as OpenRouter API keys.
- SQLite database file persisted inside a Docker volume or mounted path.
- GitHub repository hosts source code with automated Docker build workflow (CI/CD) if needed.

---

## File/Folder Structure Expectations

- `bot.py` — Telegram client service using PyroTGFork.
- `firecrawl_parser.py` — Module responsible for article content extraction.
- `openrouter_client.py` — Module handling calls to OpenRouter's ChatGPT API.
- `database.py` — SQLite access and query module.
- `Dockerfile` — Container configuration.
- `README.md` — Usage instructions.
- `SPEC.md` - Project specification.
- `pyproject.toml` — Dependency management source of truth; `requirements*.txt` are compiled lock files (uv/pip-tools).

---

## Permissions and Use Cases

- This bot and service are only for personal use.
- No external users allowed.
- No public API exposure.
- Summaries and stored data are private.
- Handle user input validation carefully to avoid malicious content processing.

---

## Testing

- Write unit tests for Firecrawl parsing and OpenRouter interface.
- Integration tests for Telegram bot message flows.
- Tests should mock external API calls to avoid over-usage quota risks.

---

## Code Quality and Formatting

- **ALWAYS run linters and autoformatting after every code change** before completing the task.
- Use the following commands in sequence after making any code modifications:
  1. `ruff check . --fix` - Run Ruff linter with auto-fixes
  2. `ruff format .` - Format code with Ruff formatter
  3. `mypy .` - Run type checking with MyPy
- Ensure all linting errors are resolved and code is properly formatted before marking tasks as complete.
- If any linting errors cannot be automatically fixed, address them manually and re-run the linters.

# GEMINI.md for Python PyroTGFork Firecrawl OpenRouter Summary Service

## Overview

This repository contains a Python service using PyroTGFork (a Telegram MTProto API framework fork), Firecrawl, and OpenRouter to provide article and forwarded message summarization. The service listens for either:

- A URL to an article, which Firecrawl parses and OpenRouter (via ChatGPT) summarizes.
- A forwarded message from a Telegram channel, which is summarized via OpenRouter.

The summary is sent back to the requesting client through the Telegram bot. All parsed and summarized data is saved in a SQLite database for persistence and auditing.

The entire service is containerized using Docker for easy deployment and environment consistency.

This repository is private and intended solely for the service owner's use.

---

## Python Service Coding Guidelines

- Use Python 3.13+ with `async`/`await` syntax for all I/O and network calls.
- Follow PEP8 style conventions strictly.
- Use type hints and docstrings on all public functions/classes.
- Modularize concerns: separate bot client, parser, API client, and DB layers. The business logic should be cleanly separated from request/response handling.
- Gracefully handle errors with retries for transient API failures (e.g., Firecrawl, OpenRouter).
- Validate and sanitize all user inputs before processing.
- Log important events, including API call success/failure.

---

## File and Module Organization

The project follows a structured layout to separate concerns:

- `bot.py`: The main entry point for starting the service.
- `app/`: The main application package.
  - `app/adapters/telegram_bot.py`: Handles the Telegram MTProto client using PyroTGFork.
  - `app/adapters/firecrawl_parser.py`: Encapsulates article parsing logic.
  - `app/adapters/openrouter_client.py`: Handles OpenRouter ChatGPT API interactions.
  - `app/db/database.py`: Manages SQLite database access and queries.
  - `app/core/`: Contains core business logic, data models, and utilities.
  - `app/prompts/`: Stores prompt templates.
- `tests/`: Contains unit and integration tests.
- `Dockerfile`: Defines the Docker container for the service.
- `docker-compose.yml`: For local development and orchestration.
- `pyproject.toml`: The source of truth for Python dependencies.
- `requirements.txt` & `requirements-dev.txt`: Locked dependency files generated from `pyproject.toml`.
- `README.md`: Usage instructions.
- `SPEC.md`: Project specification.

---

## Python Package Management with uv

Use `uv` exclusively for Python package management in this project.

### Package Management Commands

- All Python dependencies **must be installed, synchronized, and locked** using `uv`.
- **Never use** `pip`, `pip-tools`, `poetry`, or `conda` directly for dependency management.

Use these commands:
- Install dependencies: `uv add <package>`
- Remove dependencies: `uv remove <package>`
- Sync dependencies: `uv sync`

### Running Python Code

- Run a Python script: `uv run <script-name>.py`
- Run Python tools (e.g., Pytest, Ruff): `uv run pytest` or `uv run ruff`
- Launch a Python REPL: `uv run python`

---

## Docker Container Guidelines

- Use official Python base images with appropriate tags (e.g., `python:3.13-slim`).
- Minimize image layer size by cleaning cache and unnecessary files.
- Use multi-stage builds if needed to separate build/dependency and runtime layers.
- Pass secrets like API keys as environment variables, never baked into the image.
- Expose only necessary ports and restrict to localhost if possible.
- Use persistent volumes or bind mounts for SQLite database files.
- Document Docker build and run instructions clearly.
- Keep the `Dockerfile` simple and readable.

---

## Security and Permissions

- **Personal Use Only**: This bot and service are for private use. No external users are allowed, and there is no public API exposure.
- **Data Privacy**: Summaries and stored data are private.
- **Secrets Management**: Do not hardcode API keys, tokens, or other secrets in source code. Store them in environment variables or a secure vault.
- **Input Validation**: Validate any URLs or message content from users to prevent injection attacks.
- **Dependency Management**: Use the latest dependency versions with security patches. Regularly review dependencies for vulnerabilities.
- **Logging**: Avoid logging sensitive data; redact if necessary.

---

## Testing

- Write unit tests for Firecrawl parsing and the OpenRouter interface.
- Write integration tests for Telegram bot message flows.
- Tests should mock external API calls to avoid consuming API quotas.

---

## Code Quality and Formatting

- **ALWAYS run linters and autoformatting after every code change** before completing the task.
- Use the following commands in sequence after making any code modifications:
  1. `ruff check . --fix` - Run Ruff linter with auto-fixes
  2. `ruff format .` - Format code with Ruff formatter
  3. `mypy .` - Run type checking with MyPy
- Ensure all linting errors are resolved and code is properly formatted before marking tasks as complete.
- If any linting errors cannot be automatically fixed, address them manually and re-run the linters.

---

## GPT-5 Optimization Status

GPT-5 has been optimized to minimize restrictions and use truncation only as a last resort:

### Optimizations Applied

1. **Increased Token Budget**: GPT-5 now gets up to 32k tokens (vs 8k for other models)
2. **Extended Thinking Time**: GPT-5 uses "thinking=extended" parameter for better reasoning
3. **Optimized Parameters**: Temperature 0.4, top_p 0.9 for focused but diverse responses
4. **Provider Preference**: OpenAI is prioritized for GPT-5 calls via `OPENROUTER_PROVIDER_ORDER=openai`
5. **Permissive Truncation Logic**: GPT-5 gets multiple retry attempts before falling back to Gemini

### Fallback Behavior

- **First attempt**: GPT-5 with extended thinking
- **Second attempt**: GPT-5 with adjusted parameters (if truncated)
- **Third attempt**: GPT-5 with minimal restrictions (if still truncated)
- **Final fallback**: Switch to Gemini 2.5 Pro (only as last resort)

This ensures GPT-5 can provide comprehensive responses while maintaining reliability through intelligent fallback.

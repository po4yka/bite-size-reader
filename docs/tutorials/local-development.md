# Local Development Tutorial

Set up a local development environment for Bite-Size Reader.

**Time**: ~20 minutes
**Difficulty**: Intermediate
**Prerequisites**: Python 3.13+, git

---

## What You'll Learn

By the end of this tutorial, you'll have:

- ✅ Local development environment with Python venv
- ✅ All dependencies installed (including dev tools)
- ✅ Pre-commit hooks configured
- ✅ Tests running successfully
- ✅ CLI summary runner working
- ✅ Ready to make your first code change

---

## Step 1: Clone Repository (1 minute)

```bash
# Clone the repository
git clone https://github.com/po4yka/bite-size-reader.git
cd bite-size-reader

# Verify Python version (3.13+ required)
python3 --version
# Should output: Python 3.13.x or higher
```

**If Python 3.13 not installed**:

```bash
# Using pyenv (recommended)
pyenv install 3.13.0
pyenv local 3.13.0

# Verify
python3 --version
```

---

## Step 2: Create Virtual Environment (2 minutes)

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Your shell prompt should now show (.venv)

# Upgrade pip
pip install --upgrade pip
```

**macOS/Linux alternative**:

```bash
# Use the provided script
make venv
source .venv/bin/activate
```

**Windows (PowerShell)**:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

---

## Step 3: Install Dependencies (3 minutes)

```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# Verify installation
pip list | grep -E "pyrogram|firecrawl|ruff|pytest"

# Should see:
# firecrawl          x.x.x
# pyrogram           x.x.x
# pytest             x.x.x
# ruff               x.x.x
```

**Common Issues**:

- **ARM Mac (M1/M2) compilation errors**: Install build tools

  ```bash
  brew install cmake pkg-config
  pip install -r requirements.txt
  ```

- **Linux missing system libraries**:

  ```bash
  sudo apt-get install build-essential python3-dev
  pip install -r requirements.txt
  ```

---

## Step 4: Configure Environment (2 minutes)

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your API keys
nano .env  # or vim, code, etc.
```

**Minimal configuration for local development**:

```bash
# Telegram (required)
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
ALLOWED_USER_IDS=your_user_id

# Content extraction (required)
FIRECRAWL_API_KEY=your_firecrawl_key

# LLM (required)
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=deepseek/deepseek-v3.2

# Database (local dev)
DB_PATH=./data/app.db

# Logging
LOG_LEVEL=DEBUG
```

**Get API keys**: See [Quickstart Tutorial § Get API Keys](quickstart.md#step-1-get-api-keys-3-minutes)

---

## Step 5: Initialize Database (1 minute)

```bash
# Create data directory
mkdir -p data

# Run database migrations
python -m app.cli.migrate_db

# Verify database created
ls -lh data/
# Should see: app.db (~10KB)

# Check database schema
sqlite3 data/app.db ".schema" | head -20
```

---

## Step 6: Install Pre-commit Hooks (2 minutes)

Pre-commit hooks ensure code quality before commits.

```bash
# Install pre-commit
pip install pre-commit

# Install git hooks
pre-commit install

# Test hooks manually
pre-commit run --all-files

# Should run: ruff (check + format), isort, mypy, trailing-whitespace, etc.
```

**What pre-commit does**:

- **Ruff**: Auto-fixes code style issues
- **isort**: Sorts imports (black-compatible)
- **mypy**: Type checking
- **Standard hooks**: Trailing whitespace, YAML syntax, merge conflicts

**First run** will download hook environments (~2 minutes).

---

## Step 7: Run Tests (3 minutes)

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_url_utils.py

# Run tests matching pattern
pytest -k "test_normalize_url"

# Run with verbose output
pytest -v

# Run fast (skip slow tests)
pytest -m "not slow"
```

**Expected output**:

```
============================= test session starts ==============================
collected 150 items

tests/test_access_control.py ........                                    [  5%]
tests/test_json_repair.py .........                                      [ 11%]
tests/test_url_utils.py .................                                [ 22%]
...
tests/test_summary_contract.py ......................                    [100%]

============================== 150 passed in 12.34s ============================
```

**Note**: Some tests may fail due to missing `adaptive_timeout` field in test config. These are pre-existing failures documented in `MEMORY.md`.

---

## Step 8: Use CLI Summary Runner (2 minutes)

Test URL processing without running the full bot.

```bash
# Summarize a URL
python -m app.cli.summary --url https://example.com/article

# Expected output:
# INFO: Extracting content from https://example.com/article
# INFO: Generating summary...
# INFO: Summary generated successfully
# [JSON output printed to console]

# Save summary to file
python -m app.cli.summary --url https://example.com/article --json-path summary.json

# Process multiple URLs
python -m app.cli.summary --url https://example.com/article1 --url https://example.com/article2 --accept-multiple

# Verbose logging
python -m app.cli.summary --url https://example.com/article --log-level DEBUG

# Mimic Telegram command
python -m app.cli.summary "/summarize https://example.com/article"
```

**CLI advantages**:

- Fast iteration (no bot startup)
- No Telegram credentials needed (CLI generates stubs)
- Easy debugging (verbose logs, JSON output)
- Scriptable (batch processing)

---

## Step 9: Make Your First Code Change (5 minutes)

Let's make a small change to verify your setup works end-to-end.

### 9.1 Create a Feature Branch

```bash
git checkout -b feature/test-change
```

### 9.2 Make a Small Change

Edit `app/core/url_utils.py` and add a comment:

```python
def normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication.

    # Test change: This function is awesome!

    Args:
        url: Raw URL from user
    ...
```

### 9.3 Run Pre-commit Checks

```bash
# Pre-commit runs automatically on commit, but you can test manually
pre-commit run --all-files

# Should pass (ruff, isort, mypy all happy)
```

### 9.4 Run Tests

```bash
# Verify your change didn't break anything
pytest tests/test_url_utils.py

# All tests should still pass
```

### 9.5 Commit Your Change

```bash
git add app/core/url_utils.py
git commit -m "docs: add comment to normalize_url function"

# Pre-commit hooks run automatically
# If they modify files, stage changes and commit again
```

---

## Step 10: Run the Bot Locally (Optional)

If you want to test the full bot:

```bash
# Ensure .env has all required variables
# Then run the bot
python bot.py

# Expected output:
# INFO: Bot started successfully
# INFO: Listening for messages...

# Test by messaging your bot on Telegram
# Send a URL to get a summary
```

**Stop the bot**: Press `Ctrl+C`

---

## Development Workflow

### Daily Workflow

```bash
# 1. Activate venv
source .venv/bin/activate

# 2. Pull latest changes
git pull origin main

# 3. Install any new dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 4. Create feature branch
git checkout -b feature/my-feature

# 5. Make changes
# ... edit code ...

# 6. Run tests
pytest

# 7. Commit (pre-commit runs automatically)
git commit -m "feat: implement my feature"

# 8. Push and create PR
git push origin feature/my-feature
```

### Code Quality Commands

```bash
# Format code (ruff + isort)
make format

# Lint code
make lint

# Type check
make type

# Run all quality checks
make format lint type
```

### Debugging Tips

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Enable API payload logging (Authorization redacted)
export DEBUG_PAYLOADS=1

# Run CLI with verbose output
python -m app.cli.summary --url https://example.com --log-level DEBUG

# Inspect database
sqlite3 data/app.db

# Check specific request by correlation ID
sqlite3 data/app.db "SELECT * FROM requests WHERE id = '<correlation_id>';"
```

---

## Common Development Tasks

### Adding a New Dependency

```bash
# 1. Add to pyproject.toml [project.dependencies]
# 2. Lock dependencies
make lock-uv  # or make lock-piptools

# 3. Install
pip install -r requirements.txt

# 4. Commit both pyproject.toml and requirements.txt
git add pyproject.toml requirements.txt
git commit -m "deps: add new-package"
```

### Running Database Migrations

```bash
# Apply migrations
python -m app.cli.migrate_db

# Rebuild indexes
python -m app.cli.rebuild_indexes

# Check database integrity
sqlite3 data/app.db "PRAGMA integrity_check;"
```

### Testing Mobile API

```bash
# Start API server
uvicorn app.api.main:app --reload

# In another terminal, test endpoints
curl http://localhost:8000/health

# Or use the OpenAPI docs
open http://localhost:8000/docs
```

### Testing MCP Server

```bash
# Start MCP server
python -m app.mcp.server

# Test MCP tools directly
python -c "
from app.mcp.server import MCPServer
server = MCPServer()
result = server.search_summaries('python')
print(result)
"
```

---

## IDE Setup

### VS Code

Recommended extensions:

- **Python** (ms-python.python)
- **Pylance** (ms-python.vscode-pylance)
- **Ruff** (charliermarsh.ruff)
- **isort** (ms-python.isort)

`.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "none",
  "[python]": {
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll": true,
      "source.organizeImports": true
    },
    "editor.defaultFormatter": "charliermarsh.ruff"
  }
}
```

### PyCharm

1. **Set Interpreter**: Settings → Project → Python Interpreter → Add → Virtualenv → Existing → `.venv/bin/python`
2. **Enable Ruff**: Settings → Tools → External Tools → Add Ruff
3. **Configure pytest**: Settings → Tools → Python Integrated Tools → Testing → pytest

---

## Troubleshooting

### Virtual Environment Not Activating

```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat

# If issues persist, recreate venv
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

### Pre-commit Hooks Failing

```bash
# Update hooks
pre-commit autoupdate

# Clear cache and reinstall
pre-commit clean
pre-commit install

# Skip hooks temporarily (NOT recommended)
git commit --no-verify
```

### Tests Failing

```bash
# Check if failures are pre-existing
git stash
pytest  # Run tests on clean main branch
git stash pop

# If failures match, they're pre-existing (see MEMORY.md)
# If new failures, debug with:
pytest -v tests/test_failing.py
pytest --pdb  # Drop into debugger on failure
```

### Import Errors

```bash
# Ensure dependencies installed
pip install -r requirements.txt -r requirements-dev.txt

# Check PYTHONPATH
echo $PYTHONPATH

# Add project root to PYTHONPATH if needed
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

---

## Next Steps

**You're ready to develop!** 🎉

**Explore the codebase**:

- Read [CLAUDE.md](../../CLAUDE.md) - Comprehensive codebase guide
- Read [SPEC.md](../SPEC.md) - Technical specification
- Read [ADRs](../adr/README.md) - Architectural decisions

**Make contributions**:

- Fix bugs or add features
- Improve documentation
- Add tests

**Get help**:

- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - Debugging guide
- [FAQ](../FAQ.md) - Common questions
- [GitHub Issues](https://github.com/po4yka/bite-size-reader/issues) - Ask questions

---

**Tutorial Complete!** 🎓

You now have a fully functional local development environment. Happy coding!

---

**Last Updated**: 2026-02-09

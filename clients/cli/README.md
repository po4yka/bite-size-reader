# bsr-cli

Command-line client for [Bite-Size Reader](https://github.com/po4yka/bite-size-reader) -- save, search, and organize web content from your terminal.

## Installation

```bash
# From PyPI (when published)
pip install bsr-cli

# Or with pipx for isolated install
pipx install bsr-cli

# Development install
cd cli && pip install -e .
```

Requires Python 3.11+.

## Quick Start

```bash
# 1. Point at your BSR server
bsr config --url https://bsr.example.com

# 2. Authenticate
bsr login --server https://bsr.example.com --user-id 123456 --client-id my-cli --secret <secret>

# 3. Submit a mixed-source aggregation bundle
bsr aggregate https://x.com/example/status/1 https://www.youtube.com/watch?v=dQw4w9WgXcQ

# 4. Poll the aggregation session
bsr aggregation get 42

# 5. Search saved summaries
bsr search "async python" --lang en
```

## Command Reference

### Global Options

| Flag | Env Var | Description |
|------|---------|-------------|
| `--json` | | Output raw JSON (for scripting) |
| `--server URL` | `BSR_SERVER_URL` | Override server URL |
| `--version` | | Show version |
| `--help` | | Show help |

### `bsr config`

Configure the BSR server connection.

```bash
bsr config --url https://bsr.example.com
```

### `bsr login`

Authenticate with the BSR server using a secret key.

```bash
bsr login \
  --server https://bsr.example.com \
  --user-id 123456 \
  --client-id my-cli \
  --secret <secret>
```

All options are prompted interactively if omitted. The secret is hidden during input.

### `bsr whoami`

Show the currently authenticated user.

```bash
bsr whoami
bsr --json whoami    # JSON output
```

### `bsr save URL`

Save a URL and optionally trigger summarization.

```bash
bsr save https://example.com/article
bsr save https://example.com/article --title "Custom Title" --tag python --tag web
bsr save https://example.com/article --no-summarize
bsr save https://example.com/article --note "Key paragraph here"
```

| Option | Short | Description |
|--------|-------|-------------|
| `--title` | `-T` | Custom title |
| `--tag` | `-t` | Tag name (repeatable) |
| `--summarize/--no-summarize` | | Trigger summarization (default: on) |
| `--note` | | Note or selected text to attach |

### `bsr list`

List saved summaries.

```bash
bsr list
bsr list --limit 50 --offset 20
bsr list --unread
bsr list --favorites
bsr list --tag python
```

| Option | Short | Description |
|--------|-------|-------------|
| `--limit` | `-n` | Results per page (default: 20) |
| `--offset` | | Pagination offset |
| `--unread` | | Show only unread |
| `--favorites` | | Show only favorites |
| `--tag` | `-t` | Filter by tag name |

### `bsr get ID`

Get summary details by ID.

```bash
bsr get 42
bsr get 42 --content     # Include full article content
bsr --json get 42        # JSON output
```

### `bsr search QUERY`

Search summaries by text query.

```bash
bsr search "machine learning"
bsr search "rust async" --limit 5
bsr search "web dev" --tag tutorial --lang en
bsr search "api design" --domain blog.example.com
```

| Option | Short | Description |
|--------|-------|-------------|
| `--limit` | `-n` | Max results (default: 20) |
| `--tag` | `-t` | Filter by tag (repeatable) |
| `--lang` | | Filter by language (`en`, `ru`) |
| `--domain` | `-d` | Filter by domain (repeatable) |

### Aggregation Bundles

Mixed-source aggregation uses the public `/v1/aggregations` API. The CLI submits the bundle and prints the latest server-side session snapshot immediately. It does not keep polling until completion by default.

### `bsr aggregate [URL ...]`

Submit one or more URLs as a single aggregation bundle.

```bash
bsr aggregate https://x.com/example/status/1 https://youtu.be/dQw4w9WgXcQ
bsr aggregate --file sources.txt --lang en
bsr aggregate --hint x_post --hint youtube_video \
  https://x.com/example/status/1 \
  https://youtu.be/dQw4w9WgXcQ
bsr --json aggregate --file sources.txt | jq '.session.sessionId'
```

| Option | Description |
|--------|-------------|
| `URL ...` | Positional URLs to include in the bundle |
| `--file` | Read additional URLs from a file, one per line |
| `--lang` | Preferred language: `auto`, `en`, or `ru` |
| `--hint` | Source-kind hint for the matching URL position |
| `--json` | Emit the raw API payload for scripting |

Supported `--hint` values:

- `x_post`
- `x_article`
- `threads_post`
- `instagram_post`
- `instagram_carousel`
- `instagram_reel`
- `web_article`
- `telegram_post`
- `youtube_video`

### `bsr aggregation get ID`

Fetch one aggregation session by ID.

```bash
bsr aggregation get 42
bsr --json aggregation get 42 | jq '.session.progress'
```

### `bsr aggregation list`

List recent aggregation sessions for the authenticated user.

```bash
bsr aggregation list
bsr aggregation list --limit 10 --offset 10
bsr --json aggregation list --limit 5 | jq '.sessions[] | {id, status}'
```

This is the recommended polling flow for long-running bundles:

1. Run `bsr aggregate ...`
2. Note `session.sessionId`
3. Poll with `bsr aggregation get <id>` until the status is `completed`, `partial`, or `failed`

The most useful session fields are:

- `status`
- `progress.completionPercent`
- `successfulCount`
- `failedCount`
- `failure`
- `queuedAt`, `startedAt`, `completedAt`, `lastProgressAt`

### `bsr delete ID`

Delete a summary by ID.

```bash
bsr delete 42
```

### `bsr favorite ID`

Toggle favorite status on a summary.

```bash
bsr favorite 42
```

### `bsr read ID`

Mark a summary as read.

```bash
bsr read 42
```

### `bsr tags`

Manage tags. Running `bsr tags` without a subcommand lists all tags.

```bash
bsr tags                           # List all tags
bsr tags create "machine-learning" --color "#3B82F6"
bsr tags delete 5                  # Prompts for confirmation
bsr tags attach 42 "python"       # Attach tag to summary 42
bsr tags detach 42 5              # Detach tag ID 5 from summary 42
```

### `bsr collections`

Manage collections. Running `bsr collections` without a subcommand lists all collections.

```bash
bsr collections                            # List all
bsr collections create "Reading List" -d "Articles to read this week"
bsr collections delete 3                   # Prompts for confirmation
bsr collections add 3 42                   # Add summary 42 to collection 3
```

### `bsr export`

Export all data.

```bash
bsr export                          # JSON to stdout
bsr export --format csv -o data.csv
bsr export --format html -o export.html
```

| Option | Short | Description |
|--------|-------|-------------|
| `--format` | | `json`, `csv`, or `html` (default: `json`) |
| `--output` | `-o` | Output file (default: stdout) |

### `bsr import FILE`

Import bookmarks from a file.

```bash
bsr import bookmarks.html
bsr import bookmarks.json --summarize   # Trigger summarization for imports
```

### `bsr admin`

Admin-only operations.

```bash
bsr admin users     # List users with stats
bsr admin health    # Content health report
bsr admin jobs      # Background job status
```

## Configuration

Config is stored at `$XDG_CONFIG_HOME/bsr/config.toml` (defaults to `~/.config/bsr/config.toml`). The file is created with `0600` permissions (owner read/write only).

```toml
[server]
url = "https://bsr.example.com"

[auth]
client_id = "my-cli"
user_id = 123456
access_token = "..."
refresh_token = "..."
token_expires_at = "2025-12-31T00:00:00+00:00"
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `BSR_SERVER_URL` | Override server URL (same as `--server` flag) |
| `XDG_CONFIG_HOME` | Override config directory base |

## Authentication

BSR CLI uses a secret-key authentication flow:

1. A client secret is generated server-side (via Telegram bot or admin API)
2. `bsr login` exchanges the secret for JWT access and refresh tokens
3. Tokens are stored in the config file
4. The CLI automatically refreshes the access token when it's within 5 minutes of expiry

Important auth semantics:

- Client secrets are shown in plaintext only when they are created or rotated.
- A rotated or revoked secret cannot be used for future `bsr login` calls.
- If access-token refresh fails because the refresh session was revoked or expired, run `bsr login` again with an active secret.

For a full onboarding flow, including hosted MCP usage, see [External Access Quickstart](../../docs/tutorials/external-access-quickstart.md).

## JSON Output

Pass `--json` before any command to get raw JSON output, suitable for piping to `jq` or scripting:

```bash
bsr --json list | jq '.[].title'
bsr --json search "python" | jq '.results[] | {id, title}'
bsr --json get 42 | jq '.tldr'
```

## Examples

### Save and tag an article

```bash
bsr save https://blog.example.com/post -t rust -t async -T "Async Rust Guide"
```

### Browse unread articles

```bash
bsr list --unread --limit 5
bsr get 42
bsr read 42
```

### Search and export results

```bash
bsr --json search "kubernetes" --domain blog.example.com | jq '.results[].url'
```

### Build a reading list

```bash
bsr collections create "Weekend Reads"
bsr collections add 1 42
bsr collections add 1 43
bsr collections
```

### Backup your data

```bash
bsr export --format json -o backup.json
```

# ratatoskr-cli

Command-line client for [Ratatoskr](https://github.com/po4yka/ratatoskr) -- save, search, and organize web content from your terminal.

## Installation

```bash
# From PyPI (when published)
pip install ratatoskr-cli

# Or with pipx for isolated install
pipx install ratatoskr-cli

# Development install
cd cli && pip install -e .
```

Requires Python 3.11+.

## Quick Start

```bash
# 1. Point at your Ratatoskr server
ratatoskr config --url https://ratatoskr.example.com

# 2. Authenticate
ratatoskr login --server https://ratatoskr.example.com --user-id 123456 --client-id my-cli --secret <secret>

# 3. Submit a mixed-source aggregation bundle
ratatoskr aggregate https://x.com/example/status/1 https://www.youtube.com/watch?v=dQw4w9WgXcQ

# 4. Reopen the persisted aggregation session later
ratatoskr aggregation get 42

# 5. Search saved summaries
ratatoskr search "async python" --lang en
```

## Command Reference

### Global Options

| Flag | Env Var | Description |
|------|---------|-------------|
| `--json` | | Output raw JSON (for scripting) |
| `--server URL` | `RATATOSKR_SERVER_URL` | Override server URL |
| `--version` | | Show version |
| `--help` | | Show help |

### `ratatoskr config`

Configure the Ratatoskr server connection.

```bash
ratatoskr config --url https://ratatoskr.example.com
```

### `ratatoskr login`

Authenticate with the Ratatoskr server using a secret key.

```bash
ratatoskr login \
  --server https://ratatoskr.example.com \
  --user-id 123456 \
  --client-id my-cli \
  --secret <secret>
```

All options are prompted interactively if omitted. The secret is hidden during input.

### `ratatoskr whoami`

Show the currently authenticated user.

```bash
ratatoskr whoami
ratatoskr --json whoami    # JSON output
```

### `ratatoskr save URL`

Save a URL and optionally trigger summarization.

```bash
ratatoskr save https://example.com/article
ratatoskr save https://example.com/article --title "Custom Title" --tag python --tag web
ratatoskr save https://example.com/article --no-summarize
ratatoskr save https://example.com/article --note "Key paragraph here"
```

| Option | Short | Description |
|--------|-------|-------------|
| `--title` | `-T` | Custom title |
| `--tag` | `-t` | Tag name (repeatable) |
| `--summarize/--no-summarize` | | Trigger summarization (default: on) |
| `--note` | | Note or selected text to attach |

### `ratatoskr list`

List saved summaries.

```bash
ratatoskr list
ratatoskr list --limit 50 --offset 20
ratatoskr list --unread
ratatoskr list --favorites
ratatoskr list --tag python
```

| Option | Short | Description |
|--------|-------|-------------|
| `--limit` | `-n` | Results per page (default: 20) |
| `--offset` | | Pagination offset |
| `--unread` | | Show only unread |
| `--favorites` | | Show only favorites |
| `--tag` | `-t` | Filter by tag name |

### `ratatoskr get ID`

Get summary details by ID.

```bash
ratatoskr get 42
ratatoskr get 42 --content     # Include full article content
ratatoskr --json get 42        # JSON output
```

### `ratatoskr search QUERY`

Search summaries by text query.

```bash
ratatoskr search "machine learning"
ratatoskr search "rust async" --limit 5
ratatoskr search "web dev" --tag tutorial --lang en
ratatoskr search "api design" --domain blog.example.com
```

| Option | Short | Description |
|--------|-------|-------------|
| `--limit` | `-n` | Max results (default: 20) |
| `--tag` | `-t` | Filter by tag (repeatable) |
| `--lang` | | Filter by language (`en`, `ru`) |
| `--domain` | `-d` | Filter by domain (repeatable) |

### Aggregation Bundles

Mixed-source aggregation uses the public `/v1/aggregations` API. The CLI submits the bundle and waits for the server to finish extraction plus synthesis. On success it prints the final persisted session snapshot (`completed` or `partial`); on timeout or upstream failure the API returns `PROCESSING_ERROR`.

### `ratatoskr aggregate [URL ...]`

Submit one or more URLs as a single aggregation bundle.

```bash
ratatoskr aggregate https://x.com/example/status/1 https://youtu.be/dQw4w9WgXcQ
ratatoskr aggregate --file sources.txt --lang en
ratatoskr aggregate --hint x_post --hint youtube_video \
  https://x.com/example/status/1 \
  https://youtu.be/dQw4w9WgXcQ
ratatoskr --json aggregate --file sources.txt | jq '.session.sessionId'
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

### `ratatoskr aggregation get ID`

Fetch one aggregation session by ID.

```bash
ratatoskr aggregation get 42
ratatoskr --json aggregation get 42 | jq '.session.progress'
```

### `ratatoskr aggregation list`

List recent aggregation sessions for the authenticated user.

```bash
ratatoskr aggregation list
ratatoskr aggregation list --limit 10 --offset 10
ratatoskr --json aggregation list --limit 5 | jq '.sessions[] | {id, status}'
```

`ratatoskr aggregation get` and `ratatoskr aggregation list` are mainly for revisiting stored runs, recovering after a network interruption, or scripting against previously created sessions. The current create path is blocking, so a successful `ratatoskr aggregate ...` call already returns a terminal session snapshot.

The most useful session fields are:

- `status`
- `progress.completionPercent`
- `successfulCount`
- `failedCount`
- `failure`
- `queuedAt`, `startedAt`, `completedAt`, `lastProgressAt`

### `ratatoskr delete ID`

Delete a summary by ID.

```bash
ratatoskr delete 42
```

### `ratatoskr favorite ID`

Toggle favorite status on a summary.

```bash
ratatoskr favorite 42
```

### `ratatoskr read ID`

Mark a summary as read.

```bash
ratatoskr read 42
```

### `ratatoskr tags`

Manage tags. Running `ratatoskr tags` without a subcommand lists all tags.

```bash
ratatoskr tags                           # List all tags
ratatoskr tags create "machine-learning" --color "#3B82F6"
ratatoskr tags delete 5                  # Prompts for confirmation
ratatoskr tags attach 42 "python"       # Attach tag to summary 42
ratatoskr tags detach 42 5              # Detach tag ID 5 from summary 42
```

### `ratatoskr collections`

Manage collections. Running `ratatoskr collections` without a subcommand lists all collections.

```bash
ratatoskr collections                            # List all
ratatoskr collections create "Reading List" -d "Articles to read this week"
ratatoskr collections delete 3                   # Prompts for confirmation
ratatoskr collections add 3 42                   # Add summary 42 to collection 3
```

### `ratatoskr export`

Export all data.

```bash
ratatoskr export                          # JSON to stdout
ratatoskr export --format csv -o data.csv
ratatoskr export --format html -o export.html
```

| Option | Short | Description |
|--------|-------|-------------|
| `--format` | | `json`, `csv`, or `html` (default: `json`) |
| `--output` | `-o` | Output file (default: stdout) |

### `ratatoskr import FILE`

Import bookmarks from a file.

```bash
ratatoskr import bookmarks.html
ratatoskr import bookmarks.json --summarize   # Trigger summarization for imports
```

### `ratatoskr admin`

Admin-only operations.

```bash
ratatoskr admin users     # List users with stats
ratatoskr admin health    # Content health report
ratatoskr admin jobs      # Background job status
```

## Configuration

Config is stored at `$XDG_CONFIG_HOME/ratatoskr/config.toml` (defaults to `~/.config/ratatoskr/config.toml`). The file is created with `0600` permissions (owner read/write only).

```toml
[server]
url = "https://ratatoskr.example.com"

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
| `RATATOSKR_SERVER_URL` | Override server URL (same as `--server` flag) |
| `XDG_CONFIG_HOME` | Override config directory base |

## Authentication

Ratatoskr CLI uses a secret-key authentication flow:

1. A client secret is generated server-side (via Telegram bot or admin API)
2. `ratatoskr login` exchanges the secret for JWT access and refresh tokens
3. Tokens are stored in the config file
4. The CLI automatically refreshes the access token when it's within 5 minutes of expiry

Important auth semantics:

- Client secrets are shown in plaintext only when they are created or rotated.
- A rotated or revoked secret cannot be used for future `ratatoskr login` calls.
- If access-token refresh fails because the refresh session was revoked or expired, run `ratatoskr login` again with an active secret.

For a full onboarding flow, including hosted MCP usage, see [External Access Quickstart](../../docs/tutorials/external-access-quickstart.md).

## JSON Output

Pass `--json` before any command to get raw JSON output, suitable for piping to `jq` or scripting:

```bash
ratatoskr --json list | jq '.[].title'
ratatoskr --json search "python" | jq '.results[] | {id, title}'
ratatoskr --json get 42 | jq '.tldr'
```

## Examples

### Save and tag an article

```bash
ratatoskr save https://blog.example.com/post -t rust -t async -T "Async Rust Guide"
```

### Browse unread articles

```bash
ratatoskr list --unread --limit 5
ratatoskr get 42
ratatoskr read 42
```

### Search and export results

```bash
ratatoskr --json search "kubernetes" --domain blog.example.com | jq '.results[].url'
```

### Build a reading list

```bash
ratatoskr collections create "Weekend Reads"
ratatoskr collections add 1 42
ratatoskr collections add 1 43
ratatoskr collections
```

### Backup your data

```bash
ratatoskr export --format json -o backup.json
```

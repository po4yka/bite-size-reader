# Quickstart Tutorial: Your First Summary in 5 Minutes

Get your first article summary with Bite-Size Reader in 5 minutes using Docker.

**Time**: ~5 minutes
**Difficulty**: Beginner
**Prerequisites**: Docker installed

---

## What You'll Learn

By the end of this tutorial, you'll have:

- ✅ Bite-Size Reader running in a Docker container
- ✅ Your Telegram bot responding to messages
- ✅ Your first article summary generated

---

## Step 1: Get API Keys (3 minutes)

You'll need API keys from three services:

### 1.1 Telegram Bot Token

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Follow prompts to choose a name (e.g., "My Summary Bot")
4. Copy the bot token (looks like `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 1.2 Telegram API Credentials

1. Go to https://my.telegram.org/apps
2. Log in with your phone number
3. Create a new application (any name/description)
4. Copy **API ID** (numeric) and **API hash** (alphanumeric)

### 1.3 Find Your Telegram User ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Copy the numeric user ID (e.g., `123456789`)

### 1.4 Firecrawl API Key

1. Go to https://firecrawl.dev/
2. Sign up for free account
3. Navigate to **API Keys** in dashboard
4. Copy your API key (starts with `fc-`)

**Note**: Free tier gives 500 credits/month (~500 articles)

### 1.5 OpenRouter API Key

1. Go to https://openrouter.ai/
2. Sign up (Google/GitHub login works)
3. Navigate to **Keys** in dashboard
4. Create new key
5. Add $5 credit (minimum, ~500 summaries)
6. Copy your API key (starts with `sk-or-`)

---

## Step 2: Create Configuration File (1 minute)

Create a file named `.env` with your API keys:

```bash
# Create directory for data
mkdir -p ~/bite-size-reader/data

# Create .env file
cat > ~/bite-size-reader/.env << 'EOF'
# Telegram Configuration
API_ID=your_api_id_here
API_HASH=your_api_hash_here
BOT_TOKEN=your_bot_token_here
ALLOWED_USER_IDS=your_telegram_user_id_here

# Content Extraction
FIRECRAWL_API_KEY=your_firecrawl_key_here

# LLM Summarization
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_MODEL=deepseek/deepseek-v3.2

# Database
DB_PATH=/data/app.db

# Logging
LOG_LEVEL=INFO
EOF
```

**Replace placeholders** with your actual values:

- `your_api_id_here` → API ID from Step 1.2
- `your_api_hash_here` → API hash from Step 1.2
- `your_bot_token_here` → Bot token from Step 1.1
- `your_telegram_user_id_here` → User ID from Step 1.3
- `your_firecrawl_key_here` → Firecrawl key from Step 1.4
- `your_openrouter_key_here` → OpenRouter key from Step 1.5

---

## Step 3: Run with Docker (30 seconds)

```bash
# Pull latest image
docker pull ghcr.io/po4yka/bite-size-reader:latest

# Run container
docker run -d \
  --name bite-size-reader \
  --env-file ~/bite-size-reader/.env \
  -v ~/bite-size-reader/data:/data \
  --restart unless-stopped \
  ghcr.io/po4yka/bite-size-reader:latest

# Verify it's running
docker logs bite-size-reader

# Should see:
# INFO: Bot started successfully
# INFO: Listening for messages...
```

**Troubleshooting**: If you see errors, check:

- All API keys are correct (no extra spaces)
- `ALLOWED_USER_IDS` matches your Telegram user ID
- Docker has internet access

---

## Step 4: Test Your Bot (1 minute)

### 4.1 Start the Bot

1. Open Telegram
2. Search for your bot (name you chose in Step 1.1)
3. Start conversation with `/start`

**Expected response**:

```
👋 Welcome to Bite-Size Reader!

Send me:
• Web article URL → Get structured summary
• YouTube video URL → Get transcript summary
• /help → See all commands
```

### 4.2 Get Your First Summary

Send any web article URL to the bot:

```
https://example.com/some-article
```

**What happens**:

1. Bot replies "📥 Processing article..."
2. ~5-10 seconds pass
3. Bot sends formatted summary:

```
📄 Article Title

🔖 TLDR
[50-character summary]

📝 Summary (250 chars)
[Concise summary]

💡 Key Ideas
• Idea 1
• Idea 2
• Idea 3

🏷 Topics: technology, python, tutorial

✅ Processed in 8.2s
```

---

## Step 5: Verify Everything Works

Try these commands to confirm full functionality:

```
/help          → See all commands
/stats         → See usage statistics
/search python → Search past summaries
```

---

## Next Steps

Congratulations! You've successfully set up Bite-Size Reader. 🎉

**Enhance your setup**:

- ✨ [Enable YouTube support](../how-to/configure-youtube-download.md) - Summarize videos
- 🔍 [Enable web search](../how-to/enable-web-search.md) - Add real-time context
- ⚡ [Setup Redis caching](../how-to/setup-redis-caching.md) - Faster responses
- 🧠 [Setup ChromaDB](../how-to/setup-chroma-vector-search.md) - Semantic search

**Learn more**:

- [FAQ](../FAQ.md) - Common questions
- [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) - Fix issues
- [Environment variables reference](../environment_variables.md) - Full config options

---

## Common Issues

### Bot doesn't respond

**Cause**: User ID not whitelisted

**Solution**:

```bash
# Check your Telegram user ID
# Message @userinfobot and verify it matches ALLOWED_USER_IDS

# Update .env
echo "ALLOWED_USER_IDS=123456789" >> ~/bite-size-reader/.env

# Restart container
docker restart bite-size-reader
```

### "Access denied" error

**Cause**: Wrong Telegram user ID in `ALLOWED_USER_IDS`

**Solution**: Follow "Bot doesn't respond" above

### Summaries fail with "Firecrawl error"

**Cause**: Invalid Firecrawl API key or quota exceeded

**Solution**:

```bash
# Test Firecrawl key
curl -H "Authorization: Bearer YOUR_FIRECRAWL_KEY" \
     https://api.firecrawl.dev/v1/account

# Check quota (free tier: 500 credits/month)
# If exceeded, upgrade at https://firecrawl.dev/pricing
```

### Summaries fail with "OpenRouter error"

**Cause**: Invalid API key or no credits

**Solution**:

```bash
# Check OpenRouter credits
curl -H "Authorization: Bearer YOUR_OPENROUTER_KEY" \
     https://openrouter.ai/api/v1/auth/key

# Add credits at https://openrouter.ai/credits
```

---

## Docker Commands Reference

```bash
# View logs
docker logs bite-size-reader

# Follow logs in real-time
docker logs -f bite-size-reader

# Stop container
docker stop bite-size-reader

# Start container
docker start bite-size-reader

# Restart container
docker restart bite-size-reader

# Remove container
docker rm -f bite-size-reader

# Update to latest version
docker pull ghcr.io/po4yka/bite-size-reader:latest
docker rm -f bite-size-reader
# Re-run docker run command from Step 3
```

---

## Alternative: Local Installation (No Docker)

If you prefer running without Docker:

```bash
# Clone repository
git clone https://github.com/po4yka/bite-size-reader.git
cd bite-size-reader

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy .env file to project root
cp ~/bite-size-reader/.env .

# Run bot
python bot.py
```

See [Local Development Tutorial](local-development.md) for full guide.

---

**Tutorial Complete!** 🎓

You now have a working Bite-Size Reader setup. Try summarizing a few articles to get familiar with the output format.

**Questions?** Check [FAQ](../FAQ.md) or [open an issue](https://github.com/po4yka/bite-size-reader/issues).

---

**Last Updated**: 2026-02-09

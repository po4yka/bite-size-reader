# Ratatoskr Documentation Hub

Welcome to the Ratatoskr documentation. This guide helps you find the right documentation for your needs.

> Note: this directory keeps current, user-facing and engineering reference docs; temporary planning notes and historical implementation reports are removed after completion.

## Documentation freshness

- Last documentation refresh: **2026-04-28**
- This refresh aligns docs with:
  - Root namespace reorganization: `clients/`, `integrations/`, `ops/`, and `tools/`
  - web interface architecture in `clients/web/` (routing, auth modes, deploy/static namespaces)
  - Web static check workflow (`npm run check:static`) and CI jobs (`web-build`, `web-test`, `web-static-check`)
  - Docker and compose assets relocated under `ops/docker/`
  - FastAPI SPA serving contract (`/web`, `/web/*`) alongside Telegram Mini App static assets
  - Mixed-source aggregation across Telegram and FastAPI, including rollout flags and bundle observability

## Documentation by Audience

### 👤 I'm a User

You want to use Ratatoskr to summarize articles, videos, or mixed-source bundles.

**Start here**:

1. [Quickstart Tutorial](guides/quickstart.md) - Get your first summary in 5 minutes
2. [External Access Quickstart](guides/external-access-quickstart.md) - First CLI or MCP aggregation session
3. [FAQ](FAQ.md) - Common questions answered
4. [DEPLOYMENT.md](DEPLOYMENT.md) - Setup and installation
5. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Fix common issues

**Next steps**:

- [How to enable YouTube support](guides/configure-youtube-download.md)
- [How to enable web search](guides/enable-web-search.md)
- [External Access Quickstart](guides/external-access-quickstart.md)
- [SPEC.md § Mixed-source aggregation foundation](SPEC.md#data-model-sqlite)
- [Environment variables reference](environment_variables.md)

### 💻 I'm a Developer

You want to contribute code, customize the bot, or understand the architecture.

**Start here**:

1. [Architecture Overview](explanation/architecture-overview.md) - Component diagram, request lifecycle, subsystem index
2. [Local Development Tutorial](guides/local-development.md) - Set up dev environment
3. [Frontend Web Guide](reference/frontend-web.md) - web app architecture and workflows
4. [Architecture Overview § Layering quick reference](explanation/architecture-overview.md#layering-quick-reference) - Why ports and adapters
5. [SPEC.md](SPEC.md) - Technical specification
6. [CLAUDE.md](../CLAUDE.md) - AI assistant guide (comprehensive codebase overview)

**Next steps**:

- [Multi-Agent Architecture](explanation/multi-agent-architecture.md) - LLM pipeline design
- [Explanation docs](README.md#explanation-understanding-oriented) - Design rationale

### 🔧 I'm an Operator

You want to deploy, monitor, and maintain Ratatoskr in production.

**Start here**:

1. [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment guide
2. [Environment variables reference](environment_variables.md) - Configuration
3. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Debugging

**Next steps**:

- [How to setup Redis caching](guides/setup-redis-caching.md)
- [How to setup ChromaDB](guides/setup-chroma-vector-search.md)
- [How to backup and restore](guides/backup-and-restore.md)
- [How to optimize performance](guides/optimize-performance.md)

### 🤝 I'm a Contributor

You want to submit pull requests or improve the project.

**Start here**:

1. [Local Development Tutorial](guides/local-development.md)
2. Code standards: See [CLAUDE.md § Code Standards](../CLAUDE.md#code-standards)

**Next steps**:

- [SPEC.md](SPEC.md) - Technical specification
- [Architecture Overview § Layering quick reference](explanation/architecture-overview.md#layering-quick-reference) - Code organization
- [Scraper chain explainer](explanation/scraper-chain.md) - Provider taxonomy, fallback logic, and deployment topology
- [Frontend Web Guide](reference/frontend-web.md) - web app architecture and design shim notes

### 🔌 I'm an Integrator

You want to integrate Ratatoskr with other tools or build a client.

**Start here**:

1. [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md) - REST API specification
2. [Frontend Web Guide](reference/frontend-web.md) - Web client routes, auth, and API usage
3. [MCP Server Guide](reference/mcp-server.md) - AI agent integration
4. [External Access Quickstart](guides/external-access-quickstart.md)
5. [First Mobile API Client Tutorial](guides/first-mobile-api-client.md)

**Next steps**:

- [OpenAPI Schema](openapi/) - Machine-readable API spec
- [Database Schema Reference](SPEC.md#database-schema) - Direct database access
- [Summary Contract Reference](SPEC.md#summary-json-contract) - JSON output format

---

## Documentation by Task

### 🚀 Getting Started

**I want to...**

- **Get my first summary in 5 minutes** → [Quickstart Tutorial](guides/quickstart.md)
- **Submit an aggregation bundle from CLI or MCP** → [External Access Quickstart](guides/external-access-quickstart.md)
- **Install on my server** → [DEPLOYMENT.md](DEPLOYMENT.md)
- **Understand what this project does** → [README.md](../README.md) (project root)
- **Decide if this is right for me** → [FAQ](FAQ.md)
- **Open the web UI** → [Frontend Web Guide](reference/frontend-web.md)

### 🛠 Configuring Features

**I want to...**

- **Enable YouTube support** → [How to configure YouTube download](guides/configure-youtube-download.md)
- **Enable Twitter / X extraction** → [How to configure Twitter / X extraction](guides/configure-twitter-extraction.md)
- **Upgrade across the project rename** → [Migrate from bite-size-reader](guides/migrate-from-bite-size-reader.md)
- **Run mixed-source aggregation** → [SPEC.md § Mixed-source aggregation foundation](SPEC.md#data-model-sqlite)
- **Onboard an external CLI or MCP client** → [External Access Quickstart](guides/external-access-quickstart.md)
- **Enable web search enrichment** → [How to enable web search](guides/enable-web-search.md)
- **Setup Redis caching** → [How to setup Redis caching](guides/setup-redis-caching.md)
- **Setup semantic search (ChromaDB)** → [How to setup ChromaDB](guides/setup-chroma-vector-search.md)
- **See all config options** → [Environment variables reference](environment_variables.md)

### 🐛 Troubleshooting

**I'm experiencing...**

- **Bot not starting** → [TROUBLESHOOTING.md § Configuration Issues](TROUBLESHOOTING.md#configuration-issues)
- **Summaries failing** → [TROUBLESHOOTING.md § Firecrawl/OpenRouter Issues](TROUBLESHOOTING.md#firecrawl-issues)
- **YouTube downloads failing** → [TROUBLESHOOTING.md § YouTube Issues](TROUBLESHOOTING.md#youtube-issues)
- **Slow performance** → [TROUBLESHOOTING.md § Performance Issues](TROUBLESHOOTING.md#performance-issues)
- **Something else** → [TROUBLESHOOTING.md](TROUBLESHOOTING.md) (full guide)

### 🔍 Understanding the System

**I want to...**

- **Get the high-level picture** → [Architecture Overview](explanation/architecture-overview.md)
- **Understand the layer rationale** → [Architecture Overview § Layering quick reference](explanation/architecture-overview.md#layering-quick-reference)
- **Understand the multi-agent pipeline** → [Multi-Agent Architecture](explanation/multi-agent-architecture.md)
- **Understand design decisions** → [Design Philosophy](explanation/design-philosophy.md)
- **See the full technical spec** → [SPEC.md](SPEC.md)

### 🧑‍💻 Developing

**I want to...**

- **Set up local dev environment** → [Local Development Tutorial](guides/local-development.md)
- **Run web app locally** → [Frontend Web Guide](reference/frontend-web.md#local-development)
- **Run tests** → [Local Development Tutorial § Running Tests](guides/local-development.md)
- **Run web static checks** → [Frontend Web Guide](reference/frontend-web.md#quality-checks)
- **Add a new feature** → [CLAUDE.md § Adding a New Feature](../CLAUDE.md#common-tasks)
- **Understand the codebase** → [CLAUDE.md](../CLAUDE.md) (AI assistant guide, comprehensive)

### 🔌 Integrating

**I want to...**

- **Build a mobile app client** → [First Mobile API Client Tutorial](guides/first-mobile-api-client.md)
- **Connect the packaged CLI or hosted MCP** → [External Access Quickstart](guides/external-access-quickstart.md)
- **Build or extend web client** → [Frontend Web Guide](reference/frontend-web.md)
- **Integrate with Claude Desktop** → [MCP Server Guide](reference/mcp-server.md)
- **Access the database directly** → [SPEC.md § Database Schema](SPEC.md#database-schema)
- **See the full API spec** → [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md)

---

## Documentation by Type (Diátaxis Framework)

The documentation is organized using the [Diátaxis framework](https://diataxis.fr/), which categorizes docs into four types:

### Guides (Learning- and Goal-Oriented)

Step-by-step lessons and practical recipes, all in `docs/guides/`.

| Guide | Description | Audience | Time |
| ------- | ------------- | ---------- | ------ |
| [Quickstart](guides/quickstart.md) | Get your first summary in 5 minutes | Users | 5 min |
| [Clone to First Summary](guides/clone-to-first-summary.md) | Minimal clone-to-run steps | Users | 10 min |
| [Local Development](guides/local-development.md) | Full local dev environment setup | Developers | 20 min |
| [First Mobile API Client](guides/first-mobile-api-client.md) | Build a simple mobile client | Integrators | 30 min |
| [External Access Quickstart](guides/external-access-quickstart.md) | First CLI or MCP aggregation session | Integrators, External users | 10 min |
| [Configure YouTube Download](guides/configure-youtube-download.md) | Enable YouTube support | Users, Operators | |
| [Configure Twitter / X Extraction](guides/configure-twitter-extraction.md) | Two-tier (Firecrawl + Playwright) tweet, thread, and X Article extraction | Users, Operators | |
| [Configure Source Ingestors](guides/configure-source-ingestors.md) | Tune the scraper chain providers | Operators | |
| [Enable Web Search](guides/enable-web-search.md) | Add real-time web context | Users, Operators | |
| [Setup Redis Caching](guides/setup-redis-caching.md) | Configure Redis | Operators | |
| [Setup ChromaDB](guides/setup-chroma-vector-search.md) | Enable semantic search | Operators | |
| [Optimize Performance](guides/optimize-performance.md) | Tune for speed/cost | Operators | |
| [Backup and Restore](guides/backup-and-restore.md) | Data protection | Operators | |
| [Migrate Versions](guides/migrate-versions.md) | Upgrade between versions | Operators | |
| [Migrate from bite-size-reader](guides/migrate-from-bite-size-reader.md) | Operator checklist for upgrading across the project rename | Operators | |
| [Migrate Telegram Sessions to Telethon](guides/migrate-telegram-sessions-to-telethon.md) | Session migration steps | Operators | |

### Reference (Information-Oriented)

Technical facts, API specs, and complete references.

| Reference | Description | Audience |
| ----------- | ------------- | ---------- |
| [SPEC.md](SPEC.md) | Complete technical specification | Developers, Integrators |
| [Environment Variables](environment_variables.md) | Full configuration reference (250+ vars) | All |
| [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md) | REST API specification | Integrators |
| [Frontend Web Guide](reference/frontend-web.md) | web app architecture, auth, and workflows | Developers, Integrators |
| [OpenAPI Schema](openapi/) | Machine-readable API spec | Integrators |
| [Summary Contract](SPEC.md#summary-json-contract) | JSON output format (35+ fields) | Developers, Integrators |
| [Database Schema](SPEC.md#database-schema) | Database tables and relationships | Developers, Integrators |

### Explanation (Understanding-Oriented)

Background, context, and "why" discussions.

| Explanation | Description | Audience |
| ------------- | ------------- | ---------- |
| [Architecture Overview](explanation/architecture-overview.md) | Component diagram, request lifecycle, subsystem index | Operators, Developers, Integrators |
| [Hexagonal Architecture](explanation/architecture-overview.md#layering-quick-reference) | Why ports and adapters (see Architecture Overview) | Developers |
| [Multi-Agent Architecture](explanation/multi-agent-architecture.md) | Why specialized agents | Developers |
| [MCP Server](reference/mcp-server.md) | AI agent integration explained | Integrators |
| [Claude Code Hooks](reference/claude-code-hooks.md) | Safety hooks explained | Developers |

---

## Quick Reference

### Core Documentation Files

| File | Description | When to Read |
| ------ | ------------- | -------------- |
| [README.md](../README.md) | Project overview, quick start | First time using the project |
| [SPEC.md](SPEC.md) | Technical specification | Deep dive into system design |
| [CLAUDE.md](../CLAUDE.md) | AI assistant guide | Comprehensive codebase overview |
| [FAQ.md](FAQ.md) | Frequently asked questions | Quick answers to common questions |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Debugging guide | When something goes wrong |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Setup and deployment | Initial setup, production deploy |
| [environment_variables.md](environment_variables.md) | Config reference | Configuring the system |
| [CHANGELOG.md](../CHANGELOG.md) | Version history | Tracking changes over time |

### Specialized Documentation

| File | Description | When to Read |
| ------ | ------------- | -------------- |
| [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md) | REST API spec, including aggregation endpoints | Building mobile client |
| [Frontend Web Guide](reference/frontend-web.md) | Web routes/auth/build details | Building or debugging web UI |
| [Architecture Overview § Layering](explanation/architecture-overview.md#layering-quick-reference) | Architecture guide (layering section) | Understanding code structure |
| [multi-agent-architecture.md](explanation/multi-agent-architecture.md) | Multi-agent LLM | Understanding summarization pipeline |
| [mcp-server.md](reference/mcp-server.md) | MCP integration | Integrating with AI agents |
| [claude-code-hooks.md](reference/claude-code-hooks.md) | Safety hooks | Understanding dev workflow |

---

## Glossary

**Quick reference for key terms:**

- **Correlation ID**: Unique identifier (`UUID`) tying together Telegram messages, database requests, API calls, and logs
- **Summary Contract**: Strict JSON schema (35+ fields) that all LLM summaries must follow
- **Firecrawl**: Managed web scraping API used for content extraction
- **OpenRouter**: Multi-model LLM routing service (supports DeepSeek, Qwen, Kimi, GPT-4, Claude, etc.)
- **Hexagonal Architecture**: Design pattern separating core logic from adapters (Telegram, Firecrawl, database)
- **Multi-Agent Pipeline**: LLM architecture with specialized agents (extraction, summarization, validation, web search)
- **MCP Server**: Model Context Protocol server exposing Ratatoskr to AI agents (Claude Desktop, etc.)
- **ChromaDB**: Vector database for semantic search
- **Deduplication Hash**: SHA256 of normalized URL to prevent re-processing same article

See the [Architecture Overview](explanation/architecture-overview.md) for an annotated component diagram, the [SPEC.md](SPEC.md) data-model and API contracts, and the [Multi-Agent Architecture](explanation/multi-agent-architecture.md) explanation for the LLM pipeline-specific terms.

---

## Keyword Index

**Search this index to find relevant documentation:**

| Keyword | See Documentation |
| --------- | ------------------- |
| **API integration** | [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md), [First Mobile API Client Tutorial](guides/first-mobile-api-client.md) |
| **Architecture** | [Architecture Overview](explanation/architecture-overview.md), [Layering quick reference](explanation/architecture-overview.md#layering-quick-reference) |
| **Backup** | [How to backup and restore](guides/backup-and-restore.md), [TROUBLESHOOTING.md § Database](TROUBLESHOOTING.md#database-issues) |
| **ChromaDB** | [How to setup ChromaDB](guides/setup-chroma-vector-search.md), [TROUBLESHOOTING.md § ChromaDB](TROUBLESHOOTING.md#chromadb-issues) |
| **Configuration** | [environment_variables.md](environment_variables.md), [FAQ § Configuration](FAQ.md#configuration) |
| **Cost optimization** | [FAQ § Cost Optimization](FAQ.md#cost-optimization) |
| **Database** | [SPEC.md § Database Schema](SPEC.md#database-schema), [TROUBLESHOOTING.md § Database](TROUBLESHOOTING.md#database-issues) |
| **Debugging** | [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [SPEC.md § Correlation IDs](SPEC.md#correlation-ids) |
| **Deployment** | [DEPLOYMENT.md](DEPLOYMENT.md), [Quickstart Tutorial](guides/quickstart.md) |
| **Docker** | [DEPLOYMENT.md § Docker](DEPLOYMENT.md), [FAQ § Installation](FAQ.md#installation) |
| **Firecrawl** | [Scraper chain explainer](explanation/scraper-chain.md), [TROUBLESHOOTING.md § Firecrawl](TROUBLESHOOTING.md#firecrawl-issues) |
| **Installation** | [DEPLOYMENT.md](DEPLOYMENT.md), [FAQ § Installation](FAQ.md#installation) |
| **LLM models** | [environment_variables.md § LLM](environment_variables.md), [FAQ § Cost](FAQ.md#what-are-the-cheapest-models-that-work-well) |
| **MCP Server** | [reference/mcp-server.md](reference/mcp-server.md), [TROUBLESHOOTING.md § MCP](TROUBLESHOOTING.md#mcp-server-issues) |
| **Mobile API** | [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md), [First Mobile API Client Tutorial](guides/first-mobile-api-client.md) |
| **Mixed-source aggregation** | [SPEC.md](SPEC.md), [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md), [environment_variables.md](environment_variables.md) |
| **Multi-agent** | [multi-agent-architecture.md](explanation/multi-agent-architecture.md) |
| **OpenRouter** | [environment_variables.md § OpenRouter](environment_variables.md), [TROUBLESHOOTING.md § OpenRouter](TROUBLESHOOTING.md#openrouter-issues) |
| **Performance** | [How to optimize performance](guides/optimize-performance.md), [TROUBLESHOOTING.md § Performance](TROUBLESHOOTING.md#performance-issues) |
| **Redis** | [How to setup Redis](guides/setup-redis-caching.md), [TROUBLESHOOTING.md § Redis](TROUBLESHOOTING.md#redis-issues) |
| **Search** | [SPEC.md § Search](SPEC.md#search), [How to setup ChromaDB](guides/setup-chroma-vector-search.md) |
| **Security** | [FAQ § Security](FAQ.md#security) |
| **Summary contract** | [SPEC.md § Summary JSON Contract](SPEC.md#summary-json-contract), [Summary Contract Design](explanation/summary-contract-design.md) |
| **Testing** | [Local Development Tutorial § Testing](guides/local-development.md), [CLAUDE.md § Testing](../CLAUDE.md#testing) |
| **Troubleshooting** | [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [FAQ](FAQ.md) |
| **Web interface** | [Frontend Web Guide](reference/frontend-web.md), [README.md § Web Interface](../README.md#web-interface-v1) |
| **Web search** | [How to enable web search](guides/enable-web-search.md), [FAQ § Web Search](FAQ.md#web-search) |
| **YouTube** | [How to configure YouTube](guides/configure-youtube-download.md), [TROUBLESHOOTING.md § YouTube](TROUBLESHOOTING.md#youtube-issues) |

---

## Contributing to Documentation

Found a typo? Documentation unclear? Want to add a tutorial?

1. **Small fixes**: Edit directly and submit PR
2. **New documentation**: Follow [Diátaxis framework](https://diataxis.fr/)
   - Tutorials = step-by-step lessons
   - How-to guides = goal-oriented recipes
   - Reference = technical facts
   - Explanation = background and "why"
3. **Update this hub**: Add new docs to relevant sections above

---

**Last Updated**: 2026-04-28

**Questions?** Check [FAQ](FAQ.md) or open an [issue](https://github.com/po4yka/ratatoskr/issues).

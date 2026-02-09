# Bite-Size Reader Documentation Hub

Welcome to the Bite-Size Reader documentation. This guide helps you find the right documentation for your needs.

## Documentation by Audience

### 👤 I'm a User

You want to use Bite-Size Reader to summarize articles and videos.

**Start here**:

1. [Quickstart Tutorial](tutorials/quickstart.md) - Get your first summary in 5 minutes
2. [FAQ](FAQ.md) - Common questions answered
3. [DEPLOYMENT.md](DEPLOYMENT.md) - Setup and installation
4. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Fix common issues

**Next steps**:

- [How to enable YouTube support](how-to/configure-youtube-download.md)
- [How to enable web search](how-to/enable-web-search.md)
- [Environment variables reference](environment_variables.md)

### 💻 I'm a Developer

You want to contribute code, customize the bot, or understand the architecture.

**Start here**:

1. [Local Development Tutorial](tutorials/local-development.md) - Set up dev environment
2. [HEXAGONAL_ARCHITECTURE_QUICKSTART.md](HEXAGONAL_ARCHITECTURE_QUICKSTART.md) - Architecture overview
3. [SPEC.md](SPEC.md) - Technical specification
4. [CLAUDE.md](../CLAUDE.md) - AI assistant guide (comprehensive codebase overview)

**Next steps**:

- [ADRs](adr/README.md) - Architecture decision records (why things are this way)
- [Multi-Agent Architecture](multi_agent_architecture.md) - LLM pipeline design
- [Explanation docs](README.md#explanation-understanding-oriented) - Design rationale

### 🔧 I'm an Operator

You want to deploy, monitor, and maintain Bite-Size Reader in production.

**Start here**:

1. [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment guide
2. [Environment variables reference](environment_variables.md) - Configuration
3. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Debugging

**Next steps**:

- [How to setup Redis caching](how-to/setup-redis-caching.md)
- [How to setup ChromaDB](how-to/setup-chroma-vector-search.md)
- [How to backup and restore](how-to/backup-and-restore.md)
- [How to optimize performance](how-to/optimize-performance.md)

### 🤝 I'm a Contributor

You want to submit pull requests or improve the project.

**Start here**:

1. [Local Development Tutorial](tutorials/local-development.md)
2. Code standards: See [CLAUDE.md § Code Standards](../CLAUDE.md#code-standards)
3. [ADR Template](adr/template.md) - For documenting architectural decisions

**Next steps**:

- [SPEC.md](SPEC.md) - Technical specification
- [ADRs](adr/README.md) - Understand past decisions
- [HEXAGONAL_ARCHITECTURE_QUICKSTART.md](HEXAGONAL_ARCHITECTURE_QUICKSTART.md) - Code organization

### 🔌 I'm an Integrator

You want to integrate Bite-Size Reader with other tools or build a client.

**Start here**:

1. [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md) - REST API specification
2. [MCP Server Guide](mcp_server.md) - AI agent integration
3. [First Mobile API Client Tutorial](tutorials/first-mobile-api-client.md)

**Next steps**:

- [OpenAPI Schema](openapi/) - Machine-readable API spec
- [Database Schema Reference](SPEC.md#database-schema) - Direct database access
- [Summary Contract Reference](SPEC.md#summary-json-contract) - JSON output format

---

## Documentation by Task

### 🚀 Getting Started

**I want to...**

- **Get my first summary in 5 minutes** → [Quickstart Tutorial](tutorials/quickstart.md)
- **Install on my server** → [DEPLOYMENT.md](DEPLOYMENT.md)
- **Understand what this project does** → [README.md](../README.md) (project root)
- **Decide if this is right for me** → [FAQ](FAQ.md)

### 🛠 Configuring Features

**I want to...**

- **Enable YouTube support** → [How to configure YouTube download](how-to/configure-youtube-download.md)
- **Enable web search enrichment** → [How to enable web search](how-to/enable-web-search.md)
- **Setup Redis caching** → [How to setup Redis caching](how-to/setup-redis-caching.md)
- **Setup semantic search (ChromaDB)** → [How to setup ChromaDB](how-to/setup-chroma-vector-search.md)
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

- **Understand the architecture** → [HEXAGONAL_ARCHITECTURE_QUICKSTART.md](HEXAGONAL_ARCHITECTURE_QUICKSTART.md)
- **Understand the multi-agent pipeline** → [Multi-Agent Architecture](multi_agent_architecture.md)
- **Understand design decisions** → [ADRs](adr/README.md)
- **See the full technical spec** → [SPEC.md](SPEC.md)

### 🧑‍💻 Developing

**I want to...**

- **Set up local dev environment** → [Local Development Tutorial](tutorials/local-development.md)
- **Run tests** → [Local Development Tutorial § Running Tests](tutorials/local-development.md)
- **Add a new feature** → [CLAUDE.md § Adding a New Feature](../CLAUDE.md#common-tasks)
- **Understand the codebase** → [CLAUDE.md](../CLAUDE.md) (AI assistant guide, comprehensive)

### 🔌 Integrating

**I want to...**

- **Build a mobile app client** → [First Mobile API Client Tutorial](tutorials/first-mobile-api-client.md)
- **Integrate with Claude Desktop** → [MCP Server Guide](mcp_server.md)
- **Access the database directly** → [SPEC.md § Database Schema](SPEC.md#database-schema)
- **See the full API spec** → [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md)

---

## Documentation by Type (Diátaxis Framework)

The documentation is organized using the [Diátaxis framework](https://diataxis.fr/), which categorizes docs into four types:

### Tutorials (Learning-Oriented)

Step-by-step lessons that teach you how to use Bite-Size Reader.

| Tutorial | Description | Audience | Time |
|----------|-------------|----------|------|
| [Quickstart](tutorials/quickstart.md) | Get first summary in 5 minutes | Users | 5 min |
| [Local Development](tutorials/local-development.md) | Set up dev environment | Developers | 20 min |
| [First Mobile API Client](tutorials/first-mobile-api-client.md) | Build a simple mobile client | Integrators | 30 min |

### How-To Guides (Goal-Oriented)

Practical guides for accomplishing specific tasks.

| Guide | Description | Audience |
|-------|-------------|----------|
| [Configure YouTube Download](how-to/configure-youtube-download.md) | Enable YouTube support | Users, Operators |
| [Enable Web Search](how-to/enable-web-search.md) | Add real-time web context | Users, Operators |
| [Setup Redis Caching](how-to/setup-redis-caching.md) | Configure Redis | Operators |
| [Setup ChromaDB](how-to/setup-chroma-vector-search.md) | Enable semantic search | Operators |
| [Migrate Versions](how-to/migrate-versions.md) | Upgrade between versions | Operators |
| [Optimize Performance](how-to/optimize-performance.md) | Tune for speed/cost | Operators |
| [Backup and Restore](how-to/backup-and-restore.md) | Data protection | Operators |

**Existing guides** (already written):

- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment guide

### Reference (Information-Oriented)

Technical facts, API specs, and complete references.

| Reference | Description | Audience |
|-----------|-------------|----------|
| [SPEC.md](SPEC.md) | Complete technical specification | Developers, Integrators |
| [Environment Variables](environment_variables.md) | Full configuration reference (250+ vars) | All |
| [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md) | REST API specification | Integrators |
| [OpenAPI Schema](openapi/) | Machine-readable API spec | Integrators |
| [Summary Contract](SPEC.md#summary-json-contract) | JSON output format (35+ fields) | Developers, Integrators |
| [Database Schema](SPEC.md#database-schema) | Database tables and relationships | Developers, Integrators |
| [ADR Template](adr/template.md) | Architecture decision template | Contributors |

### Explanation (Understanding-Oriented)

Background, context, and "why" discussions.

| Explanation | Description | Audience |
|-------------|-------------|----------|
| [ADRs](adr/README.md) | Architecture decision records | Developers, Contributors |
| [Hexagonal Architecture](HEXAGONAL_ARCHITECTURE_QUICKSTART.md) | Why ports and adapters | Developers |
| [Multi-Agent Architecture](multi_agent_architecture.md) | Why specialized agents | Developers |
| [MCP Server](mcp_server.md) | AI agent integration explained | Integrators |
| [Claude Code Hooks](claude_code_hooks.md) | Safety hooks explained | Developers |

---

## Quick Reference

### Core Documentation Files

| File | Description | When to Read |
|------|-------------|--------------|
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
|------|-------------|--------------|
| [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md) | REST API spec | Building mobile client |
| [HEXAGONAL_ARCHITECTURE_QUICKSTART.md](HEXAGONAL_ARCHITECTURE_QUICKSTART.md) | Architecture guide | Understanding code structure |
| [multi_agent_architecture.md](multi_agent_architecture.md) | Multi-agent LLM | Understanding summarization pipeline |
| [mcp_server.md](mcp_server.md) | MCP integration | Integrating with AI agents |
| [claude_code_hooks.md](claude_code_hooks.md) | Safety hooks | Understanding dev workflow |

### Architecture Decision Records

| ADR | Title | When to Read |
|-----|-------|--------------|
| [ADR-0001](adr/0001-use-firecrawl-for-content-extraction.md) | Use Firecrawl | Why Firecrawl vs alternatives |
| [ADR-0002](adr/0002-strict-json-summary-contract.md) | Strict JSON contract | Why structured output |
| [ADR-0003](adr/0003-single-user-access-control.md) | Single-user access | Why not multi-tenant |
| [ADR-0004](adr/0004-hexagonal-architecture.md) | Hexagonal architecture | Why ports and adapters |
| [ADR-0005](adr/0005-multi-agent-llm-pipeline.md) | Multi-agent pipeline | Why specialized agents |

---

## Glossary

**Quick reference for key terms:**

- **Correlation ID**: Unique identifier (`UUID`) tying together Telegram messages, database requests, API calls, and logs
- **Summary Contract**: Strict JSON schema (35+ fields) that all LLM summaries must follow
- **Firecrawl**: Managed web scraping API used for content extraction
- **OpenRouter**: Multi-model LLM routing service (supports DeepSeek, Qwen, Kimi, GPT-4, Claude, etc.)
- **Hexagonal Architecture**: Design pattern separating core logic from adapters (Telegram, Firecrawl, database)
- **Multi-Agent Pipeline**: LLM architecture with specialized agents (extraction, summarization, validation, web search)
- **MCP Server**: Model Context Protocol server exposing Bite-Size Reader to AI agents (Claude Desktop, etc.)
- **ChromaDB**: Vector database for semantic search
- **Deduplication Hash**: SHA256 of normalized URL to prevent re-processing same article

See [SPEC.md § Glossary](SPEC.md#glossary) for full glossary.

---

## Keyword Index

**Search this index to find relevant documentation:**

| Keyword | See Documentation |
|---------|-------------------|
| **API integration** | [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md), [First Mobile API Client Tutorial](tutorials/first-mobile-api-client.md) |
| **Architecture** | [HEXAGONAL_ARCHITECTURE_QUICKSTART.md](HEXAGONAL_ARCHITECTURE_QUICKSTART.md), [ADRs](adr/README.md) |
| **Backup** | [How to backup and restore](how-to/backup-and-restore.md), [TROUBLESHOOTING.md § Database](TROUBLESHOOTING.md#database-issues) |
| **ChromaDB** | [How to setup ChromaDB](how-to/setup-chroma-vector-search.md), [TROUBLESHOOTING.md § ChromaDB](TROUBLESHOOTING.md#chromadb-issues) |
| **Configuration** | [environment_variables.md](environment_variables.md), [FAQ § Configuration](FAQ.md#configuration) |
| **Cost optimization** | [FAQ § Cost Optimization](FAQ.md#cost-optimization) |
| **Database** | [SPEC.md § Database Schema](SPEC.md#database-schema), [TROUBLESHOOTING.md § Database](TROUBLESHOOTING.md#database-issues) |
| **Debugging** | [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [SPEC.md § Correlation IDs](SPEC.md#correlation-ids) |
| **Deployment** | [DEPLOYMENT.md](DEPLOYMENT.md), [Quickstart Tutorial](tutorials/quickstart.md) |
| **Docker** | [DEPLOYMENT.md § Docker](DEPLOYMENT.md), [FAQ § Installation](FAQ.md#installation) |
| **Firecrawl** | [ADR-0001](adr/0001-use-firecrawl-for-content-extraction.md), [TROUBLESHOOTING.md § Firecrawl](TROUBLESHOOTING.md#firecrawl-issues) |
| **Installation** | [DEPLOYMENT.md](DEPLOYMENT.md), [FAQ § Installation](FAQ.md#installation) |
| **LLM models** | [environment_variables.md § LLM](environment_variables.md), [FAQ § Cost](FAQ.md#what-are-the-cheapest-models-that-work-well) |
| **MCP Server** | [mcp_server.md](mcp_server.md), [TROUBLESHOOTING.md § MCP](TROUBLESHOOTING.md#mcp-server-issues) |
| **Mobile API** | [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md), [First Mobile API Client Tutorial](tutorials/first-mobile-api-client.md) |
| **Multi-agent** | [multi_agent_architecture.md](multi_agent_architecture.md), [ADR-0005](adr/0005-multi-agent-llm-pipeline.md) |
| **OpenRouter** | [environment_variables.md § OpenRouter](environment_variables.md), [TROUBLESHOOTING.md § OpenRouter](TROUBLESHOOTING.md#openrouter-issues) |
| **Performance** | [How to optimize performance](how-to/optimize-performance.md), [TROUBLESHOOTING.md § Performance](TROUBLESHOOTING.md#performance-issues) |
| **Redis** | [How to setup Redis](how-to/setup-redis-caching.md), [TROUBLESHOOTING.md § Redis](TROUBLESHOOTING.md#redis-issues) |
| **Search** | [SPEC.md § Search](SPEC.md#search), [How to setup ChromaDB](how-to/setup-chroma-vector-search.md) |
| **Security** | [ADR-0003](adr/0003-single-user-access-control.md), [FAQ § Security](FAQ.md#security) |
| **Summary contract** | [SPEC.md § Summary JSON Contract](SPEC.md#summary-json-contract), [ADR-0002](adr/0002-strict-json-summary-contract.md) |
| **Testing** | [Local Development Tutorial § Testing](tutorials/local-development.md), [CLAUDE.md § Testing](../CLAUDE.md#testing) |
| **Troubleshooting** | [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [FAQ](FAQ.md) |
| **Web search** | [How to enable web search](how-to/enable-web-search.md), [FAQ § Web Search](FAQ.md#web-search) |
| **YouTube** | [How to configure YouTube](how-to/configure-youtube-download.md), [TROUBLESHOOTING.md § YouTube](TROUBLESHOOTING.md#youtube-issues) |

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

**Last Updated**: 2026-02-09

**Questions?** Check [FAQ](FAQ.md) or open an [issue](https://github.com/po4yka/bite-size-reader/issues).

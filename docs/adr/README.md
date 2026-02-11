# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for Bite-Size Reader.

## What are ADRs?

Architecture Decision Records document important architectural decisions made during the development of this project. Each ADR captures:

- **Context**: The problem or situation that necessitates a decision
- **Decision**: The chosen solution
- **Consequences**: The positive and negative outcomes of this decision
- **Alternatives**: Other options that were considered and why they weren't chosen

## ADR Format

We follow the [Michael Nygard ADR format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions). See [template.md](template.md) for the structure.

## ADR Status Workflow

- **Proposed**: Under discussion, not yet accepted
- **Accepted**: Decision has been made and is active
- **Deprecated**: Decision is no longer relevant but kept for historical context
- **Superseded**: Replaced by a newer decision (link to the superseding ADR)

## Index of ADRs

| ADR | Title | Status | Date |
| ----- | ------- | -------- | ------ |
| [ADR-0001](0001-use-firecrawl-for-content-extraction.md) | Use Firecrawl for Content Extraction | Accepted | 2024-12-15 |
| [ADR-0002](0002-strict-json-summary-contract.md) | Strict JSON Summary Contract | Accepted | 2024-12-18 |
| [ADR-0003](0003-single-user-access-control.md) | Single-User Access Control Model | Accepted | 2024-12-20 |
| [ADR-0004](0004-hexagonal-architecture.md) | Hexagonal Architecture Pattern | Accepted | 2025-01-10 |
| [ADR-0005](0005-multi-agent-llm-pipeline.md) | Multi-Agent LLM Processing Pipeline | Accepted | 2025-01-25 |

## Creating a New ADR

1. Copy `template.md` to a new file: `XXXX-short-title.md`
   - Use the next sequential number (e.g., `0006`)
   - Use kebab-case for the title
2. Fill in all sections of the template
3. Set status to "Proposed"
4. Submit as a pull request for team review
5. Once accepted, update status to "Accepted" and add to the index above
6. Link to related ADRs if applicable

## Updating Existing ADRs

ADRs should generally remain unchanged once accepted, as they represent decisions made at a specific point in time. However, you may:

- Add notes or updates in the "Notes" section with timestamps
- Change status to "Deprecated" or "Superseded" when a decision is no longer active
- Fix typos or clarify wording (document in Update Log)

**Never delete ADRs** - they provide valuable historical context even when superseded.

## Benefits of ADRs

- **Knowledge Preservation**: Captures why decisions were made, preventing "why did we do this?" questions
- **Onboarding**: Helps new team members understand architectural choices
- **Decision Quality**: Forces structured thinking about alternatives and consequences
- **Communication**: Creates a shared understanding across the team
- **Historical Context**: Preserves decision-making context for future reference

## Related Documentation

- [SPEC.md](../SPEC.md) - Technical specification (what the system does)
- [HEXAGONAL_ARCHITECTURE_QUICKSTART.md](../HEXAGONAL_ARCHITECTURE_QUICKSTART.md) - Architecture overview
- [multi_agent_architecture.md](../multi_agent_architecture.md) - Multi-agent system design
- [CLAUDE.md](../../CLAUDE.md) - AI assistant guide

---

**Note**: ADRs document *why* architectural decisions were made. For technical specifications (*what* the system does), see [SPEC.md](../SPEC.md).

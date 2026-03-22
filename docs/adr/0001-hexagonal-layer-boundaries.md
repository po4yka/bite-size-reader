# ADR 0001: Canonical Hexagonal Layer Boundaries

## Status

Accepted

## Context

The codebase had drifted into two competing architecture maps:

- hexagonal layering via `app/domain`, `app/application`, `app/adapters`, `app/infrastructure`, and `app/di`
- a parallel service/container map via `app/services`, adapter-side repository ports, and a monolithic DI container (since split into `app/di/*.py` modules)

That split made it easy for API, Telegram, CLI, scheduler, and MCP code to bypass application ports and assemble concrete repositories or service graphs locally.

## Decision

The canonical architecture is:

- `app/domain/`: business models and domain services
- `app/application/`: ports, use cases, DTOs, and application services
- `app/adapters/`: transports and external-facing adapters
- `app/infrastructure/`: concrete persistence, cache, vector search, messaging, and client implementations
- `app/di/`: composition roots only

Search and embedding workflows live under the canonical layers:

- `app/application/services/`: topic search, related reads, embedding orchestration, request workflows
- `app/infrastructure/search/`: vector and hybrid search implementations
- `app/infrastructure/embedding/`: embedding providers and factories

## Rules

Production code outside `app/di/` must not:

- assemble runtime graphs or own composition roots
- import `app.adapters.repository_ports`
- use `app.di.container`
- instantiate `Sqlite*RepositoryAdapter(...)` in core API, Telegram, or application workflows
- import the moved core search services from `app/services/`

## Consequences

- API and Telegram handlers resolve application services and repositories through `app/di/` or thin API dependency accessors.
- `app/services/` is no longer the canonical home for core search and embedding workflows.
- Compatibility shims may remain temporarily for tests or external import stability, but new production code must target the canonical layer locations.

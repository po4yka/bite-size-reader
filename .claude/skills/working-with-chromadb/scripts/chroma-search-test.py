"""Test ChromaDB semantic search from the command line.

Usage:
    python .claude/skills/working-with-chromadb/scripts/chroma-search-test.py "query text" [OPTIONS]

Options:
    --limit N    Max results (default: 10)
    --lang LANG  Language filter (en, ru, auto)
    --db PATH    SQLite database path (default: data/app.db)
"""

from __future__ import annotations

import asyncio
import sys


def parse_args(argv: list[str]) -> tuple[str, int, str | None, str]:
    if not argv or argv[0].startswith("--"):
        print("Usage: chroma-search-test.py QUERY [--limit N] [--lang LANG] [--db PATH]")
        raise SystemExit(1)

    query = argv[0]
    limit = 10
    lang = None
    db_path = "data/app.db"

    i = 1
    while i < len(argv):
        if argv[i] == "--limit" and i + 1 < len(argv):
            limit = int(argv[i + 1])
            i += 2
        elif argv[i] == "--lang" and i + 1 < len(argv):
            lang = argv[i + 1]
            i += 2
        elif argv[i] == "--db" and i + 1 < len(argv):
            db_path = argv[i + 1]
            i += 2
        else:
            print(f"Unknown argument: {argv[i]}")
            raise SystemExit(1)

    return query, limit, lang, db_path


async def run_search(query: str, limit: int, lang: str | None, db_path: str) -> int:
    from app.config.integrations import ChromaConfig, EmbeddingConfig
    from app.infrastructure.vector.chroma_store import ChromaVectorStore
    from app.services.chroma_vector_search_service import ChromaVectorSearchService
    from app.services.embedding_factory import create_embedding_service

    chroma_cfg = ChromaConfig()
    embedding_cfg = EmbeddingConfig()

    embedding_service = create_embedding_service(embedding_cfg)
    vector_store = ChromaVectorStore(
        host=chroma_cfg.host,
        auth_token=chroma_cfg.auth_token,
        environment=chroma_cfg.environment,
        user_scope=chroma_cfg.user_scope,
        collection_version=chroma_cfg.collection_version,
    )

    if not vector_store.available:
        print("ChromaDB: unreachable")
        return 1

    search_service = ChromaVectorSearchService(
        vector_store=vector_store,
        embedding_service=embedding_service,  # type: ignore[arg-type]
    )

    results = await search_service.search(query, language=lang, limit=limit)

    if not results.results:
        print(f"No results for: {query!r}")
        return 0

    print(f"Results for: {query!r} (lang={lang or 'auto'}, limit={limit})\n")
    for i, r in enumerate(results.results, 1):
        print(f"  [{i}] request_id={r.request_id}  similarity={r.similarity_score:.4f}")
        if r.title:
            print(f"      title: {r.title}")
        if r.url:
            print(f"      url: {r.url}")
        if r.snippet:
            print(f"      snippet: {r.snippet[:120]}...")
        if r.language:
            print(f"      lang: {r.language}")
        if r.tags:
            print(f"      tags: {', '.join(r.tags[:5])}")
        print()

    if results.has_more:
        print("  ... more results available (increase --limit)")

    return 0


def main() -> int:
    query, limit, lang, db_path = parse_args(sys.argv[1:])
    return asyncio.run(run_search(query, limit, lang, db_path))


if __name__ == "__main__":
    raise SystemExit(main())

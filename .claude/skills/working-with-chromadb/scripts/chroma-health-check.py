"""ChromaDB health check for dynamic context injection.

Prints compact status line suitable for skill dynamic context.
Exit 0 on success, 1 on failure.
"""

from __future__ import annotations


def main() -> int:
    try:
        from app.config.integrations import ChromaConfig

        cfg = ChromaConfig()
    except Exception as exc:
        print(f"ChromaDB: config error ({exc})")
        return 1

    try:
        import chromadb

        headers = {"Authorization": f"Bearer {cfg.auth_token}"} if cfg.auth_token else None
        client = chromadb.HttpClient(
            host=cfg.host,
            headers=headers,
            settings=chromadb.Settings(
                chroma_query_request_timeout_seconds=cfg.connection_timeout,
                anonymized_telemetry=False,
            ),
        )
        client.heartbeat()
    except Exception as exc:
        print(f"ChromaDB: unreachable ({exc})")
        return 1

    # Build collection name matching ChromaVectorStore convention
    safe_env = cfg.environment.replace(" ", "_")
    safe_scope = cfg.user_scope.replace(" ", "_")
    safe_ver = cfg.collection_version.replace(" ", "_")
    collection_name = f"notes_{safe_env}_{safe_scope}_{safe_ver}"

    try:
        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        doc_count = collection.count()
    except Exception as exc:
        print(f"ChromaDB: connected but collection error ({exc})")
        return 1

    print(
        f"ChromaDB: healthy | collection={collection_name} | docs={doc_count} | env={cfg.environment} | scope={cfg.user_scope}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

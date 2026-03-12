from app.infrastructure.vector.chroma_schemas import ChromaQueryFilters


def test_chroma_query_filters_strip_hash_prefix_from_tags() -> None:
    filters = ChromaQueryFilters(
        environment="dev",
        user_scope="public",
        tags=["#ai", "ml"],
    )

    assert filters.tags == ["ai", "ml"]
    assert filters.to_where() == {
        "$and": [
            {"environment": "dev"},
            {"user_scope": "public"},
            {"tags": {"$contains": "ai"}},
            {"tags": {"$contains": "ml"}},
        ]
    }

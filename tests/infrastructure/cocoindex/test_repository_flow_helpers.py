"""Tests for CocoIndex repository-flow helper parity."""

from __future__ import annotations

from app.infrastructure.cocoindex.flow import (
    _build_repository_payload,
    _extract_repository_text,
)
from app.infrastructure.embedding.repository_embedding import RepositoryEmbeddingGenerator


def test_extract_repository_text_matches_fast_path_order() -> None:
    row = {
        "full_name": "owner/repo",
        "description": "Demo repository",
        "topics_json": ["ai", "search"],
        "primary_language": "Python",
        "languages_json": {"Python": 1000, "TypeScript": 200},
        "analysis_json": {
            "purpose": "Indexes personal knowledge.",
            "tech_stack": ["FastAPI", "Qdrant"],
            "architecture_summary": "A compact API plus worker architecture.",
        },
        "readme_excerpt": "README details",
    }

    actual = _extract_repository_text(row)
    expected = RepositoryEmbeddingGenerator.compose_embedding_text(
        full_name="owner/repo",
        description="Demo repository",
        topics=["ai", "search"],
        primary_language="Python",
        languages=["Python", "TypeScript"],
        analysis=type(
            "Analysis",
            (),
            {
                "purpose": "Indexes personal knowledge.",
                "tech_stack": ["FastAPI", "Qdrant"],
                "architecture_summary": "A compact API plus worker architecture.",
            },
        )(),
        readme_excerpt="README details",
    )

    assert actual == expected


def test_build_repository_payload_matches_search_filter_fields() -> None:
    payload = _build_repository_payload(
        {
            "id": 7,
            "github_id": 99,
            "user_id": 12345,
            "full_name": "owner/repo",
            "primary_language": "Python",
            "topics_json": ["ai", "search"],
            "is_starred": True,
            "source": "starred",
            "created_at_github": None,
        },
        user_scope="public",
        environment="dev",
    )

    assert payload["entity_type"] == "repository"
    assert payload["repository_id"] == 7
    assert payload["user_id"] == 12345
    assert payload["source"] == "starred"
    assert payload["environment"] == "dev"
    assert payload["user_scope"] == "public"
    assert payload["topics"] == ["ai", "search"]

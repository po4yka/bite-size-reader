from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.summary_embedding_generator import SummaryEmbeddingGenerator


@pytest.fixture
def generator_fixture():
    embedding_service = MagicMock()
    embedding_service.get_model_name.return_value = "test-model"
    embedding_service.get_dimensions.return_value = 3
    embedding_service.generate_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
    embedding_service.serialize_embedding.return_value = b"serialized"

    with (
        patch(
            "app.services.summary_embedding_generator.SqliteEmbeddingRepositoryAdapter"
        ) as embedding_repo_cls,
        patch(
            "app.services.summary_embedding_generator.SqliteRequestRepositoryAdapter"
        ) as request_repo_cls,
        patch(
            "app.services.summary_embedding_generator.SqliteSummaryRepositoryAdapter"
        ) as summary_repo_cls,
    ):
        embedding_repo = MagicMock()
        embedding_repo.async_get_summary_embedding = AsyncMock(return_value=None)
        embedding_repo.async_create_or_update_summary_embedding = AsyncMock()
        request_repo = MagicMock()
        request_repo.async_get_request_by_id = AsyncMock(return_value=None)
        summary_repo = MagicMock()
        summary_repo.async_get_summary_by_request = AsyncMock(return_value=None)
        embedding_repo_cls.return_value = embedding_repo
        request_repo_cls.return_value = request_repo
        summary_repo_cls.return_value = summary_repo

        generator = SummaryEmbeddingGenerator(
            db=MagicMock(),
            embedding_service=embedding_service,
            model_version="2.0",
        )

    return generator, embedding_service, embedding_repo, request_repo, summary_repo


@pytest.mark.asyncio
async def test_generate_embedding_for_summary_skips_existing_matching_model(
    generator_fixture,
) -> None:
    generator, embedding_service, embedding_repo, _, _ = generator_fixture
    embedding_repo.async_get_summary_embedding.return_value = {
        "model_name": "test-model",
        "dimensions": 3,
    }

    created = await generator.generate_embedding_for_summary(
        10,
        {"summary_250": "Summary text"},
        language="en",
    )

    assert created is False
    embedding_service.generate_embedding.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_embedding_for_summary_regenerates_when_dimensions_change(
    generator_fixture,
) -> None:
    generator, embedding_service, embedding_repo, _, _ = generator_fixture
    embedding_repo.async_get_summary_embedding.return_value = {
        "model_name": "test-model",
        "dimensions": 768,
    }

    created = await generator.generate_embedding_for_summary(
        10,
        {"summary_250": "Summary text"},
        language="en",
    )

    assert created is True
    embedding_service.generate_embedding.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_embedding_for_summary_returns_false_for_empty_prepared_text(
    generator_fixture,
) -> None:
    generator, embedding_service, _, _, _ = generator_fixture

    with patch(
        "app.services.summary_embedding_generator.prepare_text_for_embedding", return_value=""
    ):
        created = await generator.generate_embedding_for_summary(10, {"summary_250": "ignored"})

    assert created is False
    embedding_service.generate_embedding.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_embedding_for_summary_persists_generated_vector(generator_fixture) -> None:
    generator, embedding_service, embedding_repo, _, _ = generator_fixture

    created = await generator.generate_embedding_for_summary(
        11,
        {
            "summary_1000": "Detailed summary",
            "topic_tags": ["#ai"],
            "metadata": {"title": "Title"},
        },
        language="ru",
        force=True,
    )

    assert created is True
    embedding_service.generate_embedding.assert_awaited_once()
    embedding_repo.async_create_or_update_summary_embedding.assert_awaited_once_with(
        summary_id=11,
        embedding_blob=b"serialized",
        model_name="test-model",
        model_version="2.0",
        dimensions=3,
        language="ru",
    )


@pytest.mark.asyncio
async def test_generate_embedding_for_summary_handles_embedding_errors(generator_fixture) -> None:
    generator, embedding_service, _, _, _ = generator_fixture
    embedding_service.generate_embedding.side_effect = RuntimeError("boom")

    created = await generator.generate_embedding_for_summary(
        12,
        {"summary_250": "Summary text"},
    )

    assert created is False


@pytest.mark.asyncio
async def test_generate_embedding_for_request_handles_missing_request_summary_or_payload(
    generator_fixture,
) -> None:
    generator, _, _, request_repo, summary_repo = generator_fixture

    request_repo.async_get_request_by_id.return_value = None
    assert await generator.generate_embedding_for_request(100) is False

    request_repo.async_get_request_by_id.return_value = {"id": 100, "lang_detected": "en"}
    summary_repo.async_get_summary_by_request.return_value = None
    assert await generator.generate_embedding_for_request(100) is False

    summary_repo.async_get_summary_by_request.return_value = {"id": 5, "json_payload": None}
    assert await generator.generate_embedding_for_request(100) is False


@pytest.mark.asyncio
async def test_generate_embedding_for_request_delegates_to_summary_generation(
    generator_fixture,
) -> None:
    generator, _, _, request_repo, summary_repo = generator_fixture
    request_repo.async_get_request_by_id.return_value = {"id": 101, "lang_detected": "en"}
    summary_repo.async_get_summary_by_request.return_value = {
        "id": 9,
        "json_payload": {"summary_250": "Summary text"},
    }

    with patch.object(
        generator, "generate_embedding_for_summary", new=AsyncMock(return_value=True)
    ) as generate:
        created = await generator.generate_embedding_for_request(101, force=True)

    assert created is True
    generate.assert_awaited_once_with(
        summary_id=9,
        payload={"summary_250": "Summary text"},
        language="en",
        force=True,
    )

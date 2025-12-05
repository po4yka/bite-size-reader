import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Mock chromadb to bypass environment issues
mock_chromadb = MagicMock()
mock_chromadb.errors.ChromaError = Exception
sys.modules["chromadb"] = mock_chromadb
sys.modules["chromadb.errors"] = mock_chromadb.errors

from app.services.chroma_vector_search_service import ChromaVectorSearchService  # noqa: E402


@pytest.mark.asyncio
async def test_find_duplicates():
    # Setup mocks
    vector_store = MagicMock()
    embedding_service = MagicMock()
    embedding_service.generate_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])

    service = ChromaVectorSearchService(
        vector_store=vector_store, embedding_service=embedding_service
    )

    # Mock query results
    # query returns dict with ids, metadatas, distances
    mock_results = {
        "ids": [["id1", "id2"]],
        "metadatas": [
            [
                {"text": "similar note 1", "request_id": 1, "summary_id": 101},
                {"text": "similar note 2", "request_id": 2, "summary_id": 102},
            ]
        ],
        "distances": [[0.05, 0.08]],  # 0.95 and 0.92 similarity
    }
    vector_store.query.return_value = mock_results

    # Execute
    duplicates = await service.find_duplicates("some text", threshold=0.9)

    # Verify
    # detect_language likely returns 'en' for "some text" or defaults
    embedding_service.generate_embedding.assert_awaited_once()
    args, _ = embedding_service.generate_embedding.call_args
    assert args[0] == "some text"

    vector_store.query.assert_called_once()

    # Check results
    assert len(duplicates) == 2
    assert duplicates[0].request_id == 1
    assert duplicates[0].similarity_score == pytest.approx(0.95)  # 1 - 0.05
    assert duplicates[1].request_id == 2
    assert duplicates[1].similarity_score == pytest.approx(0.92)  # 1 - 0.08


@pytest.mark.asyncio
async def test_find_duplicates_filters_by_threshold():
    # Setup mocks
    vector_store = MagicMock()
    embedding_service = MagicMock()
    embedding_service.generate_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])

    service = ChromaVectorSearchService(
        vector_store=vector_store, embedding_service=embedding_service
    )

    # Mock query results
    mock_results = {
        "ids": [["id1", "id2"]],
        "metadatas": [
            [
                {"text": "highly similar", "request_id": 1, "summary_id": 101},
                {"text": "somewhat similar", "request_id": 2, "summary_id": 102},
            ]
        ],
        "distances": [[0.05, 0.2]],  # 0.95 and 0.8 similarity
    }
    vector_store.query.return_value = mock_results

    # Execute with threshold 0.9
    duplicates = await service.find_duplicates("some text", threshold=0.9)

    # Verify
    assert len(duplicates) == 1
    assert duplicates[0].request_id == 1
    assert duplicates[0].similarity_score > 0.9

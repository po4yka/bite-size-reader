import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest

# Mock chromadb to bypass environment issues (numpy/pydantic mismatches)
mock_chromadb = MagicMock()
mock_chromadb.HttpClient = MagicMock
mock_chromadb.errors.ChromaError = Exception
sys.modules["chromadb"] = mock_chromadb
sys.modules["chromadb.errors"] = mock_chromadb.errors

from app.config import ChromaConfig  # noqa: E402

# Now we can import the store
from app.infrastructure.vector.chroma_store import ChromaVectorStore  # noqa: E402

# Use a unique collection name for testing to avoid conflicts
TEST_ENV = "test_integration"
TEST_USER_SCOPE = f"user_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def chroma_config():
    return ChromaConfig(
        host="http://localhost:8000",
        environment=TEST_ENV,
        user_scope=TEST_USER_SCOPE,
    )


@pytest.fixture
def vector_store(chroma_config):
    # Setup mock client
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection

    # Patch HttpClient to return our mock
    with patch(
        "app.infrastructure.vector.chroma_store.chromadb.HttpClient", return_value=mock_client
    ):
        store = ChromaVectorStore(
            host=chroma_config.host,
            auth_token=chroma_config.auth_token,
            environment=chroma_config.environment,
            user_scope=chroma_config.user_scope,
        )
        # Attach mocks to store for assertions
        store._client = mock_client
        store._collection = mock_collection
        yield store


def test_health_check(vector_store):
    vector_store._client.heartbeat.return_value = 12345
    assert vector_store.health_check() is True
    vector_store._client.heartbeat.assert_called_once()


def test_upsert_and_query(vector_store):
    # Data
    vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    metadatas = [
        {"request_id": 1, "text": "note 1", "user_scope": TEST_USER_SCOPE},
        {"request_id": 2, "text": "note 2", "user_scope": TEST_USER_SCOPE},
    ]
    ids = ["id1", "id2"]

    # Upsert
    vector_store.upsert_notes(vectors, metadatas, ids=ids)

    # Verify upsert call
    vector_store._collection.upsert.assert_called_once()
    call_args = vector_store._collection.upsert.call_args[1]
    assert call_args["embeddings"] == vectors
    assert call_args["metadatas"] == metadatas
    assert call_args["ids"] == ids

    # Query
    mock_results = {
        "ids": [["id1"]],
        "metadatas": [[{"text": "note 1"}]],
        "distances": [[0.1]],
    }
    vector_store._collection.query.return_value = mock_results

    results = vector_store.query(query_vector=[0.1, 0.2, 0.3], filters=None, top_k=1)

    assert results == mock_results
    vector_store._collection.query.assert_called_once()


def test_delete_by_request_id(vector_store):
    # Delete
    vector_store.delete_by_request_id(123)

    # Verify delete call
    vector_store._collection.delete.assert_called_once()
    call_args = vector_store._collection.delete.call_args[1]
    assert call_args["where"] == {"request_id": 123}


def test_reset(vector_store):
    # Mock count behavior: first call returns 1, second call returns 0
    vector_store._collection.count.side_effect = [1, 0]

    assert vector_store.count() == 1

    vector_store.reset()

    vector_store._client.delete_collection.assert_called_once()
    vector_store._client.get_or_create_collection.assert_called()

    assert vector_store.count() == 0

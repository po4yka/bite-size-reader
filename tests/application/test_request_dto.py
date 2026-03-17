"""Tests for request DTOs."""

from __future__ import annotations

from app.application.dto.request_dto import CreateRequestDTO, RequestDTO
from app.domain.models.request import Request, RequestStatus, RequestType


def test_create_request_dto_to_domain_model_url() -> None:
    dto = CreateRequestDTO(
        user_id=1,
        chat_id=100,
        request_type="url",
        input_url="https://example.com",
        normalized_url="https://example.com",
        dedupe_hash="abc123",
        correlation_id="corr-1",
    )
    model = dto.to_domain_model()
    assert isinstance(model, Request)
    assert model.user_id == 1
    assert model.chat_id == 100
    assert model.request_type == RequestType.URL
    assert model.status == RequestStatus.PENDING
    assert model.input_url == "https://example.com"
    assert model.correlation_id == "corr-1"


def test_create_request_dto_to_domain_model_forward() -> None:
    dto = CreateRequestDTO(
        user_id=2,
        chat_id=200,
        request_type="forward",
        content_text="Some content",
        fwd_from_chat_id=999,
        fwd_from_msg_id=42,
    )
    model = dto.to_domain_model()
    assert model.request_type == RequestType.FORWARD
    assert model.content_text == "Some content"
    assert model.fwd_from_chat_id == 999
    assert model.fwd_from_msg_id == 42


def test_request_dto_from_domain_model() -> None:
    domain = Request(
        id=5,
        user_id=10,
        chat_id=20,
        request_type=RequestType.URL,
        status=RequestStatus.COMPLETED,
        input_url="https://example.org",
        normalized_url="https://example.org",
        dedupe_hash="def456",
        correlation_id="corr-2",
        lang_detected="en",
    )
    dto = RequestDTO.from_domain_model(domain)
    assert dto.request_id == 5
    assert dto.user_id == 10
    assert dto.request_type == "url"
    assert dto.status == "ok"
    assert dto.input_url == "https://example.org"
    assert dto.lang_detected == "en"


def test_request_dto_roundtrip() -> None:
    domain = Request(
        id=7,
        user_id=3,
        chat_id=30,
        request_type=RequestType.URL,
        status=RequestStatus.PENDING,
        correlation_id="corr-3",
    )
    dto = RequestDTO.from_domain_model(domain)
    reconstructed = dto.to_domain_model()
    assert reconstructed.request_type == domain.request_type
    assert reconstructed.status == domain.status
    assert reconstructed.correlation_id == domain.correlation_id

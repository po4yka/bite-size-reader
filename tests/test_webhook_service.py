# ruff: noqa: RUF059
import pytest

from app.domain.services.webhook_service import (
    build_webhook_payload,
    generate_webhook_secret,
    sign_payload,
    validate_webhook_url,
    verify_signature,
)


class TestGenerateWebhookSecret:
    def test_returns_64_char_hex_string(self):
        secret = generate_webhook_secret()
        assert len(secret) == 64
        assert all(c in "0123456789abcdef" for c in secret)

    def test_different_on_each_call(self):
        s1 = generate_webhook_secret()
        s2 = generate_webhook_secret()
        assert s1 != s2


class TestSignPayload:
    def test_consistent_for_same_input(self):
        secret = "test-secret"
        payload = b'{"event": "test"}'
        sig1 = sign_payload(secret, payload)
        sig2 = sign_payload(secret, payload)
        assert sig1 == sig2

    def test_different_for_different_payload(self):
        secret = "test-secret"
        sig1 = sign_payload(secret, b"payload-a")
        sig2 = sign_payload(secret, b"payload-b")
        assert sig1 != sig2

    def test_different_for_different_secret(self):
        payload = b"same-payload"
        sig1 = sign_payload("secret-a", payload)
        sig2 = sign_payload("secret-b", payload)
        assert sig1 != sig2


class TestVerifySignature:
    def test_valid_signature(self):
        secret = "my-secret"
        payload = b'{"data": "value"}'
        sig = sign_payload(secret, payload)
        assert verify_signature(secret, payload, sig) is True

    def test_invalid_signature(self):
        secret = "my-secret"
        payload = b'{"data": "value"}'
        assert verify_signature(secret, payload, "bad-signature") is False

    def test_tampered_payload(self):
        secret = "my-secret"
        original = b'{"data": "value"}'
        sig = sign_payload(secret, original)
        tampered = b'{"data": "tampered"}'
        assert verify_signature(secret, tampered, sig) is False


class TestValidateWebhookUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/webhook",
            "http://localhost:8000/hook",
            "https://api.example.com:8443/hook",
            "http://127.0.0.1/hook",
        ],
    )
    def test_valid_urls(self, url):
        valid, error = validate_webhook_url(url)
        assert valid is True
        assert error is None

    def test_rejects_ftp_scheme(self):
        valid, error = validate_webhook_url("ftp://example.com")
        assert valid is False
        assert error is not None

    def test_rejects_private_ip(self):
        valid, error = validate_webhook_url("http://10.0.0.1/hook")
        assert valid is False

    def test_rejects_private_ip_192(self):
        valid, error = validate_webhook_url("http://192.168.1.1/hook")
        assert valid is False

    def test_rejects_empty_string(self):
        valid, error = validate_webhook_url("")
        assert valid is False

    def test_rejects_no_scheme(self):
        valid, error = validate_webhook_url("example.com/webhook")
        assert valid is False

    def test_rejects_http_non_localhost(self):
        valid, error = validate_webhook_url("http://example.com/hook")
        assert valid is False


class TestBuildWebhookPayload:
    def test_has_required_keys(self):
        payload = build_webhook_payload("summary.created", {"id": 1})
        assert "event" in payload
        assert "timestamp" in payload
        assert "data" in payload

    def test_event_type_matches(self):
        payload = build_webhook_payload("summary.created", {"id": 1})
        assert payload["event"] == "summary.created"

    def test_data_matches(self):
        data = {"id": 42, "title": "Test"}
        payload = build_webhook_payload("test.event", data)
        assert payload["data"] == data

    def test_timestamp_is_iso_format(self):
        from datetime import datetime

        payload = build_webhook_payload("test.event", {})
        # Should parse without error
        datetime.fromisoformat(payload["timestamp"])

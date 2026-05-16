"""Fernet symmetric encryption for at-rest secrets (e.g., GitHub PAT, OAuth access tokens).

Key loading is lazy and cached. The first call validates the configured key.
Missing key raises `MissingEncryptionKeyError` with a hint to generate one.

Key rotation (zero-downtime):
1. Generate a new key: ``python tools/scripts/generate_github_encryption_key.py``
2. Set the new key as ``GITHUB_TOKEN_ENCRYPTION_KEY``.
3. Move the old key to ``GITHUB_TOKEN_PREVIOUS_KEYS`` (comma-separated; multiple old keys OK).
4. Deploy — existing ciphertexts still decrypt; new writes use the new key.
5. Backfill: ``python -m app.cli.rotate_github_tokens``
6. Remove the old key from ``GITHUB_TOKEN_PREVIOUS_KEYS`` and redeploy.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

__all__ = [
    "InvalidEncryptedTokenError",
    "MissingEncryptionKeyError",
    "decrypt_token",
    "encrypt_token",
    "reset_key_cache",
]


class MissingEncryptionKeyError(RuntimeError):
    """Raised when GITHUB_TOKEN_ENCRYPTION_KEY is unset or malformed."""


class InvalidEncryptedTokenError(ValueError):
    """Raised when a ciphertext cannot be decrypted (key change, corruption, tampering)."""


def _parse_previous_keys(raw: str | None) -> list[Fernet]:
    """Parse comma-separated previous Fernet keys.  Returns [] when *raw* is empty."""
    if not raw:
        return []
    result: list[Fernet] = []
    for i, part in enumerate(p.strip() for p in raw.split(",") if p.strip()):
        encoded = part.encode("utf-8") if isinstance(part, str) else part
        try:
            result.append(Fernet(encoded))
        except (ValueError, TypeError) as exc:
            raise MissingEncryptionKeyError(
                f"GITHUB_TOKEN_PREVIOUS_KEYS[{i}] is malformed "
                f"(must be 32 url-safe base64 bytes). Underlying error: {exc}"
            ) from exc
    return result


@lru_cache(maxsize=1)
def _get_multi_fernet() -> MultiFernet:
    from app.config.settings import load_config

    settings = load_config(allow_stub_telegram=True)
    secret = settings.github.token_encryption_key
    if secret is None:
        raise MissingEncryptionKeyError(
            "GITHUB_TOKEN_ENCRYPTION_KEY is not configured. "
            "Generate one with: python tools/scripts/generate_github_encryption_key.py "
            "and set it in your .env file."
        )
    raw_value = secret.get_secret_value()
    raw = raw_value.encode("utf-8") if isinstance(raw_value, str) else raw_value
    try:
        primary = Fernet(raw)
    except (ValueError, TypeError) as exc:
        raise MissingEncryptionKeyError(
            f"GITHUB_TOKEN_ENCRYPTION_KEY is malformed (must be 32 url-safe base64 bytes). "
            f"Generate one with: python tools/scripts/generate_github_encryption_key.py. "
            f"Underlying error: {exc}"
        ) from exc

    prev_secret = settings.github.token_previous_keys
    prev_raw = prev_secret.get_secret_value() if prev_secret is not None else None
    previous = _parse_previous_keys(prev_raw)

    return MultiFernet([primary, *previous])


def encrypt_token(plaintext: str) -> bytes:
    """Encrypt a token string with the primary key. Returns Fernet ciphertext bytes."""
    if not plaintext:
        raise ValueError("Cannot encrypt empty plaintext")
    return _get_multi_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_token(ciphertext: bytes) -> str:
    """Decrypt previously encrypted ciphertext. Tries primary key then all previous keys."""
    try:
        return _get_multi_fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise InvalidEncryptedTokenError("Ciphertext could not be decrypted") from exc


def reset_key_cache() -> None:
    """Clear the cached MultiFernet instance and the settings config cache. For tests."""
    _get_multi_fernet.cache_clear()
    from app.config.settings import clear_config_cache

    clear_config_cache()

"""Fernet symmetric encryption for at-rest secrets (e.g., GitHub PAT, OAuth access tokens).

Key loading is lazy and cached. The first call validates the configured key.
Missing key raises `MissingEncryptionKeyError` with a hint to generate one.

Key rotation: this module currently supports a single Fernet key. To rotate without
re-encrypting all existing rows, migrate to `cryptography.fernet.MultiFernet`:
construct with `MultiFernet([new_key, old_key])`. New writes use new_key; existing
ciphertexts encrypted with old_key still decrypt successfully. Once a backfill
re-encrypts all rows under new_key, drop old_key.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

__all__ = [
    "InvalidEncryptedTokenError",
    "MissingEncryptionKeyError",
    "decrypt_token",
    "encrypt_token",
]


class MissingEncryptionKeyError(RuntimeError):
    """Raised when GITHUB_TOKEN_ENCRYPTION_KEY is unset and crypto is requested."""


class InvalidEncryptedTokenError(ValueError):
    """Raised when a ciphertext cannot be decrypted (key change, corruption, tampering)."""


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
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
        return Fernet(raw)
    except (ValueError, TypeError) as e:
        raise MissingEncryptionKeyError(
            f"GITHUB_TOKEN_ENCRYPTION_KEY is malformed (must be 32 url-safe base64 bytes). "
            f"Generate one with: python tools/scripts/generate_github_encryption_key.py. "
            f"Underlying error: {e}"
        ) from e


def encrypt_token(plaintext: str) -> bytes:
    """Encrypt a token string. Returns Fernet ciphertext bytes."""
    if not plaintext:
        raise ValueError("Cannot encrypt empty plaintext")
    return _get_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_token(ciphertext: bytes) -> str:
    """Decrypt previously encrypted ciphertext. Returns the plaintext string."""
    try:
        return _get_fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as e:
        raise InvalidEncryptedTokenError("Ciphertext could not be decrypted") from e


def reset_key_cache() -> None:
    """Clear the cached Fernet instance and the settings config cache. For tests."""
    _get_fernet.cache_clear()
    from app.config.settings import clear_config_cache

    clear_config_cache()

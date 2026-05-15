"""Fernet encryption/decryption for backup archives at rest."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

__all__ = [
    "FERNET_MAGIC",
    "InvalidBackupCiphertextError",
    "MissingBackupEncryptionKeyError",
    "decrypt_backup",
    "encrypt_backup",
    "is_fernet_ciphertext",
]

FERNET_MAGIC = b"gAAAAA"


class InvalidBackupCiphertextError(ValueError):
    """Raised when a backup ciphertext cannot be decrypted (wrong key or corruption)."""


class MissingBackupEncryptionKeyError(RuntimeError):
    """Raised by callers when BACKUP_ENCRYPTION_KEY is not configured and encryption is needed."""


def _fernet(key: SecretStr) -> Fernet:
    from cryptography.fernet import Fernet

    return Fernet(key.get_secret_value().encode())


def is_fernet_ciphertext(data: bytes) -> bool:
    """Return True if *data* starts with the Fernet token prefix."""
    return data[:6] == FERNET_MAGIC


def encrypt_backup(zip_bytes: bytes, key: SecretStr) -> bytes:
    """Fernet-encrypt *zip_bytes* and return opaque ciphertext bytes."""
    return _fernet(key).encrypt(zip_bytes)


def decrypt_backup(data: bytes, key: SecretStr) -> bytes:
    """Decrypt Fernet *data* and return raw ZIP bytes.

    Raises InvalidBackupCiphertextError on wrong key or corrupted ciphertext.
    """
    from cryptography.fernet import InvalidToken

    try:
        return _fernet(key).decrypt(data)
    except InvalidToken as exc:
        raise InvalidBackupCiphertextError(
            "Could not decrypt backup archive (wrong key or corrupted ciphertext)"
        ) from exc

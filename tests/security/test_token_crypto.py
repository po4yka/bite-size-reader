import pytest
from cryptography.fernet import Fernet

from app.security.token_crypto import (
    InvalidEncryptedTokenError,
    MissingEncryptionKeyError,
    decrypt_token,
    encrypt_token,
    reset_key_cache,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    # Pre-reset is the real protection: ensures a clean state even if the previous
    # test's teardown reset fired while monkeypatched env vars were still active.
    reset_key_cache()
    yield
    reset_key_cache()


def _set_valid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))


def test_encrypt_decrypt_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_valid_key(monkeypatch)
    plaintext = "ghp_thisIsATestToken12345"
    ct = encrypt_token(plaintext)
    assert isinstance(ct, bytes)
    assert ct != plaintext.encode()
    assert decrypt_token(ct) == plaintext


def test_missing_key_raises_at_use(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN_ENCRYPTION_KEY", raising=False)
    with pytest.raises(MissingEncryptionKeyError):
        encrypt_token("anything")


def test_malformed_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", "not-a-valid-fernet-key")
    with pytest.raises(MissingEncryptionKeyError):
        encrypt_token("x")


def test_invalid_ciphertext_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_valid_key(monkeypatch)
    with pytest.raises(InvalidEncryptedTokenError):
        decrypt_token(b"this is not a valid ciphertext")


def test_decrypt_with_different_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_valid_key(monkeypatch)
    ct = encrypt_token("secret")
    reset_key_cache()
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    with pytest.raises(InvalidEncryptedTokenError):
        decrypt_token(ct)


def test_empty_plaintext_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_valid_key(monkeypatch)
    with pytest.raises(ValueError):
        encrypt_token("")


def test_decrypt_with_previous_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ciphertext produced by an old key decrypts when that key is in PREVIOUS_KEYS."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    old_ct = Fernet(old_key).encrypt(b"ghp_old_secret")

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key.decode("ascii"))
    monkeypatch.setenv("GITHUB_TOKEN_PREVIOUS_KEYS", old_key.decode("ascii"))

    assert decrypt_token(old_ct) == "ghp_old_secret"


def test_encrypt_uses_primary_key_not_previous(monkeypatch: pytest.MonkeyPatch) -> None:
    """encrypt_token always produces ciphertext readable by the primary key alone."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key.decode("ascii"))
    monkeypatch.setenv("GITHUB_TOKEN_PREVIOUS_KEYS", old_key.decode("ascii"))

    ct = encrypt_token("ghp_test")
    # primary-key-only Fernet must decrypt it successfully
    assert Fernet(new_key).decrypt(ct) == b"ghp_test"


def test_old_ciphertext_fails_without_previous_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Old-key ciphertext raises when old key is absent from PREVIOUS_KEYS."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    old_ct = Fernet(old_key).encrypt(b"ghp_secret")

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key.decode("ascii"))
    monkeypatch.delenv("GITHUB_TOKEN_PREVIOUS_KEYS", raising=False)

    with pytest.raises(InvalidEncryptedTokenError):
        decrypt_token(old_ct)


def test_multiple_previous_keys_all_decrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Comma-separated previous keys: each old ciphertext decrypts successfully."""
    k1, k2, new_key = Fernet.generate_key(), Fernet.generate_key(), Fernet.generate_key()
    ct1 = Fernet(k1).encrypt(b"token_from_k1")
    ct2 = Fernet(k2).encrypt(b"token_from_k2")

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key.decode("ascii"))
    monkeypatch.setenv(
        "GITHUB_TOKEN_PREVIOUS_KEYS",
        f"{k1.decode('ascii')},{k2.decode('ascii')}",
    )

    assert decrypt_token(ct1) == "token_from_k1"
    assert decrypt_token(ct2) == "token_from_k2"


def test_malformed_previous_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed entry in GITHUB_TOKEN_PREVIOUS_KEYS raises MissingEncryptionKeyError."""
    new_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key)
    monkeypatch.setenv("GITHUB_TOKEN_PREVIOUS_KEYS", "not-a-valid-fernet-key")

    with pytest.raises(MissingEncryptionKeyError):
        encrypt_token("x")

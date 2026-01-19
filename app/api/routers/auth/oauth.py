"""
OAuth provider verification (Apple, Google).
"""

import hashlib
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from app.api.exceptions import AuthenticationError
from app.core.logging_utils import get_logger

logger = get_logger(__name__)

# OAuth provider public key URLs
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
GOOGLE_KEYS_URL = "https://www.googleapis.com/oauth2/v3/certs"
APPLE_ISSUER = "https://appleid.apple.com"

# Cache for JWKS clients (thread-safe, handles key rotation automatically)
_apple_jwks_client: PyJWKClient | None = None
_google_jwks_client: PyJWKClient | None = None


def _get_apple_jwks_client() -> PyJWKClient:
    """Get or create Apple JWKS client."""
    global _apple_jwks_client
    if _apple_jwks_client is None:
        _apple_jwks_client = PyJWKClient(APPLE_KEYS_URL, cache_keys=True, lifespan=3600)
    return _apple_jwks_client


def _get_google_jwks_client() -> PyJWKClient:
    """Get or create Google JWKS client."""
    global _google_jwks_client
    if _google_jwks_client is None:
        _google_jwks_client = PyJWKClient(GOOGLE_KEYS_URL, cache_keys=True, lifespan=3600)
    return _google_jwks_client


def verify_apple_id_token(id_token: str, client_id: str) -> dict[str, Any]:
    """Verify an Apple Sign-In ID token and return the claims.

    Args:
        id_token: The JWT token from Apple Sign-In
        client_id: The expected audience (your app's bundle ID)

    Returns:
        Decoded token claims including 'sub' (user identifier)

    Raises:
        AuthenticationError: If token verification fails
    """
    try:
        jwks_client = _get_apple_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)

        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=APPLE_ISSUER,
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )

        logger.info(
            "Apple token verified successfully",
            extra={"sub": claims.get("sub"), "email": claims.get("email")},
        )
        return claims

    except PyJWTError as e:
        logger.warning(
            "Apple token verification failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise AuthenticationError(f"Invalid Apple ID token: {e}") from e
    except Exception as e:
        logger.error(
            "Apple token verification error",
            extra={"error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        raise AuthenticationError("Failed to verify Apple ID token") from e


def verify_google_id_token(id_token: str, client_id: str) -> dict[str, Any]:
    """Verify a Google Sign-In ID token and return the claims.

    Args:
        id_token: The JWT token from Google Sign-In
        client_id: The expected audience (your OAuth client ID)

    Returns:
        Decoded token claims including 'sub' (user identifier)

    Raises:
        AuthenticationError: If token verification fails
    """
    try:
        jwks_client = _get_google_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)

        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )

        # Additional Google-specific validation
        if not claims.get("email_verified", False):
            logger.warning(
                "Google token has unverified email",
                extra={"sub": claims.get("sub"), "email": claims.get("email")},
            )
            # Allow login but log warning - email verification is recommended

        logger.info(
            "Google token verified successfully",
            extra={
                "sub": claims.get("sub"),
                "email": claims.get("email"),
                "email_verified": claims.get("email_verified"),
            },
        )
        return claims

    except PyJWTError as e:
        logger.warning(
            "Google token verification failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise AuthenticationError(f"Invalid Google ID token: {e}") from e
    except Exception as e:
        logger.error(
            "Google token verification error",
            extra={"error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        raise AuthenticationError("Failed to verify Google ID token") from e


def derive_user_id_from_sub(provider: str, sub: str) -> int:
    """Derive a consistent numeric user ID from an OAuth provider's 'sub' claim.

    Args:
        provider: Provider name (e.g., 'apple', 'google')
        sub: The 'sub' (subject) claim from the ID token

    Returns:
        A consistent numeric user ID derived from the sub claim
    """
    # Combine provider and sub to ensure uniqueness across providers
    combined = f"{provider}:{sub}"
    # Use SHA256 to get a consistent hash, then take last 15 digits to stay within int range
    hash_hex = hashlib.sha256(combined.encode()).hexdigest()
    # Use modulo to keep within a reasonable range (positive int)
    return int(hash_hex, 16) % 10**15

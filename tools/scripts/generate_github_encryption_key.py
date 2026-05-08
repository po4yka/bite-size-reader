#!/usr/bin/env python3
"""Generate a new Fernet key for GITHUB_TOKEN_ENCRYPTION_KEY.

Usage:
    python tools/scripts/generate_github_encryption_key.py

Copy the output line into your .env file:
    GITHUB_TOKEN_ENCRYPTION_KEY=<generated-key>

Notes:
- Rotate by generating a new key, re-encrypting all existing tokens, then deleting the old key.
- Future versions may support `MultiFernet` for staged rotation; for now, single-key only.
"""

from __future__ import annotations

from cryptography.fernet import Fernet


def main() -> None:
    key = Fernet.generate_key().decode("ascii")
    print(f"GITHUB_TOKEN_ENCRYPTION_KEY={key}")


if __name__ == "__main__":
    main()

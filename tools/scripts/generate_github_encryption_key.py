#!/usr/bin/env python3
"""Generate a new Fernet key for GITHUB_TOKEN_ENCRYPTION_KEY.

Usage:
    python tools/scripts/generate_github_encryption_key.py

Copy the output line into your .env file:
    GITHUB_TOKEN_ENCRYPTION_KEY=<generated-key>

Zero-downtime key rotation procedure:
1. Generate a new key with this script.
2. In your .env / secret store:
   - Set GITHUB_TOKEN_ENCRYPTION_KEY=<new-key>
   - Set GITHUB_TOKEN_PREVIOUS_KEYS=<old-key>   (comma-separate multiple old keys)
3. Deploy (requires process restart) — existing ciphertexts still decrypt; new writes use the new key.
4. Run the backfill CLI to re-encrypt all stored tokens under the new key:
       python -m app.cli.rotate_github_tokens
   Use --dry-run first to preview, then run without it to commit.
5. Remove the old key from GITHUB_TOKEN_PREVIOUS_KEYS and redeploy.
   Old-key ciphertexts no longer exist after a successful backfill.
"""

from __future__ import annotations

from cryptography.fernet import Fernet


def main() -> None:
    key = Fernet.generate_key().decode("ascii")
    print(f"GITHUB_TOKEN_ENCRYPTION_KEY={key}")


if __name__ == "__main__":
    main()

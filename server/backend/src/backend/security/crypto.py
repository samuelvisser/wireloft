from __future__ import annotations

import base64
import os
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


ENV_SECRET_KEY = "WL_SECRET_KEY"


def _derive_key_from_env() -> bytes:
    """
    Load the application secret key from environment.
    Expects a 32-byte urlsafe base64 key for Fernet.
    If a raw (non-base64) 32-byte key is provided, base64-encode it.
    In development, if not provided, generates a new key per process.
    """
    raw = os.environ.get(ENV_SECRET_KEY, "").strip()
    if not raw:
        # Development fallback: generate ephemeral key
        key = Fernet.generate_key()
        # Warn through logs if available
        try:
            import logging
            logging.getLogger(__name__).warning(
                "%s not set; generating ephemeral key for this process. Tokens will not persist across restarts.",
                ENV_SECRET_KEY,
            )
        except Exception:
            pass
        return key

    # If it looks like a base64 fernet key (length ~44 and contains =), use as is
    try:
        # Try to decode as base64 and re-encode to normalize
        decoded = base64.urlsafe_b64decode(raw)
        if len(decoded) not in (16, 24, 32):
            # Fernet requires 32 bytes; if not, we will handle below
            pass
        normalized = base64.urlsafe_b64encode(decoded)
        return normalized
    except Exception:
        # Treat as plain text secret; pad/truncate to 32 bytes and base64-encode
        b = raw.encode("utf-8")
        if len(b) < 32:
            b = (b + b"\0" * 32)[:32]
        else:
            b = b[:32]
        return base64.urlsafe_b64encode(b)


@lru_cache(maxsize=1)
def get_fernet() -> Fernet:
    return Fernet(_derive_key_from_env())


def encrypt_text(plaintext: str | bytes | None) -> Optional[bytes]:
    if plaintext is None:
        return None
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    return get_fernet().encrypt(plaintext)


def decrypt_text(token: bytes | str | None) -> Optional[str]:
    if token is None:
        return None
    if isinstance(token, str):
        token_bytes = token.encode("utf-8")
    else:
        token_bytes = token
    try:
        return get_fernet().decrypt(token_bytes).decode("utf-8")
    except InvalidToken:
        return None

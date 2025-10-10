from __future__ import annotations

import base64
import binascii
import os
import logging
from pathlib import Path
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from wireloft_config import get_settings


def _normalize_to_fernet_key(raw: str | bytes) -> bytes:
    """
    Normalize secret material into a Fernet-compatible key (urlsafe base64 of 32 bytes).
    Accepts either a base64-encoded string/bytes or raw secret text.
    """
    if isinstance(raw, bytes):
        raw_text = raw.decode("utf-8", errors="ignore")
    else:
        raw_text = str(raw)

    # Try to decode as base64 and re-encode to normalize
    try:
        decoded = base64.urlsafe_b64decode(raw_text)
        if len(decoded) == 32:
            return base64.urlsafe_b64encode(decoded)
    except (binascii.Error, UnicodeEncodeError):
        pass

    # Treat as plain text secret; pad/truncate to 32 bytes and base64-encode
    b = raw_text.encode("utf-8")
    if len(b) < 32:
        b = (b + b"\0" * 32)[:32]
    else:
        b = b[:32]
    return base64.urlsafe_b64encode(b)


def _read_key_file(path: Path) -> Optional[bytes]:
    try:
        if path.exists() and path.is_file():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                return _normalize_to_fernet_key(content)
    except (OSError, UnicodeDecodeError) as e:
        logging.getLogger(__name__).warning("Failed to read WL secret key file at %s", path, e)
    return None


def _write_key_file(path: Path, key: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(key.decode("utf-8"), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except (OSError, PermissionError, NotImplementedError):
            # Not fatal, especially on Windows or restricted FS
            pass
    except (OSError, UnicodeError) as e:
        logging.getLogger(__name__).warning("Could not persist WL secret key to %s: %s", path, e)


def _derive_key_from_env() -> bytes:
    """
    Resolve the application secret key used for encrypting session tokens from central settings.

    Precedence:
    1. settings.crypto.secret_key: literal key material (either Fernet base64 or raw secret text)
    2. settings.crypto.secret_key_file: path to a file containing the key
    3. settings.crypto.default_secret_file

    If neither 1 nor 2 is provided and writing the default key file fails, an
    ephemeral key is generated and a warning is logged that tokens won't persist
    across restarts.
    """
    s = get_settings().crypto

    # 1) Literal from settings
    if getattr(s, "secret_key", None):
        return _normalize_to_fernet_key(s.secret_key)

    # 2/3) File path from settings
    path = Path(s.secret_key_file) if getattr(s, "secret_key_file", None) else Path(s.default_secret_file)

    # Try reading the existing file
    key_from_file = _read_key_file(path)
    if key_from_file:
        return key_from_file

    # Not present: generate and persist a new key
    key = Fernet.generate_key()
    try:
        _write_key_file(path, key)
        logging.getLogger(__name__).info(
            "No crypto.secret_key provided; generated persistent secret key at %s. Tokens will persist across restarts.",
            path,
        )
        return key
    except (OSError, UnicodeError) as e:
        # Fall back to an ephemeral key
        logging.getLogger(__name__).warning(
            "No crypto.secret_key provided and could not persist a key to %s; using ephemeral key. Tokens will not persist across restarts.",
            path, e
        )
        return key


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

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Optional

import keyring
from keyring.errors import PasswordDeleteError


@dataclass
class TokenRecord:
    access_token: str
    refresh_token: Optional[str]
    token_type: str
    expires_at: float  # epoch seconds
    scope: Optional[str] = None


class TokenStore:
    """
    Keyring-only token storage. No file fallback by design.
    Fails fast if the system keyring is unusable.
    """

    def __init__(self, service_name: str = "wireloft-dailywire-auth"):
        self.service_name = service_name
        # Basic sanity check: some keyring backends return None silently.
        try:
            backend = keyring.get_keyring()
            if backend is None:
                raise RuntimeError("No usable keyring backend found.")
        except Exception as e:
            raise RuntimeError("Failed to initialize keyring backend.") from e

    def _get(self, key: str) -> Optional[str]:
        try:
            return keyring.get_password(self.service_name, key)
        except Exception as e:
            raise RuntimeError("Failed to read from OS keyring.") from e

    def _set(self, key: str, value: str) -> None:
        try:
            keyring.set_password(self.service_name, key, value)
        except Exception as e:
            raise RuntimeError("Failed to write to OS keyring.") from e

    def _delete(self, key: str) -> None:
        try:
            keyring.delete_password(self.service_name, key)
        except PasswordDeleteError:
            # ignore if already gone
            return
        except Exception as e:
            raise RuntimeError("Failed to delete from OS keyring.") from e

    def load(self, key: str) -> Optional[TokenRecord]:
        raw = self._get(key)
        if not raw:
            return None
        d = json.loads(raw)
        return TokenRecord(**d)

    def save(self, key: str, record: TokenRecord) -> None:
        payload = json.dumps(asdict(record))
        self._set(key, payload)

    def delete(self, key: str) -> None:
        self._delete(key)

from typing import Optional
from .passwords import verify_scrypt
from ..registry import get_settings

class AdminAuth:
    def __init__(self, admin_password_hash: Optional[str] = None, *, pepper: str | None = None):
        self._hash = admin_password_hash or get_settings().admin_auth.password_hash
        self._pepper = pepper  # optional: append to password before verify

        if self._hash != get_settings().admin_auth.password_hash:
            self._is_enabled = bool(self._hash)
        else:
            self._is_enabled = get_settings().admin_auth.enabled

    @property
    def is_enabled(self) -> bool:
        return self._is_enabled

    def verify(self, candidate: str) -> bool:
        if not self.is_enabled:
            return False
        if self._pepper:
            candidate = candidate + self._pepper
        if self._hash.startswith("scrypt$"):
            return verify_scrypt(candidate, str(self._hash))
        return False

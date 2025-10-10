from typing import Literal, TypeAlias, Optional
from .passwords import verify_scrypt
from ..registry import get_settings

HashOrDisabled: TypeAlias = str | Literal[False]

class AdminAuth:
    def __init__(self, admin_password_hash: Optional[HashOrDisabled] = None, *, pepper: str | None = None):
        self._hash = admin_password_hash or get_settings().admin_password_hash
        self._pepper = pepper  # optional: append to password before verify

    def is_enabled(self) -> bool:
        return isinstance(self._hash, str)

    def verify(self, candidate: str) -> bool:
        if not self.is_enabled():
            return False
        if self._pepper:
            candidate = candidate + self._pepper
        if self._hash.startswith("scrypt$"):
            return verify_scrypt(candidate, str(self._hash))
        return False

from typing import Literal, TypeAlias
from .passwords import verify_scrypt

HashOrDisabled: TypeAlias = str | Literal[False]

class AdminAuth:
    def __init__(self, admin_password_hash: HashOrDisabled, *, pepper: str | None = None):
        self._hash = admin_password_hash
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

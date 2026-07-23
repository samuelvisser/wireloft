import base64, hashlib, secrets, binascii


def hash_password_scrypt(password: str, *, n=2**14, r=8, p=1, dklen=32) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=dklen)
    return f"scrypt${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(dk).decode()}"

def verify_scrypt(password: str, encoded: str) -> bool:
    try:
        # Extract scheme, salt, and derived key from encoded string
        parts = encoded.split("$", 2)
        if len(parts) != 3:
            return False
        scheme, salt_b64, dk_b64 = parts
        if scheme != "scrypt":
            return False

        # Verify derived key matches password
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(dk_b64.encode())
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=len(expected))
        return secrets.compare_digest(actual, expected)
    except (ValueError, binascii.Error, UnicodeEncodeError):
        return False

def derive_admin_password_client_value(password: str) -> str:
    """
    Mirror the frontend derivation used before sending to the API:
    - SHA-256 over UTF-8 password
    - base64url encode (RFC 4648 URL-safe), without padding
    Returns the base64url string.
    """
    digest = hashlib.sha256(password.encode()).digest()
    b64 = base64.urlsafe_b64encode(digest).decode()
    return b64.rstrip("=")
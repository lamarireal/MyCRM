import hashlib
import hmac
import secrets

from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
dummy_password_hash = password_hash.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return password_hash.verify(password, encoded_hash)


def verify_password_or_dummy(password: str, encoded_hash: str | None) -> bool:
    """Spend comparable work for unknown users to reduce login timing leaks."""
    return verify_password(password, encoded_hash or dummy_password_hash)


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str, secret_key: str) -> str:
    return hmac.new(secret_key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()

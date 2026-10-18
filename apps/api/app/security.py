import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request, Response

from app.config import get_settings

ACCESS_COOKIE = "av_access"
CSRF_COOKIE = "av_csrf"
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def csrf_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_csrf() -> str:
    nonce = secrets.token_urlsafe(32)
    signature = hmac.new(
        get_settings().jwt_secret.get_secret_value().encode(),
        f"csrf:{nonce}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{nonce}.{signature}"


def valid_csrf(token: str) -> bool:
    if not token or len(token) > 128 or not token.isascii():
        return False
    nonce, separator, signature = token.partition(".")
    expected = hmac.new(
        get_settings().jwt_secret.get_secret_value().encode(),
        f"csrf:{nonce}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return bool(nonce and separator) and hmac.compare_digest(signature, expected)


def validate_csrf(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if request.headers.get("origin") not in get_settings().origins:
        raise HTTPException(403, "Untrusted or missing request origin")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("x-csrf-token", "")
    if not valid_csrf(cookie) or not header.isascii() or not hmac.compare_digest(cookie, header):
        raise HTTPException(403, "Invalid CSRF token")


def set_cookie(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path="/",
    )


def issue_token(user_id: uuid.UUID, session_id: uuid.UUID, expires: datetime) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "jti": str(session_id),
            "iat": datetime.now(UTC),
            "exp": expires,
            "iss": "assetvision-api",
            "aud": "assetvision-web",
        },
        get_settings().jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def session_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=get_settings().access_token_expire_minutes)

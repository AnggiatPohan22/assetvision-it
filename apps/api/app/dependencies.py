import hmac
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AuthSession, Role, User
from app.security import ACCESS_COOKIE, CSRF_COOKIE, csrf_digest

Database = Annotated[Session, Depends(get_db)]
session_cookie = APIKeyCookie(
    name=ACCESS_COOKIE,
    scheme_name="SessionCookie",
    auto_error=False,
    description="HttpOnly session cookie issued by POST /api/v1/auth/login; no bearer auth.",
)


def current_session(
    request: Request,
    db: Database,
    token: Annotated[str | None, Security(session_cookie)],
) -> AuthSession:
    try:
        payload = jwt.decode(
            token or "",
            get_settings().jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience="assetvision-web",
            issuer="assetvision-api",
            options={"require": ["sub", "jti", "exp", "iat"]},
        )
        session = db.get(AuthSession, uuid.UUID(payload["jti"]))
        if (
            session is None
            or session.revoked
            or str(session.user_id) != payload["sub"]
            or session.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC)
        ):
            raise ValueError("Invalid session")
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(401, "Authentication required") from None
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not hmac.compare_digest(
        session.csrf_hash, csrf_digest(request.cookies.get(CSRF_COOKIE, ""))
    ):
        raise HTTPException(403, "CSRF token does not belong to this session")
    return session


def current_user(
    db: Database,
    session: Annotated[AuthSession, Depends(current_session)],
) -> User:
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "Authentication required")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_roles(*roles: Role) -> Callable[..., User]:
    def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Insufficient permissions")
        return user

    return check

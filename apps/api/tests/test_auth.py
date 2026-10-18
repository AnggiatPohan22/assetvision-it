import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from conftest import csrf_headers, session_headers, sign_in
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditEvent, AuthSession, Role, User
from app.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    hash_password,
    issue_token,
    new_csrf,
    verify_password,
)


def test_password_hashing() -> None:
    password = secrets.token_urlsafe(20)
    hashed = hash_password(password)
    assert hashed.startswith("$argon2id$")
    assert hashed != hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password(password, "invalid")


def test_login_me_and_cookie_security(client: TestClient, user: User, password: str) -> None:
    response = sign_in(client, password)
    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": "ADMIN",
    }
    assert "password" not in response.text
    assert "access_token" not in response.text
    for cookie in response.headers.get_list("set-cookie"):
        assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
        assert "Max-Age=900" in cookie
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/admin/status").status_code == 200
    assert response.headers["cache-control"] == "no-store"
    claims = jwt.decode(
        client.cookies[ACCESS_COOKIE],
        get_settings().jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience="assetvision-web",
        issuer="assetvision-api",
    )
    assert 0 < claims["exp"] - claims["iat"] <= 900


@pytest.mark.parametrize(
    "email,wrong",
    [
        ("admin@example.com", True),
        ("missing@example.com", False),
    ],
)
def test_invalid_credentials(
    client: TestClient,
    user: User,
    password: str,
    email: str,
    wrong: bool,
) -> None:
    response = sign_in(client, "wrong" if wrong else password, email)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert ACCESS_COOKIE not in client.cookies


def test_disabled_user(client: TestClient, db: Session, user: User, password: str) -> None:
    user.is_active = False
    db.commit()
    assert sign_in(client, password).status_code == 401


def test_disable_after_login(client: TestClient, db: Session, user: User, password: str) -> None:
    assert sign_in(client, password).status_code == 200
    user.is_active = False
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("path", ["/auth/me", "/auth/session", "/admin/status"])
def test_unauthorized(client: TestClient, path: str) -> None:
    assert client.get("/api/v1" + path).status_code == 401


@pytest.mark.parametrize("role", [Role.OFFICER, Role.VIEWER])
def test_admin_only(
    client: TestClient,
    db: Session,
    user: User,
    password: str,
    role: Role,
) -> None:
    user.role = role
    db.commit()
    assert sign_in(client, password).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.get("/api/v1/admin/status").status_code == 403


def test_role_change_is_immediate(
    client: TestClient,
    db: Session,
    user: User,
    password: str,
) -> None:
    assert sign_in(client, password).status_code == 200
    user.role = Role.VIEWER
    db.commit()
    assert client.get("/api/v1/admin/status").status_code == 403


@pytest.mark.parametrize("mode", ["missing", "mismatch", "unsigned", "foreign_origin", "no_origin"])
def test_login_csrf(client: TestClient, user: User, password: str, mode: str) -> None:
    headers = csrf_headers(client)
    if mode == "missing":
        headers.pop("X-CSRF-Token")
    elif mode == "mismatch":
        headers["X-CSRF-Token"] = "wrong"
    elif mode == "unsigned":
        client.cookies.set(CSRF_COOKIE, "forged", domain="localhost.local", path="/")
        headers["X-CSRF-Token"] = "forged"
    elif mode == "foreign_origin":
        headers["Origin"] = "http://evil.example"
    else:
        headers.pop("Origin")
    response = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": password}, headers=headers
    )
    assert response.status_code == 403
    assert ACCESS_COOKIE not in client.cookies


def test_logout_revokes_token_and_audits(
    client: TestClient,
    db: Session,
    user: User,
    password: str,
) -> None:
    assert sign_in(client, password).status_code == 200
    stolen_token = client.cookies[ACCESS_COOKIE]
    assert client.post("/api/v1/auth/logout", headers=session_headers(client)).status_code == 204
    assert ACCESS_COOKIE not in client.cookies
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set(ACCESS_COOKIE, stolen_token)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert set(db.scalars(select(AuditEvent.action))) == {"login", "logout"}


def test_logout_rejects_missing_or_unbound_csrf(
    client: TestClient,
    user: User,
    password: str,
) -> None:
    assert sign_in(client, password).status_code == 200
    assert (
        client.post("/api/v1/auth/logout", headers={"Origin": "http://localhost:3000"}).status_code
        == 403
    )
    # Even a valid anonymous token cannot mutate an authenticated session.
    other_token = new_csrf()
    client.cookies.set(CSRF_COOKIE, other_token, domain="localhost.local", path="/")
    assert (
        client.post(
            "/api/v1/auth/logout",
            headers={"Origin": "http://localhost:3000", "X-CSRF-Token": other_token},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/auth/me").status_code == 200


@pytest.mark.parametrize("mode", ["expired", "tampered", "unknown_session", "wrong_audience"])
def test_invalid_access_tokens(
    client: TestClient,
    db: Session,
    user: User,
    password: str,
    mode: str,
) -> None:
    assert sign_in(client, password).status_code == 200
    session = db.scalar(select(AuthSession))
    assert session is not None
    if mode == "expired":
        token = issue_token(user.id, session.id, datetime.now(UTC) - timedelta(seconds=1))
    elif mode == "tampered":
        token = client.cookies[ACCESS_COOKIE] + "x"
    elif mode == "unknown_session":
        token = issue_token(user.id, uuid.uuid4(), datetime.now(UTC) + timedelta(minutes=1))
    else:
        token = jwt.encode(
            {
                "sub": str(user.id),
                "jti": str(session.id),
                "iat": datetime.now(UTC),
                "exp": datetime.now(UTC) + timedelta(minutes=1),
                "aud": "wrong",
                "iss": "assetvision-api",
            },
            get_settings().jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
    client.cookies.clear()
    client.cookies.set(ACCESS_COOKIE, token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_validation_does_not_echo_password(client: TestClient) -> None:
    secret = secrets.token_urlsafe(20)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "bad", "password": secret},
        headers=csrf_headers(client),
    )
    assert response.status_code == 422
    assert secret not in response.text

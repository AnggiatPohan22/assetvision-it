import pytest
from conftest import session_headers, sign_in
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from app.models import User
from app.security import CSRF_COOKIE, validate_csrf


def test_csrf_bootstrap_keeps_authenticated_logout_working(
    client: TestClient,
    user: User,
    password: str,
) -> None:
    assert sign_in(client, password).status_code == 200
    token = client.cookies[CSRF_COOKIE]
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    assert response.json()["csrf_token"] == token
    assert "set-cookie" not in response.headers
    assert client.post("/api/v1/auth/logout", headers=session_headers(client)).status_code == 204


def test_non_ascii_csrf_is_forbidden_instead_of_server_error() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [
                (b"origin", b"http://localhost:3000"),
                (b"cookie", b"av_csrf=\xff"),
                (b"x-csrf-token", b"\xff"),
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        validate_csrf(request)
    assert exc.value.status_code == 403

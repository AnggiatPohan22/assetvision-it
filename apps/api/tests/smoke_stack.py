"""HTTP smoke against real API + Next.js using only the ephemeral test database."""

import os
import secrets
import subprocess
import sys

import httpx
from sqlalchemy import select
from sqlalchemy.engine import make_url

test_url = make_url(os.environ["TEST_DATABASE_URL"])
if test_url.database != "assetvision_test" or test_url.host != "db-test":
    raise SystemExit("Smoke tests require the isolated test database")

os.environ["DATABASE_URL"] = test_url.set(
    password=os.environ["POSTGRES_PASSWORD"]
).render_as_string(hide_password=False)
sys.path.insert(0, os.getcwd())
from app.db import SessionLocal  # noqa: E402
from app.models import Role, User  # noqa: E402

password = secrets.token_urlsafe(24)
email = "smoke@example.com"
for expected in ("Initial admin created", "Active admin already exists; unchanged"):
    result = subprocess.run(
        [sys.executable, "-m", "app.bootstrap", "--email", email, "--name", "Smoke Admin"],
        input=password + "\n" + password + "\n",
        text=True,
        capture_output=True,
        check=True,
    )
    assert expected in result.stdout
print("PASS bootstrap CLI + idempotency")

with httpx.Client(base_url="http://web-smoke:3000", timeout=20, follow_redirects=False) as client:
    assert client.get("/login").status_code == 200
    assert client.get("/dashboard").status_code == 307
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/ready").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    print("PASS login page, anonymous dashboard redirect, health, readiness, 401")

    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    headers = {"Origin": "http://localhost:3002", "X-CSRF-Token": csrf}
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong"}, headers=headers
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
            headers={"Origin": "http://evil.example"},
        ).status_code
        == 403
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}, headers=headers
    )
    assert login.status_code == 200
    assert len(login.headers.get_list("set-cookie")) == 2
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Smoke Admin" in dashboard.text and "ADMIN" in dashboard.text
    assert client.get("/api/v1/admin/status").status_code == 200
    print("PASS invalid login, CSRF rejection, real proxy cookies, authenticated dashboard")

    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.role = Role.VIEWER
    assert client.get("/api/v1/admin/status").status_code == 403
    csrf = client.get("/api/v1/auth/session").json()["csrf_token"]
    response = client.post(
        "/api/v1/auth/logout",
        headers={
            "Origin": "http://localhost:3002",
            "X-CSRF-Token": csrf,
        },
    )
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/dashboard").status_code == 307
    print("PASS non-admin 403, logout, session revocation, dashboard redirect")

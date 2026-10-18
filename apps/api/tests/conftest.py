import os
import secrets
from collections.abc import Generator

from sqlalchemy.engine import make_url

os.environ["APP_ENV"] = "test"
os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
test_url = make_url(os.environ.get("TEST_DATABASE_URL", "sqlite:////tmp/av-unused.db"))
if test_url.get_backend_name() == "postgresql":
    if test_url.database != "assetvision_test" or test_url.host != "db-test":
        raise RuntimeError("Tests require db-test/assetvision_test")
    test_url = test_url.set(password=os.environ["POSTGRES_PASSWORD"])
os.environ["DATABASE_URL"] = test_url.render_as_string(hide_password=False)

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db import Base, get_db
from app.main import app
from app.models import Role, User
from app.security import hash_password


@pytest.fixture()
def factory() -> Generator[sessionmaker[Session]]:
    url = os.environ["DATABASE_URL"]
    postgres = url.startswith("postgresql")
    if postgres:
        # Guard before any destructive test setup. Compose uses a dedicated DB and tmpfs.
        if make_url(url).database != "assetvision_test" or make_url(url).host != "db-test":
            raise RuntimeError("Integration tests require the isolated assetvision_test database")
        engine = create_engine(get_settings().db_url)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")
    with engine.connect() as connection:
        config = Config("alembic.ini")
        if postgres:
            from sqlalchemy import text

            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
            connection.commit()
        # Alembic runs against this exact fixture connection.
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def db(factory: sessionmaker[Session]) -> Generator[Session]:
    with factory() as session:
        yield session


@pytest.fixture()
def client(factory: sessionmaker[Session]) -> Generator[TestClient]:
    def override() -> Generator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app, base_url="http://localhost:3000") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def password() -> str:
    return secrets.token_urlsafe(20)


@pytest.fixture()
def user(db: Session, password: str) -> User:
    user = User(
        email="admin@example.com",
        name="Test Admin",
        role=Role.ADMIN,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    return user


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    return {"Origin": "http://localhost:3000", "X-CSRF-Token": token}


def sign_in(client: TestClient, password: str, email: str = "admin@example.com"):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=csrf_headers(client),
    )


def session_headers(client: TestClient) -> dict[str, str]:
    token = client.get("/api/v1/auth/session").json()["csrf_token"]
    return {"Origin": "http://localhost:3000", "X-CSRF-Token": token}

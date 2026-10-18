import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


def test_ready(client: TestClient) -> None:
    assert client.get("/api/v1/ready").json() == {"status": "ready"}


def test_not_ready_on_db_failure(client: TestClient) -> None:
    class Unavailable:
        def execute(self, *args: object) -> None:
            raise OperationalError("unavailable", {}, Exception())

    app.dependency_overrides[get_db] = lambda: Unavailable()
    assert client.get("/api/v1/health").status_code == 200
    response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "Database or schema is not ready"


@pytest.mark.parametrize("version", ["0001_sprint0", "0002_device_catalog", "old_revision", None])
def test_not_ready_on_schema_mismatch(client: TestClient, db: Session, version: str | None) -> None:
    db.execute(text("DELETE FROM alembic_version"))
    if version:
        db.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": version})
    db.commit()
    assert client.get("/api/v1/ready").status_code == 503


def test_not_ready_when_catalog_table_missing(client: TestClient, db: Session) -> None:
    db.execute(text("DROP TABLE device_reference_images"))
    db.commit()
    assert client.get("/api/v1/ready").status_code == 503

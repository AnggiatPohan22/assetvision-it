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


@pytest.mark.parametrize(
    "version",
    [
        "0001_sprint0",
        "0002_device_catalog",
        "0003_image_cleanup",
        "0004_asset_registry",
        "0005_asset_imports",
        "0006_locations",
        "0007_asset_location",
        "0008_asset_movements",
        "0009_observations",
        "0010_embedding_index",
        "old_revision",
        None,
    ],
)
def test_not_ready_on_schema_mismatch(client: TestClient, db: Session, version: str | None) -> None:
    db.execute(text("DELETE FROM alembic_version"))
    if version:
        db.execute(text("INSERT INTO alembic_version VALUES (:v)"), {"v": version})
    db.commit()
    assert client.get("/api/v1/ready").status_code == 503


def test_not_ready_when_catalog_table_missing(client: TestClient, db: Session) -> None:
    db.execute(text("DROP TABLE image_embeddings"))
    db.execute(text("DROP TABLE device_reference_images"))
    db.commit()
    assert client.get("/api/v1/ready").status_code == 503


def test_not_ready_when_import_receipts_missing(client: TestClient, db: Session) -> None:
    db.execute(text("DROP TABLE asset_import_batches"))
    db.commit()
    assert client.get("/api/v1/ready").status_code == 503


def test_not_ready_when_locations_missing(client: TestClient, db: Session) -> None:
    db.execute(text("DROP TABLE recognition_reviews"))
    db.execute(text("DROP TABLE survey_observations"))
    db.execute(text("DROP TABLE location_observations"))
    db.execute(text("DROP TABLE asset_movements"))
    if db.bind.dialect.name == "postgresql":
        db.execute(text("ALTER TABLE assets DROP CONSTRAINT fk_assets_current_location"))
    db.execute(text("DROP TABLE locations"))
    db.commit()
    assert client.get("/api/v1/ready").status_code == 503


@pytest.mark.parametrize("table", ["asset_change_events", "asset_identifiers", "assets"])
def test_not_ready_when_asset_table_missing(client: TestClient, db: Session, table: str) -> None:
    # Drop dependents first on PostgreSQL; schema corruption is confined to the fixture DB.
    for dependent in (
        "recognition_reviews",
        "survey_observations",
        "location_observations",
        "asset_movements",
        "asset_events",
        "asset_change_events",
        "asset_identifiers",
        "assets",
    ):
        db.execute(text(f"DROP TABLE {dependent}"))
        if dependent == table:
            break
    db.commit()
    assert client.get("/api/v1/ready").status_code == 503


def test_not_ready_when_location_events_missing(client, db):
    db.execute(text("DROP TABLE asset_events"))
    db.commit()
    assert client.get("/api/v1/ready").status_code == 503


def test_not_ready_when_movements_missing(client, db):
    db.execute(text("DROP TABLE asset_movements"))
    db.commit()
    assert client.get("/api/v1/ready").status_code == 503


def test_not_ready_when_observations_missing(client, db):
    db.execute(text("DROP TABLE location_observations"))
    db.commit()
    assert client.get("/api/v1/ready").status_code == 503


@pytest.mark.parametrize(
    "table", ["embedding_indexes", "image_embeddings", "embedding_index_state"]
)
def test_not_ready_when_embedding_tables_missing(client, db, table):
    if table == "embedding_indexes":
        db.execute(text("DROP TABLE embedding_index_state"))
        db.execute(text("DROP TABLE image_embeddings"))
    db.execute(text(f"DROP TABLE {table}"))
    db.commit()
    assert client.get("/api/v1/ready").status_code == 503


@pytest.mark.parametrize(
    "table", ["recognition_jobs", "survey_observations", "recognition_reviews"]
)
def test_not_ready_when_recognition_evidence_missing(client, db, table):
    for dependent in ("recognition_reviews", "survey_observations", "recognition_jobs"):
        db.execute(text(f"DROP TABLE {dependent}"))
        if dependent == table:
            break
    db.commit()
    assert client.get("/api/v1/ready").status_code == 503

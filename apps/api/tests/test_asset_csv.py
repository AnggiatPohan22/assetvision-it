import csv
import hashlib
import io
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from conftest import csrf_headers
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from test_asset_api import headers as headers
from test_asset_api import model as model

from app.asset_csv import commit_csv
from app.asset_csv_schemas import CsvCommit
from app.asset_imports import AssetImportBatch
from app.assets import (
    AssetChangeEvent,
    AssetIdentifier,
    AssetUnit,
    IdentifierSource,
    IdentifierType,
)
from app.db import Base
from app.models import Role, User

ROOT = "/api/v1/assets"


def csv_text(*rows, columns=None):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        columns
        or [
            "asset_code",
            "manufacturer",
            "model",
            "serial_number",
            "mac_address",
            "hostname",
            "condition",
            "status",
            "notes",
            "location_hint",
        ]
    )
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def row(code="CSV-001", **values):
    defaults = dict(
        asset_code=code,
        manufacturer="Synthetic Manufacturer",
        model="Synthetic AP",
        serial_number="",
        mac_address="",
        hostname="",
        condition="",
        status="",
        notes="",
        location_hint="",
    )
    defaults.update(values)
    return list(defaults.values())


def preview(client, headers, content):
    return client.post(ROOT + "/imports/preview", headers=headers, json={"csv_text": content})


def commit(client, headers, content, key=None, **values):
    return client.post(
        ROOT + "/imports/commit",
        headers=headers,
        json={
            "csv_text": content,
            "idempotency_key": str(key or uuid.uuid4()),
            **values,
        },
    )


def fingerprint(db):
    result = {}
    for table in Base.metadata.sorted_tables:
        rows = [
            dict(item) for item in db.execute(select(table).order_by(*table.primary_key)).mappings()
        ]
        result[table.name] = hashlib.sha256(
            json.dumps(rows, default=str, sort_keys=True).encode()
        ).hexdigest()
    return result


def test_preview_read_only_commit_and_replay(client, headers, model, db, user):
    content = csv_text(
        row(
            serial_number="SN-001",
            mac_address="aabb.ccdd.eeff",
            hostname=" AP-One ",
            notes="Label, quoted\nsecond line",
            location_hint="Staging rack",
        ),
        row("CSV-002"),
    )
    before = fingerprint(db)
    result = preview(client, headers, "\ufeff" + content)
    assert result.status_code == 200, result.text
    assert result.json()["valid_rows"] == 2 and not result.json()["has_collisions"]
    assert fingerprint(db) == before
    key = uuid.uuid4()
    saved = commit(client, headers, content, key)
    assert saved.status_code == 200, saved.text
    output = saved.json()
    assert output["status"] == "COMMITTED" and output["created_count"] == 2
    assert output["rows"][0]["location_hint"] == "Staging rack"
    assert [r["version"] for r in output["rows"]] == [4, 1]
    first = db.get(AssetUnit, uuid.UUID(output["rows"][0]["asset_id"]))
    assert first.notes == "Label, quoted\nsecond line"
    assert not hasattr(first, "current_location")
    claims = list(db.scalars(select(AssetIdentifier).where(AssetIdentifier.asset_id == first.id)))
    assert len(claims) == 3 and all(
        c.source == "IMPORT" and c.verification_status == "UNVERIFIED" for c in claims
    )
    assert {c.normalized_value for c in claims} == {"SN-001", "AA:BB:CC:DD:EE:FF", "ap-one"}
    events = list(db.scalars(select(AssetChangeEvent)))
    assert len(events) == 5 and all(e.actor_id == user.id for e in events)
    state = fingerprint(db)
    assert commit(client, headers, content, key).json() == output
    assert fingerprint(db) == state
    # Replay survives later catalog/domain changes; it returns the saved receipt.
    model.is_active = False
    db.commit()
    assert commit(client, headers, content, key).json() == output
    receipt = db.get(AssetImportBatch, key)
    assert receipt.result_json == output and len(receipt.request_sha256) == 64
    assert content not in json.dumps(receipt.result_json)
    assert commit(client, headers, content + "\n", key).status_code == 409


def test_key_ownership_and_live_rbac_on_replay(client, headers, model, db, user):
    content = csv_text(row())
    key = uuid.uuid4()
    assert commit(client, headers, content, key).status_code == 200
    receipt = db.get(AssetImportBatch, key)
    other = User(
        email="other@example.com",
        name="Other admin",
        password_hash=user.password_hash,
        role=Role.ADMIN,
    )
    db.add(other)
    db.flush()
    receipt.actor_id = other.id
    db.commit()
    assert commit(client, headers, content, key).status_code == 409
    user.role = Role.OFFICER
    db.commit()
    assert commit(client, headers, content, key).status_code == 403


@pytest.mark.parametrize(
    "content",
    [
        "",
        "asset_code,manufacturer\nA,M\n",
        "asset_code,manufacturer,model,asset_code\nA,M,X,A\n",
        "asset_code,manufacturer,model,unknown\nA,M,X,x\n",
        "asset_code,manufacturer,model\n",
        'asset_code,manufacturer,model\nA,"unterminated,X',
        "asset_code,manufacturer,model\n" + "\n".join(f"AP-{i},M,X" for i in range(501)),
    ],
)
def test_malformed_csv_rejected_without_writes(client, headers, model, db, content):
    before = fingerprint(db)
    assert preview(client, headers, content).status_code == 422
    assert commit(client, headers, content).status_code == 422
    assert fingerprint(db) == before


@pytest.mark.parametrize(
    "values",
    [
        {"asset_code": "bad/code"},
        {"manufacturer": "Unknown"},
        {"model": "No model"},
        {"serial_number": "UNKNOWN"},
        {"mac_address": "bad-mac"},
        {"hostname": "bad\nname"},
        {"condition": "BROKEN"},
        {"status": "MISSING"},
        {"notes": "x" * 4001},
        {"notes": "bad\x00"},
        {"location_hint": "x" * 1001},
    ],
)
def test_row_errors_reject_whole_batch(client, headers, model, db, values):
    content = csv_text(row("CSV-OK"), row("CSV-BAD", **values))
    report = preview(client, headers, content).json()
    assert report["valid_rows"] == 1 and report["invalid_rows"] == 1
    assert report["rows"][1]["errors"]
    before = fingerprint(db)
    saved = commit(client, headers, content)
    assert saved.status_code == 409 and saved.json()["failed_count"] == 2
    assert saved.json()["created_count"] == 0
    assert fingerprint(db) == before


def test_duplicates_db_conflicts_and_commit_revalidation(client, headers, model, db):
    duplicate = csv_text(row(" csv-001 "), row("CSV-001"))
    report = preview(client, headers, duplicate).json()
    assert report["invalid_rows"] == 2
    assert all("Duplicate asset code within CSV" in r["errors"] for r in report["rows"])
    assert commit(client, headers, duplicate).status_code == 409
    content = csv_text(row())
    assert preview(client, headers, content).json()["valid_rows"] == 1
    asset = AssetUnit(
        asset_code="CSV-001",
        device_model_id=model.id,
        lifecycle_status="ARCHIVED",
        notes="Existing data",
    )
    db.add(asset)
    db.commit()
    state = fingerprint(db)
    conflict = commit(client, headers, content)
    assert conflict.status_code == 409 and conflict.json()["rows"][0]["errors"]
    assert fingerprint(db) == state
    fresh = csv_text(row("CSV-NEW"))
    assert preview(client, headers, fresh).json()["valid_rows"] == 1
    model.is_active = False
    db.commit()
    assert commit(client, headers, fresh).status_code == 409


def test_collision_reporting_acknowledgement_and_sources(client, headers, model, db):
    existing = AssetUnit(asset_code="EXISTING", device_model_id=model.id)
    db.add(existing)
    db.flush()
    db.add(
        AssetIdentifier(
            asset_id=existing.id,
            identifier_type=IdentifierType.MAC_LAN,
            raw_value="aabbccddeeff",
            source=IdentifierSource.MANUAL,
        )
    )
    db.commit()
    content = csv_text(
        row(mac_address="AA-BB-CC-DD-EE-FF", serial_number="Shared"),
        row("CSV-002", mac_address="aabb.ccdd.eeff", serial_number="Shared"),
    )
    report = preview(client, headers, content).json()
    assert report["has_collisions"] and report["invalid_rows"] == 0
    collision = next(
        c for c in report["rows"][0]["collisions"] if c["identifier_type"] == "MAC_LAN"
    )
    assert collision["asset_ids"] == [str(existing.id)] and collision["csv_rows"] == [3]
    assert commit(client, headers, content).status_code == 409
    saved = commit(client, headers, content, allow_identifier_collisions=True)
    assert saved.status_code == 200 and saved.json()["created_count"] == 2
    assert db.scalar(select(func.count()).select_from(AssetIdentifier)) == 5


def test_csv_column_count_blank_lines_and_case_resolution(client, headers, model, db):
    from app.catalog import DeviceModel, Environment, Manufacturer

    maker = Manufacturer(name="Other Manufacturer")
    db.add(maker)
    db.flush()
    other = DeviceModel(
        manufacturer_id=maker.id,
        category_id=model.category_id,
        model_name=model.model_name,
        environment=Environment.INDOOR,
    )
    db.add(other)
    db.commit()
    content = "\n" + csv_text(
        row(manufacturer="  SYNTHETIC   manufacturer ", model=" synthetic   AP ")
    )
    # Leading empty records are malformed headers; blank lines among data are ignored.
    assert preview(client, headers, content).status_code == 422
    content = (
        csv_text(row(manufacturer="  SYNTHETIC   manufacturer ", model=" synthetic   AP ")) + "\n"
    )
    result = commit(client, headers, content)
    assert result.status_code == 200
    asset = db.get(AssetUnit, uuid.UUID(result.json()["rows"][0]["asset_id"]))
    assert asset.device_model_id == model.id
    malformed = (
        "asset_code,manufacturer,model\nA,Synthetic Manufacturer\n"
        "B,Synthetic Manufacturer,Synthetic AP,extra\n"
    )
    report = preview(client, headers, malformed).json()
    assert report["invalid_rows"] == 2
    assert all(r["errors"] == ["Column count differs from header"] for r in report["rows"])


def test_csv_500_row_boundary_and_deleted_claim_not_collision(client, headers, model, db):
    content = csv_text(*(row(f"BOUND-{i}") for i in range(500)))
    result = preview(client, headers, content)
    assert result.status_code == 200 and result.json()["valid_rows"] == 500
    asset = AssetUnit(asset_code="DELETED-CLAIM", device_model_id=model.id)
    db.add(asset)
    db.flush()
    from datetime import UTC, datetime

    db.add(
        AssetIdentifier(
            asset_id=asset.id,
            identifier_type=IdentifierType.SERIAL_NUMBER,
            raw_value="OLD-SN",
            source=IdentifierSource.MANUAL,
            deleted_at=datetime.now(UTC),
        )
    )
    db.commit()
    report = preview(client, headers, csv_text(row(serial_number="OLD-SN"))).json()
    assert not report["has_collisions"]


def test_csv_stream_limit_without_content_length(client, headers, model):
    def chunks():
        for _ in range(20):
            yield b"x" * (64 * 1024)

    response = client.post(
        ROOT + "/imports/preview",
        headers={**headers, "Content-Type": "application/json"},
        content=chunks(),
    )
    assert response.request.headers.get("content-length") is None
    assert response.status_code == 413


def test_shape_limits_and_csrf(client, headers, model, db):
    for target in ("preview", "commit"):
        path = ROOT + "/imports/" + target
        assert (
            client.post(path, headers=headers, content=b"x" * (1024 * 1024 + 1)).status_code == 415
        )
        assert (
            client.post(
                path,
                headers={**headers, "Content-Type": "application/json"},
                content=b"x" * (1024 * 1024 + 1),
            ).status_code
            == 413
        )
    assert preview(client, headers, "é" * (128 * 1024 + 1)).status_code == 422
    assert preview(client, headers, "x" * (256 * 1024 + 1)).status_code == 422
    content = csv_text(row())
    assert client.post(ROOT + "/imports/preview", json={"csv_text": content}).status_code == 403
    assert (
        client.post(
            ROOT + "/imports/commit", headers=headers, json={"csv_text": content}
        ).status_code
        == 422
    )
    assert commit(client, headers, content, allow_identifier_collisions="true").status_code == 422
    assert (
        client.post(
            ROOT + "/imports/preview",
            headers=headers,
            json={"csv_text": content, "unexpected": True},
        ).status_code
        == 422
    )
    assert db.scalar(select(func.count()).select_from(AssetImportBatch)) == 0


@pytest.mark.parametrize("role", [Role.OFFICER, Role.VIEWER, None])
def test_csv_admin_only(client, headers, model, db, user, role):
    if role is None:
        client.cookies.clear()
        headers = csrf_headers(client)
    else:
        user.role = role
        db.commit()
    before = fingerprint(db)
    expected = 401 if role is None else 403
    assert preview(client, headers, csv_text(row())).status_code == expected
    assert commit(client, headers, csv_text(row())).status_code == expected
    assert client.get(ROOT + "/export.csv").status_code == expected
    assert fingerprint(db) == before


@pytest.mark.parametrize("at", [1, 3, 4])
def test_failure_after_partial_work_rolls_back_receipt_assets_claims_audit(
    client, headers, model, db, at
):
    content = csv_text(row(serial_number="S1"), row("CSV-002", hostname="AP2"))
    before = fingerprint(db)
    calls = 0

    def fail(mapper, connection, target):
        nonlocal calls
        calls += 1
        if calls == at:
            raise IntegrityError("synthetic audit failure", {}, None)

    event.listen(AssetChangeEvent, "before_insert", fail)
    try:
        result = commit(client, headers, content)
        assert result.status_code == 409
        assert result.json()["created_count"] == 0 and result.json()["failed_count"] == 2
        assert all(r["asset_id"] is None and r["version"] is None for r in result.json()["rows"])
    finally:
        event.remove(AssetChangeEvent, "before_insert", fail)
    assert fingerprint(db) == before


@pytest.mark.parametrize(
    "value", ["=1+1", "+cmd", "-1+2", "@SUM(A1)", " \t=1+1", "\tplain", "\rplain", "\nplain"]
)
def test_export_formula_safety_all_claims_and_filters(client, headers, model, db, value):
    asset = AssetUnit(asset_code="CSV-001", device_model_id=model.id, notes=value)
    db.add(asset)
    db.flush()
    for kind, raw in [
        (IdentifierType.SERIAL_NUMBER, "=formula"),
        (IdentifierType.MAC_LAN, "aabbccddeeff"),
        (IdentifierType.MAC_LAN, "112233445566"),
        (IdentifierType.BSSID, "1234567890ab"),
    ]:
        db.add(
            AssetIdentifier(
                asset_id=asset.id,
                identifier_type=kind,
                raw_value=raw,
                source=IdentifierSource.MANUAL,
            )
        )
    db.commit()
    before = fingerprint(db)
    response = client.get(
        ROOT + "/export.csv", params={"model_id": str(model.id), "search": "CSV-001"}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == 'attachment; filename="assets.csv"'
    assert response.headers["cache-control"] == "no-store"
    items = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(items) == 1 and items[0]["notes"] == "'" + value
    assert items[0]["serial_number"] == "'=formula"
    assert len(json.loads(items[0]["identifiers_json"])) == 4
    assert items[0]["location_hint"] == ""
    assert len(items[0]["mac_address"].splitlines()) == 2
    assert client.get(ROOT + "/export.csv?status=IN_USE").text.count("CSV-001") == 0
    assert client.get(ROOT + "/export.csv?page=1").status_code == 422
    assert fingerprint(db) == before


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_commits_postgres(client, headers, model, db, user, factory, same_key):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL unique-index transaction waits")
    barrier = Barrier(2)
    actor_id = user.id
    common = uuid.uuid4()
    content = csv_text(row(serial_number="S1"), row("CSV-002"))

    def run(index):
        with factory() as session:
            actor = session.get(User, actor_id)
            request = CsvCommit(
                csv_text=content, idempotency_key=common if same_key else uuid.uuid4()
            )
            barrier.wait(timeout=10)
            return commit_csv(session, request, actor).model_dump(mode="json")

    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(run, [0, 1]))
    if same_key:
        assert outputs[0] == outputs[1] and outputs[0]["status"] == "COMMITTED"
    else:
        assert sorted(o["status"] for o in outputs) == ["COMMITTED", "REJECTED"]
    assert db.scalar(select(func.count()).select_from(AssetUnit)) == 2
    assert db.scalar(select(func.count()).select_from(AssetImportBatch)) == 1
    assert db.scalar(select(func.count()).select_from(AssetChangeEvent)) == 3


def test_import_migration_preserves_all_existing_tables(client, headers, model, db, factory):
    content = csv_text(row(serial_number="MIGRATION-SN"))
    assert commit(client, headers, content).status_code == 200
    expected = fingerprint(db)
    expected.pop("asset_import_batches")
    db.rollback()
    with factory.kw["bind"].connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.downgrade(config, "0004_asset_registry")
        assert "asset_import_batches" not in inspect(connection).get_table_names()
        connection.commit()
        command.upgrade(config, "head")
        command.check(config)
    db.expire_all()
    actual = fingerprint(db)
    actual.pop("asset_import_batches")
    assert actual == expected
    assert db.scalar(select(func.count()).select_from(AssetImportBatch)) == 0
    assert (
        db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        == "0005_asset_imports"
    )

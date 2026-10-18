"""Sprint 1B review regressions: audit integrity and private failure boundaries."""

import logging
import uuid

import pytest
from sqlalchemy import event, select
from test_asset_api import create
from test_asset_api import headers as headers
from test_asset_api import model as model
from test_asset_csv import fingerprint

from app.assets import AssetChangeEvent
from app.models import Role

ROOT = "/api/v1/assets"


def test_six_audit_events_expose_complete_version_chain_and_reads_do_not_write(
    client, headers, model, db, user
):
    asset = create(client, headers, model, "AUDIT-001")
    path = f"{ROOT}/{asset['id']}"
    assert (
        client.patch(
            path, headers=headers, json={"version": 1, "notes": "Synthetic audit diff"}
        ).status_code
        == 200
    )
    added = client.post(
        path + "/identifiers",
        headers=headers,
        json={
            "asset_version": 2,
            "identifier_type": "HOSTNAME",
            "raw_value": "synthetic.invalid",
            "source": "MANUAL",
        },
    ).json()
    claim_path = path + "/identifiers/" + added["identifier"]["id"]
    assert (
        client.patch(
            claim_path,
            headers=headers,
            json={
                "asset_version": 3,
                "version": 1,
                "verification_status": "VERIFIED",
            },
        ).status_code
        == 200
    )
    assert (
        client.delete(claim_path + "?asset_version=4&version=2", headers=headers).status_code == 200
    )
    assert client.post(path + "/archive", headers=headers, json={"version": 5}).status_code == 200
    events = client.get(path + "/events").json()["items"]
    assert [e["event_type"] for e in events] == [
        "ARCHIVE",
        "IDENTIFIER_REMOVE",
        "IDENTIFIER_UPDATE",
        "IDENTIFIER_ADD",
        "UPDATE",
        "CREATE",
    ]
    assert [e["after_json"]["asset"]["version"] for e in events] == [6, 5, 4, 3, 2, 1]
    for entry in events:
        assert entry["actor_id"] == str(user.id) and entry["recorded_at"]
        assert entry["after_json"]["asset"]["asset_code"] == "AUDIT-001"
        if entry["event_type"] != "CREATE":
            assert (
                entry["before_json"]["asset"]["version"] + 1
                == entry["after_json"]["asset"]["version"]
            )
    assert events[1]["after_json"]["identifier"]["deleted_at"]
    assert events[2]["after_json"]["identifier"]["verification_status"] == "VERIFIED"
    assert events[4]["before_json"]["asset"]["notes"] is None
    before = fingerprint(db)
    for role in Role:
        user.role = role
        db.commit()
        own_before = fingerprint(db)
        for suffix in ("", "/identifiers", "/events?page_size=1", "/events?page=999"):
            response = client.get(path + suffix)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["x-request-id"]
        assert fingerprint(db) == own_before
    user.role = Role.ADMIN
    db.commit()
    assert fingerprint(db) == before


def test_unexpected_audit_exception_is_private_and_rolls_back(client, headers, model, db, caplog):
    before = fingerprint(db)
    sensitive = "SYNTHETIC-PRIVATE-IDENTIFIER"

    def fail(mapper, connection, target):
        raise RuntimeError(sensitive)

    event.listen(AssetChangeEvent, "before_insert", fail)
    try:
        with caplog.at_level(logging.INFO, logger="assetvision"):
            response = client.post(
                ROOT,
                headers=headers,
                json={
                    "asset_code": "PRIVATE-001",
                    "device_model_id": str(model.id),
                    "notes": sensitive,
                },
            )
    finally:
        event.remove(AssetChangeEvent, "before_insert", fail)
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert sensitive not in response.text
    app_records = [record for record in caplog.records if record.name == "assetvision"]
    assert any(record.getMessage() == "request_failed" for record in app_records)
    assert all(
        sensitive not in record.getMessage() + str(getattr(record, "context", {}))
        for record in app_records
    )
    assert fingerprint(db) == before


@pytest.mark.parametrize("target", ["asset", "identifier"])
def test_server_owned_identity_audit_and_version_fields_cannot_be_forged(
    client, headers, model, db, target
):
    asset = create(client, headers, model, "FORGE-001")
    before = fingerprint(db)
    data = {
        "id": str(uuid.uuid4()),
        "actor_id": str(uuid.uuid4()),
        "created_at": "2000-01-01",
        "after_json": {"injected": True},
        "normalized_value": "forged",
        "version": 99,
    }
    if target == "asset":
        response = client.patch(f"{ROOT}/{asset['id']}", headers=headers, json=data)
    else:
        response = client.post(
            f"{ROOT}/{asset['id']}/identifiers",
            headers=headers,
            json={
                **data,
                "asset_version": 1,
                "identifier_type": "SERIAL_NUMBER",
                "raw_value": "SYNTHETIC-VALID",
                "source": "MANUAL",
            },
        )
    assert response.status_code == 422
    assert fingerprint(db) == before
    assert (
        db.scalar(
            select(AssetChangeEvent).where(AssetChangeEvent.asset_id == uuid.UUID(asset["id"]))
        ).event_type
        == "CREATE"
    )

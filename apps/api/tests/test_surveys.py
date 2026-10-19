"""API/security/transaction tests on generated images and isolated synthetic registry."""

import hashlib
import io
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from conftest import session_headers, sign_in
from PIL import Image
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError

from app.assets import (
    AssetIdentifier,
    AssetUnit,
    IdentifierSource,
    IdentifierType,
    VerificationStatus,
)
from app.catalog import DeviceCategory, DeviceModel, Manufacturer, StorageCleanupJob
from app.image_service import cleanup_pending
from app.main import app
from app.models import AuditEvent, Role, User
from app.ocr_schemas import OCRLine, OCRReading
from app.recognition_observations import RecognitionJob, RecognitionReview, SurveyObservation
from app.recognition_routes import get_ocr_engine
from app.storage import LocalStorageProvider, StorageError, get_storage
from app.survey_schemas import SurveyCreate, SurveyReview
from app.survey_service import create_observation, review_observation


def picture():
    target = io.BytesIO()
    exif = Image.Exif()
    exif[270] = "PRIVATE EXIF TEST"
    Image.new("RGB", (40, 20), "orange").save(target, format="PNG", exif=exif)
    return target.getvalue()


@pytest.fixture()
def storage(tmp_path):
    provider = LocalStorageProvider(tmp_path / "photos")
    app.dependency_overrides[get_storage] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture()
def headers(client, user, password):
    assert sign_in(client, password).status_code == 200
    return session_headers(client)


@pytest.fixture()
def registry(db):
    category = DeviceCategory(code="survey-synthetic", name="Synthetic")
    maker = Manufacturer(name="Survey Synthetic")
    db.add_all([category, maker])
    db.flush()
    model = DeviceModel(
        category_id=category.id, manufacturer_id=maker.id, model_name="Test AP", environment="both"
    )
    db.add(model)
    db.flush()
    asset = AssetUnit(asset_code="SYN-AP-1", device_model_id=model.id)
    db.add(asset)
    db.flush()
    db.add(
        AssetIdentifier(
            asset_id=asset.id,
            identifier_type=IdentifierType.SERIAL_NUMBER,
            raw_value="ABC789XYZ",
            normalized_value="ABC789XYZ",
            source=IdentifierSource.MANUAL,
            verification_status=VerificationStatus.VERIFIED,
        )
    )
    db.commit()
    return asset, maker


def upload(client, headers, endpoint="model-candidates", **kw):
    return client.post(
        "/api/v1/recognition/" + endpoint,
        headers=headers,
        files={
            "file": ("../../private.png", kw.get("data", picture()), kw.get("mime", "image/png"))
        },
    )


def observation(client, headers, job_id, **kw):
    return client.post(
        "/api/v1/recognition/observations",
        headers=headers,
        json={
            "request_id": str(uuid.uuid4()),
            "device_job_id": job_id,
            "notes": "Synthetic observed device",
            **kw,
        },
    )


def match_payload(asset, maker):
    return dict(
        version=1,
        decision="MATCH",
        selected_asset_id=str(asset.id),
        asset_version=asset.version,
        manufacturer_id=str(maker.id),
        checked_manual_indices=[0],
        label_checked=True,
        notes="Label independently checked against verified registry claim",
    )


def test_upload_unknown_original_private_sanitized_preview(client, headers, storage, db):
    raw = picture()
    response = upload(client, headers, data=raw)
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["result"]["status"] == "UNKNOWN_MODEL"
    assert job["source_image_sha256"] == hashlib.sha256(raw).hexdigest()
    stored = db.get(RecognitionJob, uuid.UUID(job["id"]))
    assert storage.read(stored.storage_key) == raw
    preview = client.get(job["content_url"])
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"
    assert b"PRIVATE EXIF TEST" not in preview.content
    assert preview.headers["cache-control"] == "no-store"
    assert "storage_key" not in response.text


def test_manual_observation_review_preserves_predictions_and_master(
    client, headers, storage, registry, db, user
):
    asset, maker = registry
    original_version = asset.version
    job = upload(client, headers).json()
    obs = observation(client, headers, job["id"], correction={"corrected_text": "SN: ABC789XYZ"})
    assert obs.status_code == 201, obs.text
    initial = obs.json()
    evidence = initial["evidence"]
    assert evidence["ocr"]["raw_text"] == ""
    assert evidence["ocr"]["corrected_text"] == "SN: ABC789XYZ"
    review = client.post(
        f"/api/v1/recognition/observations/{initial['id']}/review",
        headers=headers,
        json=match_payload(asset, maker),
    )
    assert review.status_code == 200, review.text
    result = review.json()
    assert result["asset_id"] == str(asset.id)
    assert result["review"]["evidence"]["result_status"] == "VERIFIED_ASSET"
    assert result["review"]["reviewer_id"] == str(user.id)
    assert result["evidence"] == evidence
    db.refresh(asset)
    assert asset.version == original_version and asset.current_location_id is None
    assert (
        client.post(
            f"/api/v1/recognition/observations/{initial['id']}/review",
            headers=headers,
            json=match_payload(asset, maker),
        ).status_code
        == 409
    )


def test_raw_ocr_and_correction_not_overwritten(client, headers, storage, db):
    class Engine:
        def recognize(self, image):
            return OCRReading(
                engine_version="synthetic",
                model_fingerprint="a" * 64,
                lines=(OCRLine(text="SN: RAW123", score=0.5),),
            )

    app.dependency_overrides[get_ocr_engine] = lambda: Engine()
    try:
        device = upload(client, headers).json()
        label = upload(client, headers, "ocr").json()
        result = observation(
            client,
            headers,
            device["id"],
            label_job_id=label["id"],
            correction={"corrected_text": "SN: MANUAL456"},
        )
        assert result.status_code == 201, result.text
        ocr = result.json()["evidence"]["ocr"]
        assert ocr["raw_text"] == "SN: RAW123" and ocr["corrected_text"] == "SN: MANUAL456"
        assert ocr["ocr_candidates"][0]["source"] == "OCR"
        assert ocr["manual_candidates"][0]["source"] == "MANUAL"
        stored = db.get(RecognitionJob, uuid.UUID(label["id"]))
        assert stored.result_json["corrected_text"] is None
    finally:
        app.dependency_overrides.pop(get_ocr_engine, None)


@pytest.mark.parametrize("decision", ["UNKNOWN", "CONFLICT", "MORE_PHOTOS"])
def test_nonmatch_review_retains_null_asset(client, headers, storage, decision):
    job = upload(client, headers).json()
    obs = observation(client, headers, job["id"], force_unknown=True).json()
    response = client.post(
        f"/api/v1/recognition/observations/{obs['id']}/review",
        headers=headers,
        json=dict(version=1, decision=decision, notes="Synthetic human review"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["asset_id"] is None
    assert response.json()["review_status"] == decision


@pytest.mark.parametrize(
    "field,value",
    [
        ("label_checked", False),
        ("checked_manual_indices", []),
        ("manufacturer_id", None),
        ("asset_version", 999),
    ],
)
def test_match_rejects_missing_or_stale_identity(client, headers, storage, registry, field, value):
    asset, maker = registry
    job = upload(client, headers).json()
    obs = observation(
        client, headers, job["id"], correction={"corrected_text": "SN: ABC789XYZ"}
    ).json()
    payload = match_payload(asset, maker)
    payload[field] = value
    response = client.post(
        f"/api/v1/recognition/observations/{obs['id']}/review", headers=headers, json=payload
    )
    assert response.status_code in {409, 422}, response.text


def test_registry_change_blocks_match(client, headers, storage, registry, db):
    asset, maker = registry
    job = upload(client, headers).json()
    obs = observation(
        client, headers, job["id"], correction={"corrected_text": "SN: ABC789XYZ"}
    ).json()
    asset.notes = "Changed after observation"
    db.commit()
    response = client.post(
        f"/api/v1/recognition/observations/{obs['id']}/review",
        headers=headers,
        json=match_payload(asset, maker),
    )
    assert response.status_code == 409, response.text
    assert "changed" in response.json()["detail"]


def test_observation_retry_same_key_payload_and_cross_actor(client, headers, storage, db, user):
    job = upload(client, headers).json()
    key = str(uuid.uuid4())
    first = observation(client, headers, job["id"], request_id=key)
    again = observation(client, headers, job["id"], request_id=key)
    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"]
    assert (
        observation(client, headers, job["id"], request_id=key, notes="Different").status_code
        == 409
    )
    assert db.scalar(select(func.count()).select_from(SurveyObservation)) == 1


@pytest.mark.parametrize("endpoint", ["model-candidates", "ocr"])
def test_anonymous_and_csrf_upload_rejected(client, user, password, storage, endpoint):
    assert upload(client, {}, endpoint).status_code in {401, 403}
    sign_in(client, password)
    assert upload(client, {}, endpoint).status_code == 403


@pytest.mark.parametrize("role", [Role.OFFICER, Role.VIEWER])
def test_server_roles(client, headers, storage, db, user, role):
    user.role = role
    db.commit()
    result = upload(client, headers)
    assert result.status_code == (201 if role == Role.OFFICER else 403)
    assert client.get("/api/v1/recognition/metrics").status_code == 403
    response = client.post(
        f"/api/v1/recognition/observations/{uuid.uuid4()}/review",
        headers=headers,
        json={"version": 1, "decision": "UNKNOWN", "notes": "Test"},
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "data,mime,code",
    [
        (b"not image", "image/png", 415),
        (picture(), "image/jpeg", 415),
        (b"a" * (8 * 1024 * 1024 + 1), "image/png", 413),
    ],
)
def test_upload_validation(client, headers, storage, db, data, mime, code):
    assert upload(client, headers, data=data, mime=mime).status_code == code
    assert db.scalar(select(func.count()).select_from(RecognitionJob)) == 0


def test_rate_limit_persistent_for_invalid_requests(client, headers, storage):
    for _ in range(10):
        assert upload(client, headers, data=b"bad").status_code == 415
    response = upload(client, headers)
    assert response.status_code == 429 and response.headers["retry-after"] == "60"


def test_job_ownership_cannot_be_forged(client, headers, storage, db, user):
    job = upload(client, headers).json()
    other = User(
        email="other@synthetic.invalid",
        name="Other",
        password_hash=user.password_hash,
        role=Role.OFFICER,
    )
    db.add(other)
    db.commit()
    with pytest.raises(Exception) as error:
        create_observation(
            db,
            SurveyCreate(request_id=uuid.uuid4(), device_job_id=job["id"], notes="Stolen job"),
            other,
        )
    assert error.value.status_code == 404


@pytest.mark.parametrize(
    "table", ["recognition_jobs", "survey_observations", "recognition_reviews"]
)
def test_immutable_evidence_guards(client, headers, storage, db, table):
    job = upload(client, headers).json()
    obs = observation(client, headers, job["id"]).json()
    client.post(
        f"/api/v1/recognition/observations/{obs['id']}/review",
        headers=headers,
        json={"version": 1, "decision": "UNKNOWN", "notes": "Synthetic unknown"},
    )
    for sql in [f"UPDATE {table} SET id=id", f"DELETE FROM {table}"]:
        with pytest.raises(IntegrityError):
            db.execute(text(sql))
            db.commit()
        db.rollback()


def test_populated_migration_downgrade_rejected(client, headers, storage, db):
    upload(client, headers)
    config = Config("alembic.ini")
    connection = db.connection()
    config.attributes["connection"] = connection
    with pytest.raises(RuntimeError, match="populated"):
        command.downgrade(config, "0010_embedding_index")
    db.rollback()
    assert db.scalar(select(func.count()).select_from(RecognitionJob)) == 1


def test_cleanup_preserves_referenced_capture(client, headers, storage, db):
    uploaded = upload(client, headers).json()
    record = db.get(RecognitionJob, uuid.UUID(uploaded["id"]))
    db.add(
        StorageCleanupJob(
            storage_key=record.storage_key, created_at=datetime.now(UTC) - timedelta(minutes=20)
        )
    )
    db.commit()
    assert cleanup_pending(db, storage) == 1
    assert storage.read(record.storage_key)


def test_atomic_audit_failure_rolls_back_observation(client, headers, storage, db, user):
    job = upload(client, headers).json()

    def fail(mapper, connection, target):
        if target.action == "recognition_observation_create":
            raise RuntimeError("Synthetic audit failure")

    event.listen(AuditEvent, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            create_observation(
                db,
                SurveyCreate(
                    request_id=uuid.uuid4(), device_job_id=job["id"], notes="Synthetic failure"
                ),
                user,
            )
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    assert db.scalar(select(func.count()).select_from(SurveyObservation)) == 0


def test_forbidden_trusted_payload_fields(client, headers, storage):
    job = upload(client, headers).json()
    result = observation(
        client, headers, job["id"], human_checked=True, fusion={"status": "VERIFIED_ASSET"}
    )
    assert result.status_code == 422


@pytest.mark.parametrize("kind", ["collision", "unverified", "location"])
def test_conflict_and_untrusted_claim_cannot_be_verified(
    client, headers, storage, registry, db, kind
):
    from app.locations import Location

    asset, maker = registry
    location = None
    if kind == "collision":
        duplicate = AssetUnit(asset_code="SYN-AP-2", device_model_id=asset.device_model_id)
        db.add(duplicate)
        db.flush()
        db.add(
            AssetIdentifier(
                asset_id=duplicate.id,
                identifier_type="SERIAL_NUMBER",
                raw_value="ABC789XYZ",
                normalized_value="ABC789XYZ",
                source="IMPORT",
                verification_status="VERIFIED",
            )
        )
    elif kind == "unverified":
        claim = db.scalar(select(AssetIdentifier).where(AssetIdentifier.asset_id == asset.id))
        claim.verification_status = VerificationStatus.UNVERIFIED
    else:
        official = Location(code="official", name="Official", kind="ROOM")
        location = Location(code="observed", name="Observed", kind="ROOM")
        db.add_all([official, location])
        db.flush()
        asset.current_location_id = official.id
    db.commit()
    job = upload(client, headers).json()
    obs = observation(
        client,
        headers,
        job["id"],
        observed_location_id=str(location.id) if location else None,
        correction={"corrected_text": "SN: ABC789XYZ"},
    ).json()
    response = client.post(
        f"/api/v1/recognition/observations/{obs['id']}/review",
        headers=headers,
        json=match_payload(asset, maker),
    )
    assert response.status_code == 409, response.text
    assert db.scalar(select(func.count()).select_from(RecognitionReview)) == 0


def test_read_acl_unattached_private_then_viewer_reads_published(
    client, headers, storage, db, user, password
):
    job = upload(client, headers).json()
    viewer = User(
        email="survey-viewer@example.com",
        name="Viewer",
        password_hash=user.password_hash,
        role=Role.VIEWER,
    )
    db.add(viewer)
    db.commit()
    assert sign_in(client, password, email=viewer.email).status_code == 200
    assert client.get(job["content_url"]).status_code == 404
    assert sign_in(client, password).status_code == 200
    observation(client, session_headers(client), job["id"])
    assert sign_in(client, password, email=viewer.email).status_code == 200
    assert client.get(job["content_url"]).status_code == 200
    listed = client.get("/api/v1/recognition/observations").json()
    assert "unit_snapshots" not in json.dumps(listed)
    assert listed["total"] == 1


def test_storage_failure_has_no_job_and_cleanup_intent_retried(
    client, headers, storage, db, monkeypatch
):
    def fail(key, data):
        raise StorageError("Synthetic write failure")

    monkeypatch.setattr(storage, "put", fail)
    response = upload(client, headers)
    assert response.status_code == 503
    assert db.scalar(select(func.count()).select_from(RecognitionJob)) == 0
    assert db.scalar(select(func.count()).select_from(StorageCleanupJob)) == 0


def test_review_audit_failure_rolls_back_decision(client, headers, storage, db, user):
    job = upload(client, headers).json()
    obs = observation(client, headers, job["id"]).json()

    def fail(mapper, connection, target):
        if target.action == "recognition_observation_review":
            raise RuntimeError("Synthetic audit failure")

    event.listen(AuditEvent, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            review_observation(
                db,
                uuid.UUID(obs["id"]),
                SurveyReview(version=1, decision="UNKNOWN", notes="Synthetic review rollback"),
                user,
            )
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    assert db.scalar(select(func.count()).select_from(RecognitionReview)) == 0


def test_concurrent_postgres_reviews_have_one_winner(factory, user):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fastapi import HTTPException

    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL concurrency only")
    with factory() as db:
        job = RecognitionJob(
            id=uuid.uuid4(),
            created_by=user.id,
            created_at=datetime.now(UTC),
            kind="MODEL",
            storage_key=uuid.uuid4().hex + ".png",
            sha256="a" * 64,
            mime_type="image/png",
            result_json={},
        )
        db.add(job)
        db.flush()
        record = SurveyObservation(
            id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            payload_sha256="a" * 64,
            created_by=user.id,
            created_at=datetime.now(UTC),
            observed_at=datetime.now(UTC),
            device_job_id=job.id,
            notes="Concurrent synthetic",
            evidence_json={},
        )
        db.add(record)
        db.commit()
        record_id = record.id
    barrier = Barrier(2)

    def worker(decision):
        with factory() as db:
            actor = db.get(User, user.id)
            barrier.wait(timeout=10)
            try:
                review_observation(
                    db,
                    record_id,
                    SurveyReview(version=1, decision=decision, notes="Concurrent review"),
                    actor,
                )
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, ["UNKNOWN", "MORE_PHOTOS"]))
    assert sorted(results) == [200, 409]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RecognitionReview)) == 1


def test_preview_survives_lowered_upload_limit(client, headers, storage, monkeypatch):
    from app.config import get_settings

    image = Image.effect_noise((300, 300), 100).convert("RGB")
    target = io.BytesIO()
    image.save(target, format="PNG")
    response = upload(client, headers, data=target.getvalue())
    assert response.status_code == 201, response.text
    monkeypatch.setattr(get_settings(), "image_max_bytes", 1024)
    assert client.get(response.json()["content_url"]).status_code == 200


def test_process_adapter_timeout_is_unavailable(monkeypatch):
    import subprocess
    from pathlib import Path

    from app.recognition_encoder import EncoderUnavailable
    from app.recognition_http_encoder import ProcessCPUEncoder

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("synthetic", 10)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(EncoderUnavailable):
        _ = ProcessCPUEncoder("mobilenet_v3_small", Path("/missing")).spec


def test_pending_upload_recovery_ownership_and_consumption(client, headers, storage):
    job = upload(client, headers).json()
    pending = client.get("/api/v1/recognition/jobs").json()
    assert [j["id"] for j in pending["items"]] == [job["id"]]
    assert observation(client, headers, job["id"]).status_code == 201
    assert client.get("/api/v1/recognition/jobs").json()["items"] == []


def test_openapi_recognition_request_contracts(client):
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/api/v1/recognition/ocr"]["post"]["requestBody"]["content"][
        "multipart/form-data"
    ]["schema"]["required"] == ["file"]
    assert "human_checked" not in schema["components"]["schemas"]["SurveyCreate"]["properties"]
    assert "checked_manual_indices" in schema["components"]["schemas"]["SurveyReview"]["properties"]


def test_additive_migration_preserves_populated_predecessor(factory, registry):
    asset, maker = registry
    with factory.kw["bind"].connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.downgrade(config, "0010_embedding_index")
        before = connection.execute(text("SELECT * FROM assets")).mappings().all()
        claims = connection.execute(text("SELECT * FROM asset_identifiers")).mappings().all()
        connection.commit()
        command.upgrade(config, "head")
        assert connection.execute(text("SELECT * FROM assets")).mappings().all() == before
        assert (
            connection.execute(text("SELECT * FROM asset_identifiers")).mappings().all() == claims
        )
        assert connection.scalar(text("SELECT count(*) FROM recognition_jobs")) == 0
        command.check(config)

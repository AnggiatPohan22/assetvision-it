"""Synthetic isolated fixtures only. Fake calibration exercises policy, not model accuracy."""

import hashlib
import io
import math
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import event, func, inspect, select, update
from sqlalchemy.exc import IntegrityError

from app.catalog import DeviceCategory, DeviceModel, DeviceReferenceImage, Environment, Manufacturer
from app.models import AuditEvent, Role, User
from app.recognition_encoder import EncoderUnavailable
from app.recognition_index import catalog_snapshot, head, rebuild_index, search_models
from app.recognition_models import EmbeddingIndex, EmbeddingIndexState, ImageEmbedding
from app.recognition_schemas import EncoderSpec, RebuildRequest, SearchRequest
from app.storage import LocalStorageProvider


def picture(color="red", marker=0, size=(32, 32)):
    image = Image.new("RGB", size, color)
    image.putpixel((1, 0), (marker, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeEncoder:
    spec = EncoderSpec(
        name="test-only",
        version="synthetic-v1",
        weights_sha256="1" * 64,
        preprocess_version="2" * 64,
        dimensions=3,
    )

    def encode(self, image):
        return [float(x) for x in image.getpixel((0, 0))]


@pytest.fixture()
def encoder():
    return FakeEncoder()


@pytest.fixture()
def storage(tmp_path):
    return LocalStorageProvider(tmp_path / "private")


@pytest.fixture()
def catalog(db, user, storage):
    category = DeviceCategory(code="synthetic", name="Synthetic category")
    maker = Manufacturer(name="Synthetic maker")
    db.add_all([category, maker])
    db.flush()
    models = []
    for name, color in (("A", "red"), ("B", "green"), ("C", "blue"), ("D", "gray")):
        model = DeviceModel(
            id=uuid.uuid4(),
            category_id=category.id,
            manufacturer_id=maker.id,
            model_name=name,
            environment=Environment.BOTH,
        )
        db.add(model)
        db.flush()
        for marker in range(5):
            data = picture(color, marker)
            image_id = uuid.uuid4()
            key = image_id.hex + ".png"
            storage.put(key, data)
            db.add(
                DeviceReferenceImage(
                    id=image_id,
                    device_model_id=model.id,
                    storage_key=key,
                    sha256=hashlib.sha256(data).hexdigest(),
                    mime_type="image/png",
                    byte_size=len(data),
                    uploaded_by=user.id,
                    is_primary=marker == 0,
                )
            )
        models.append(model)
    db.commit()
    return models


def build(db, user, storage, encoder, *, version=None, report=None):
    version = version if version is not None else head(db).version
    fingerprint = catalog_snapshot(db).fingerprint if report is not None else None
    return rebuild_index(
        db,
        storage,
        encoder,
        RebuildRequest(
            expected_version=version,
            reason="Synthetic test rebuild",
            calibration_reference_fingerprint=fingerprint,
        ),
        user.id,
        report,
    )


def query(db, user, encoder, color="red", k=3):
    return search_models(db, encoder, picture(color), "image/png", SearchRequest(top_k=k), user.id)


def fake_report(db, encoder):
    snapshot = catalog_snapshot(db)
    counts = {}
    for ref in snapshot.references:
        counts.setdefault(str(ref.model_id), {"reference": 0, "calibration": 2, "test": 3})[
            "reference"
        ] += 1
    return {
        "synthetic": False,
        "dataset_selection_eligible": True,
        "top3_go_no_go": "GO",
        "encoder": encoder.spec.name,
        "encoder_version": encoder.spec.version,
        "weights_sha256": encoder.spec.weights_sha256,
        "preprocess_version": encoder.spec.preprocess_version,
        "embedding_dimensions": encoder.spec.dimensions,
        "per_model_counts": counts,
        "counts": {"unknown_calibration": 3, "unknown_test": 3},
        "manifest_sha256": "3" * 64,
        "threshold": 0.99,
        "metrics": {
            "top1_accuracy": 1.0,
            "top3_accuracy": 1.0,
            "unknown_precision": 1.0,
            "unknown_recall": 1.0,
            "unknown_false_accept_rate": 0.0,
            "known_false_reject_rate": 0.0,
        },
    }


def tally(db):
    return tuple(
        db.scalar(select(func.count()).select_from(table))
        for table in (EmbeddingIndex, ImageEmbedding, AuditEvent)
    )


def test_empty_state_and_no_default_encoder(db, user, encoder):
    result = query(db, user, None)
    assert result.status == "UNKNOWN_MODEL" and result.reason == "EMPTY_INDEX"
    assert not result.candidates and result.encoder is None
    assert head(db).version == 1 and tally(db)[:2] == (0, 0)


def test_atomic_versioned_rebuild_and_model_unique_ranking(db, user, catalog, encoder, storage):
    before = [(m.id, m.version) for m in catalog]
    record = build(db, user, storage, encoder)
    assert record.reference_count == 20 and head(db).version == 2
    assert tally(db) == (1, 20, 1)
    result = query(db, user, encoder)
    assert result.status == "UNCERTAIN" and result.reason == "UNCALIBRATED_SIMILARITY_ONLY"
    assert len(result.candidates) == 3 and len({c.device_model_id for c in result.candidates}) == 3
    assert result.candidates[0].device_model_id == catalog[0].id
    assert result.candidates[0].similarity == 1 and result.encoder == encoder.spec
    assert result.index_id == record.id and not result.calibrated
    assert [(m.id, m.version) for m in catalog] == before
    vectors = list(db.scalars(select(ImageEmbedding)))
    assert all(abs(sum(x * x for x in v.vector_data) - 1) < 1e-6 for v in vectors)
    next_record = build(db, user, storage, encoder)
    assert next_record.id != record.id and tally(db) == (2, 40, 2) and head(db).version == 3


def test_calibrated_known_and_unknown_no_forced_match(db, user, catalog, encoder, storage):
    build(db, user, storage, encoder, report=fake_report(db, encoder))
    known = query(db, user, encoder)
    assert known.status == "KNOWN_MODEL_CANDIDATE" and known.threshold == 0.99
    assert known.candidates[0].device_model_id == catalog[0].id
    unknown = query(db, user, encoder, "yellow")
    assert unknown.status == "UNKNOWN_MODEL" and not unknown.candidates and unknown.calibrated
    assert not hasattr(known, "asset_id") and "not confidence" in known.score_label
    build(db, user, storage, encoder)  # Calibration is never silently inherited by a new build.
    assert query(db, user, encoder).status == "UNCERTAIN"


@pytest.mark.parametrize("role", [Role.OFFICER, Role.VIEWER])
def test_only_admin_rebuilds_but_all_active_roles_read(db, user, catalog, encoder, storage, role):
    build(db, user, storage, encoder)
    user.role = role
    db.commit()
    before = tally(db)
    with pytest.raises(HTTPException) as error:
        build(db, user, storage, encoder)
    assert error.value.status_code == 403 and tally(db) == before
    assert query(db, user, encoder).candidates


def test_inactive_or_missing_actor_denied(db, user, catalog, encoder, storage):
    user.is_active = False
    db.commit()
    with pytest.raises(HTTPException) as error:
        query(db, user, encoder)
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        rebuild_index(
            db, storage, encoder, RebuildRequest(expected_version=1, reason="test"), uuid.uuid4()
        )
    assert error.value.status_code == 403


@pytest.mark.parametrize(
    "change", ["archive", "metadata", "photo-delete", "photo-hash", "new-model"]
)
def test_changed_catalog_returns_uncertain_until_explicit_rebuild(
    db, user, catalog, encoder, storage, change
):
    build(db, user, storage, encoder)
    if change == "archive":
        catalog[0].is_active = False
    elif change == "metadata":
        catalog[0].model_name = "Changed"
    elif change == "photo-delete":
        image = db.scalar(
            select(DeviceReferenceImage).where(
                DeviceReferenceImage.device_model_id == catalog[0].id
            )
        )
        image_id = image.id
        db.delete(image)
    elif change == "photo-hash":
        image = db.scalar(select(DeviceReferenceImage))
        image.sha256 = "0" * 64
    else:
        db.add(
            DeviceModel(
                category_id=catalog[0].category_id,
                manufacturer_id=catalog[0].manufacturer_id,
                model_name="Extra",
                environment=Environment.BOTH,
            )
        )
    db.commit()
    result = query(db, user, encoder)
    assert result.reason == "STALE_REFERENCE_INDEX" and not result.candidates
    if change == "photo-delete":
        historic = db.scalar(
            select(ImageEmbedding).where(ImageEmbedding.reference_snapshot_id == image_id)
        )
        assert historic.reference_image_id is None and historic.reference_snapshot_id == image_id
    if change == "archive":
        record = build(db, user, storage, encoder)
        assert record.reference_count == 15
        assert all(
            c.device_model_id != catalog[0].id for c in query(db, user, encoder, k=10).candidates
        )


def test_missing_or_version_mismatched_encoder_fails_closed(db, user, catalog, encoder, storage):
    build(db, user, storage, encoder)
    assert query(db, user, None).reason == "ENCODER_NOT_CONFIGURED"
    encoder.spec = encoder.spec.model_copy(update={"version": "different"})
    assert query(db, user, encoder).reason == "ENCODER_VERSION_MISMATCH"


@pytest.mark.parametrize(
    "bad", [[0, 0, 0], [1, 2], [math.nan, 0, 1], [math.inf, 0, 1], [True, 0, 1], None]
)
def test_bad_encoder_vector_rolls_back_without_publication(
    db, user, catalog, encoder, storage, bad
):
    build(db, user, storage, encoder)
    before = tally(db)
    encoder.encode = lambda image: bad
    with pytest.raises(HTTPException) as error:
        build(db, user, storage, encoder)
    assert error.value.status_code == 422 and tally(db) == before and head(db).version == 2
    assert query(db, user, encoder).status == "UNCERTAIN"


@pytest.mark.parametrize("failure", ["missing", "checksum", "decode", "encoder"])
def test_rebuild_failure_preserves_old_index(db, user, catalog, encoder, storage, failure):
    build(db, user, storage, encoder)
    before = tally(db)
    row = db.scalar(select(DeviceReferenceImage))
    if failure == "missing":
        storage.delete(row.storage_key)
    elif failure == "checksum":
        storage.delete(row.storage_key)
        storage.put(row.storage_key, b"wrong bytes")
    elif failure == "decode":
        storage.delete(row.storage_key)
        storage.put(row.storage_key, b"bad png")
        row.sha256 = hashlib.sha256(b"bad png").hexdigest()
        row.byte_size = 7
        db.commit()
    else:

        def fail(image):
            raise EncoderUnavailable("offline")

        encoder.encode = fail
    with pytest.raises(HTTPException):
        build(db, user, storage, encoder)
    assert tally(db) == before and head(db).version == 2


def test_audit_failure_rolls_back_generation_and_head(db, user, catalog, encoder, storage, factory):
    before = tally(db)

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO audit_events"):
            raise RuntimeError("Synthetic audit unavailable")

    engine = factory.kw["bind"]
    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            build(db, user, storage, encoder)
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert tally(db) == before and head(db).current_index_id is None and head(db).version == 1


def test_stale_head_and_dirty_session_rejected(db, user, catalog, encoder, storage):
    build(db, user, storage, encoder)
    before = tally(db)
    with pytest.raises(HTTPException) as error:
        build(db, user, storage, encoder, version=1)
    assert error.value.status_code == 409 and tally(db) == before
    actor_id = user.id
    catalog[0].model_name = "Unsaved"
    with pytest.raises(HTTPException) as error:
        search_models(db, encoder, picture(), "image/png", SearchRequest(), actor_id)
    assert error.value.status_code == 409 and catalog[0] in db.dirty
    db.rollback()


@pytest.mark.parametrize(
    "field,value",
    [
        ("synthetic", True),
        ("dataset_selection_eligible", False),
        ("top3_go_no_go", "NO_GO"),
        ("encoder_version", "wrong"),
        ("threshold", math.nan),
        ("metrics", None),
        ("per_model_counts", {}),
        ("manifest_sha256", "wrong"),
    ],
)
def test_ineligible_or_mismatched_calibration_rejected(
    db, user, catalog, encoder, storage, field, value
):
    report = fake_report(db, encoder)
    report[field] = value
    before = tally(db)
    with pytest.raises(HTTPException) as error:
        build(db, user, storage, encoder, report=report)
    assert error.value.status_code == 422 and tally(db) == before


def test_calibration_source_fingerprint_must_match(db, user, catalog, encoder, storage):
    with pytest.raises(HTTPException) as error:
        rebuild_index(
            db,
            storage,
            encoder,
            RebuildRequest(
                expected_version=1, reason="test", calibration_reference_fingerprint="0" * 64
            ),
            user.id,
            fake_report(db, encoder),
        )
    assert error.value.status_code == 409


@pytest.mark.parametrize(
    "changes", [{"top_k": 0}, {"top_k": 11}, {"top_k": True}, {"unexpected": 1}]
)
def test_search_input_is_strict(changes):
    with pytest.raises(ValidationError):
        SearchRequest(**changes)


@pytest.mark.parametrize(
    "data,mime,status",
    [
        (b"", "image/png", 413),
        (b"not png", "image/png", 415),
        (picture(), "image/jpeg", 415),
        (b"\x89PNG\r\n\x1a\nBAD", "image/png", 422),
    ],
)
def test_query_image_validation_precedes_empty_index(db, user, encoder, data, mime, status):
    with pytest.raises(HTTPException) as error:
        search_models(db, encoder, data, mime, SearchRequest(), user.id)
    assert error.value.status_code == status


def test_empty_rebuild_has_no_forced_candidates(db, user, encoder, storage):
    record = build(db, user, storage, encoder)
    assert record.reference_count == 0 and query(db, user, encoder).reason == "NO_ACTIVE_REFERENCES"


@pytest.mark.parametrize("table", [EmbeddingIndex, ImageEmbedding, EmbeddingIndexState])
def test_history_and_head_direct_delete_guard(db, user, catalog, encoder, storage, table):
    build(db, user, storage, encoder)
    with pytest.raises(IntegrityError):
        db.execute(table.__table__.delete())
        db.commit()
    db.rollback()
    assert head(db).version == 2 and tally(db) == (1, 20, 1)


def test_direct_vector_and_generation_mutation_guard(db, user, catalog, encoder, storage):
    build(db, user, storage, encoder)
    for statement in (
        update(ImageEmbedding).values(vector_data=[1, 0, 0]),
        update(EmbeddingIndex).values(reference_count=0),
        update(EmbeddingIndexState).values(version=1),
    ):
        with pytest.raises(IntegrityError):
            db.execute(statement)
            db.commit()
        db.rollback()
    assert query(db, user, encoder).candidates


def test_new_migration_preserves_previous_data_and_checks(factory, db, user, catalog):
    original = [(m.id, m.version, m.model_name) for m in catalog]
    db.rollback()
    with factory.kw["bind"].connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.downgrade(config, "0009_observations")
        assert "image_embeddings" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        command.check(config)
        connection.commit()
    db.expire_all()
    assert [(m.id, m.version, m.model_name) for m in catalog] == original
    assert head(db).version == 1


def test_populated_embedding_downgrade_refuses(factory, db, user, catalog, encoder, storage):
    build(db, user, storage, encoder)
    db.rollback()
    with factory.kw["bind"].connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        with pytest.raises(RuntimeError, match="Cannot downgrade populated"):
            command.downgrade(config, "0009_observations")
        connection.rollback()


def test_postgres_concurrent_rebuilds_cas(factory, db, user, catalog, storage):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL multi-session row locks")
    actor_id = user.id
    barrier = Barrier(2)
    db.rollback()

    def worker(_):
        encoder = FakeEncoder()
        original = encoder.encode
        first = True

        def synchronized(image):
            nonlocal first
            if first:
                first = False
                barrier.wait(timeout=20)
            return original(image)

        encoder.encode = synchronized
        with factory() as session:
            try:
                rebuild_index(
                    session,
                    storage,
                    encoder,
                    RebuildRequest(expected_version=1, reason="Race"),
                    actor_id,
                )
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(worker, [0, 1])) == [200, 409]
    db.expire_all()
    assert tally(db) == (1, 20, 1) and head(db).version == 2


def test_catalog_change_during_encoding_is_not_published(
    db, user, catalog, encoder, storage, factory
):
    model_id = catalog[0].id
    original = encoder.encode
    changed = False

    def mutate(image):
        nonlocal changed
        if not changed:
            changed = True
            with factory() as other:
                record = other.get(DeviceModel, model_id)
                record.is_active = False
                other.commit()
        return original(image)

    encoder.encode = mutate
    with pytest.raises(HTTPException) as error:
        build(db, user, storage, encoder)
    assert error.value.status_code == 409 and tally(db) == (0, 0, 0) and head(db).version == 1


def test_completed_generation_rejects_extra_rows(db, user, catalog, encoder, storage):
    record = build(db, user, storage, encoder)
    ref = db.scalar(select(DeviceReferenceImage))
    db.add(
        ImageEmbedding(
            index_id=record.id,
            reference_image_id=ref.id,
            reference_snapshot_id=uuid.uuid4(),
            device_model_id=ref.device_model_id,
            source_sha256=ref.sha256,
            vector_data=[1, 0, 0],
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert tally(db) == (1, 20, 1) and query(db, user, encoder).candidates


@pytest.mark.parametrize(
    "operation", ["rebuild-revoke", "query-revoke", "query-catalog", "query-publish"]
)
def test_revalidation_after_cpu_work(db, user, catalog, encoder, storage, factory, operation):
    if operation != "rebuild-revoke":
        build(db, user, storage, encoder)
    actor_id = user.id
    model_id = catalog[0].id
    original = encoder.encode
    changed = False

    def mutate(image):
        nonlocal changed
        if not changed:
            changed = True
            with factory() as other:
                if operation.endswith("revoke"):
                    other.get(User, actor_id).is_active = False
                    other.commit()
                elif operation == "query-catalog":
                    other.get(DeviceModel, model_id).is_active = False
                    other.commit()
                else:
                    rebuild_index(
                        other,
                        storage,
                        FakeEncoder(),
                        RebuildRequest(expected_version=2, reason="Concurrent generation"),
                        actor_id,
                    )
        return original(image)

    encoder.encode = mutate
    if operation.endswith("revoke"):
        with pytest.raises(HTTPException) as error:
            if operation == "rebuild-revoke":
                build(db, user, storage, encoder)
            else:
                search_models(db, encoder, picture(), "image/png", SearchRequest(), actor_id)
        assert error.value.status_code == 403
        assert tally(db)[:2] == ((0, 0) if operation == "rebuild-revoke" else (1, 20))
    else:
        result = search_models(db, encoder, picture(), "image/png", SearchRequest(), actor_id)
        assert result.status == "UNCERTAIN" and not result.candidates
        assert result.reason == (
            "STALE_REFERENCE_INDEX"
            if operation == "query-catalog"
            else "INDEX_CHANGED_DURING_QUERY"
        )

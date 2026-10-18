import hashlib
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from conftest import csrf_headers, session_headers, sign_in
from PIL import Image
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from app.catalog import (
    DeviceCategory,
    DeviceModel,
    DeviceReferenceImage,
    Environment,
    Manufacturer,
    StorageCleanupJob,
)
from app.config import get_settings
from app.image_service import cleanup_pending
from app.main import app
from app.models import AuditEvent, Role
from app.storage import LocalStorageProvider, StorageError, get_storage


def picture(format="PNG", size=(24, 16), **options) -> bytes:
    target = io.BytesIO()
    Image.new("RGB", size, "orange").save(target, format=format, **options)
    return target.getvalue()


@pytest.fixture()
def storage(tmp_path):
    provider = LocalStorageProvider(tmp_path / "private")
    app.dependency_overrides[get_storage] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture()
def image_model(db):
    category = DeviceCategory(code="access-point", name="Access Point")
    maker = Manufacturer(name="Synthetic maker")
    db.add_all([category, maker])
    db.flush()
    model = DeviceModel(
        category_id=category.id,
        manufacturer_id=maker.id,
        model_name="Reference model",
        environment=Environment.BOTH,
    )
    db.add(model)
    db.commit()
    return model


@pytest.fixture()
def headers(client, user, password):
    assert sign_in(client, password).status_code == 200
    return session_headers(client)


def path(model) -> str:
    return f"/api/v1/device-models/{model.id}/reference-images"


def upload(client, model, headers, *, version=1, data=None, mime="image/png", **fields):
    return client.post(
        path(model),
        files={"file": ("../../host-secret.png", data if data is not None else picture(), mime)},
        data={"version": str(version), **fields},
        headers=headers,
    )


@pytest.mark.parametrize(
    "format,mime", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")]
)
def test_upload_serve_sanitizes_metadata(
    client, headers, image_model, storage, db, user, format, mime
):
    exif = Image.Exif()
    exif[270] = "PRIVATE GPS TEST MARKER"
    exif[274] = 6
    raw = picture(format, exif=exif)
    response = upload(client, image_model, headers, data=raw, mime=mime, angle=" Front   view ")
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["model_version"] == 2
    metadata = result["image"]
    assert metadata["angle"] == "Front view" and metadata["is_primary"]
    assert metadata["uploaded_by"] == str(user.id)
    assert "storage_key" not in response.text and str(storage.root) not in response.text
    served = client.get(metadata["content_url"])
    assert served.status_code == 200 and served.headers["content-type"] == mime
    assert served.headers["x-content-type-options"] == "nosniff"
    assert served.headers["cache-control"] == "no-store"
    assert metadata["sha256"] == hashlib.sha256(served.content).hexdigest()
    assert metadata["byte_size"] == len(served.content)
    assert b"PRIVATE GPS TEST MARKER" not in served.content
    with Image.open(io.BytesIO(served.content)) as decoded:
        assert not decoded.getexif() and decoded.size == (16, 24)
    assert len(list(storage.root.iterdir())) == 1
    assert db.scalar(select(func.count()).select_from(StorageCleanupJob)) == 0


def test_five_images_limit_and_primary_delete(
    client, headers, image_model, storage, db, monkeypatch
):
    monkeypatch.setattr(get_settings(), "image_max_per_model", 5)
    metadata = []
    for version in range(1, 6):
        response = upload(client, image_model, headers, version=version)
        assert response.status_code == 201, response.text
        metadata.append(response.json()["image"])
    listed = client.get(path(image_model)).json()
    assert len(listed["items"]) == 5 and listed["model_version"] == 6
    assert sum(item["is_primary"] for item in listed["items"]) == 1
    assert upload(client, image_model, headers, version=6).status_code == 409
    response = client.delete(
        path(image_model) + "/" + metadata[0]["id"], params={"version": 6}, headers=headers
    )
    assert response.status_code == 204 and response.headers["x-model-version"] == "7"
    assert client.get(metadata[0]["content_url"]).status_code == 404
    assert len(list(storage.root.iterdir())) == 4
    assert sum(item["is_primary"] for item in client.get(path(image_model)).json()["items"]) == 1
    assert db.scalar(select(func.count()).select_from(StorageCleanupJob)) == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "reference_image_delete")
        )
        == 1
    )


@pytest.mark.parametrize("role", [Role.OFFICER, Role.VIEWER])
def test_read_only_roles(client, headers, image_model, storage, db, user, role):
    image = upload(client, image_model, headers).json()["image"]
    user.role = role
    db.commit()
    assert client.get(path(image_model)).status_code == 200
    assert client.get(image["content_url"]).status_code == 200
    assert upload(client, image_model, headers, version=2).status_code == 403
    assert (
        client.delete(
            path(image_model) + "/" + image["id"], params={"version": 2}, headers=headers
        ).status_code
        == 403
    )


def test_anonymous_and_csrf(client, headers, image_model, storage):
    image = upload(client, image_model, headers).json()["image"]
    assert upload(client, image_model, {}, version=2).status_code == 403
    assert (
        client.delete(path(image_model) + "/" + image["id"], params={"version": 2}).status_code
        == 403
    )
    client.cookies.clear()
    anonymous_csrf = csrf_headers(client)
    assert client.get(path(image_model)).status_code == 401
    assert client.get(image["content_url"]).status_code == 401
    assert upload(client, image_model, anonymous_csrf).status_code == 401
    assert (
        client.delete(
            path(image_model) + "/" + image["id"], params={"version": 2}, headers=anonymous_csrf
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "raw,mime,status",
    [
        (b"not an image", "image/png", 415),
        (b"<svg></svg>", "image/svg+xml", 415),
        (b"\x89PNG\r\n\x1a\ncorrupt", "image/png", 422),
        (picture(), "image/jpeg", 415),
        (picture("GIF"), "image/gif", 415),
        (picture()[:40], "image/png", 422),
        (b"", "image/png", 415),
    ],
)
def test_invalid_content_no_orphans(client, headers, image_model, storage, db, raw, mime, status):
    response = upload(client, image_model, headers, data=raw, mime=mime)
    assert response.status_code == status
    assert not storage.root.exists()
    assert db.scalar(select(func.count()).select_from(DeviceReferenceImage)) == 0
    assert db.scalar(select(func.count()).select_from(StorageCleanupJob)) == 0


@pytest.mark.parametrize(
    "mode", ["file_bytes", "body_bytes", "dimension", "pixels", "animation", "bomb"]
)
def test_resource_limits(client, headers, image_model, storage, monkeypatch, mode):
    data = picture()
    expected = 422
    if mode in {"file_bytes", "body_bytes"}:
        monkeypatch.setattr(get_settings(), "image_max_bytes", 1024)
        data = b"x" * (1025 if mode == "file_bytes" else 70000)
        expected = 413
    elif mode == "dimension":
        monkeypatch.setattr(get_settings(), "image_max_dimension", 64)
        data = picture(size=(65, 16))
    elif mode == "pixels":
        monkeypatch.setattr(get_settings(), "image_max_pixels", 4096)
        data = picture(size=(65, 65))
    elif mode == "animation":
        target = io.BytesIO()
        Image.new("RGB", (16, 16), "red").save(
            target,
            "PNG",
            save_all=True,
            append_images=[Image.new("RGB", (16, 16), "blue")],
            duration=100,
        )
        data = target.getvalue()
    else:
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 200)
    assert upload(client, image_model, headers, data=data).status_code == expected
    assert not storage.root.exists()


def test_versions_archive_missing_and_wrong_parent(client, headers, image_model, storage, db):
    image = upload(client, image_model, headers).json()["image"]
    assert upload(client, image_model, headers, version=1).status_code == 409
    item = path(image_model) + "/" + image["id"]
    assert client.delete(item, headers=headers).status_code == 422
    assert client.delete(item, params={"version": 1}, headers=headers).status_code == 409
    wrong = image["content_url"].replace(str(image_model.id), str(uuid.uuid4()))
    assert client.get(wrong).status_code == 404
    assert (
        client.delete(
            path(image_model) + "/" + str(uuid.uuid4()), params={"version": 2}, headers=headers
        ).status_code
        == 404
    )
    archived = client.post(
        f"/api/v1/device-models/{image_model.id}/archive", json={"version": 2}, headers=headers
    )
    assert archived.status_code == 200
    assert upload(client, image_model, headers, version=3).status_code == 409
    assert client.get(image["content_url"]).status_code == 200
    assert len(list(storage.root.iterdir())) == 1


@pytest.mark.parametrize(
    "mode",
    [
        "missing_version",
        "unknown_field",
        "multiple_files",
        "duplicate_version",
        "no_file",
        "bad_angle",
        "bad_version",
        "wrong_content_type",
    ],
)
def test_multipart_validation(client, headers, image_model, storage, mode):
    data = {"version": "1"}
    files = [("file", ("image.png", picture(), "image/png"))]
    if mode == "missing_version":
        data = {}
    elif mode == "unknown_field":
        data["storage_key"] = "/etc/passwd"
    elif mode == "multiple_files":
        files.append(files[0])
    elif mode == "duplicate_version":
        files.append(("version", (None, "1")))
    elif mode == "no_file":
        files = []
    elif mode == "bad_angle":
        data["angle"] = "x" * 101
    elif mode == "bad_version":
        data["version"] = "-1"
    if mode == "wrong_content_type":
        response = client.post(path(image_model), json={}, headers=headers)
    else:
        response = client.post(path(image_model), data=data, files=files, headers=headers)
    assert response.status_code in {400, 415, 422}, response.text
    assert not storage.root.exists()


@pytest.mark.parametrize("action", ["upload", "delete"])
def test_db_audit_failure_preserves_consistency(client, headers, image_model, storage, db, action):
    image = upload(client, image_model, headers).json()["image"] if action == "delete" else None

    def fail(mapper, connection, target):
        if target.action == f"reference_image_{action}":
            raise IntegrityError("synthetic audit failure", {}, Exception())

    event.listen(AuditEvent, "before_insert", fail)
    try:
        response = (
            upload(client, image_model, headers)
            if action == "upload"
            else client.delete(
                path(image_model) + "/" + image["id"], params={"version": 2}, headers=headers
            )
        )
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    assert response.status_code == 409
    assert db.scalar(select(func.count()).select_from(DeviceReferenceImage)) == (
        0 if action == "upload" else 1
    )
    assert len(list(storage.root.iterdir())) == (0 if action == "upload" else 1)
    assert db.scalar(select(func.count()).select_from(StorageCleanupJob)) == 0
    if image:
        assert client.get(image["content_url"]).status_code == 200


def test_partial_write_compensated(client, headers, image_model, storage, db, monkeypatch):
    original = storage.put

    def fail(key, data):
        original(key, data)
        raise StorageError("synthetic partial write")

    monkeypatch.setattr(storage, "put", fail)
    assert upload(client, image_model, headers).status_code == 503
    assert list(storage.root.iterdir()) == []
    assert db.scalar(select(func.count()).select_from(StorageCleanupJob)) == 0


def test_failed_unlink_is_durable_and_retryable(
    client, headers, image_model, storage, db, monkeypatch
):
    image = upload(client, image_model, headers).json()["image"]
    original = storage.delete

    def fail(key):
        raise StorageError("synthetic unlink failure")

    monkeypatch.setattr(storage, "delete", fail)
    assert (
        client.delete(
            path(image_model) + "/" + image["id"], params={"version": 2}, headers=headers
        ).status_code
        == 204
    )
    assert client.get(image["content_url"]).status_code == 404
    job = db.scalar(select(StorageCleanupJob))
    assert job is not None and len(list(storage.root.iterdir())) == 1
    job.created_at = datetime.now(UTC) - timedelta(minutes=11)
    db.commit()
    monkeypatch.setattr(storage, "delete", original)
    assert cleanup_pending(db, storage) == 1
    assert list(storage.root.iterdir()) == []
    assert cleanup_pending(db, storage) == 0


def test_crash_cleanup_grace_and_reference_protection(client, headers, image_model, storage, db):
    image = upload(client, image_model, headers).json()["image"]
    record = db.get(DeviceReferenceImage, uuid.UUID(image["id"]))
    key = uuid.uuid4().hex + ".png"
    job = StorageCleanupJob(storage_key=key)
    db.add(job)
    db.commit()
    storage.put(key, picture())
    assert cleanup_pending(db, storage) == 0
    job.created_at = datetime.now(UTC) - timedelta(minutes=11)
    db.add(StorageCleanupJob(storage_key=record.storage_key, created_at=job.created_at))
    db.commit()
    assert cleanup_pending(db, storage) == 2
    assert client.get(image["content_url"]).status_code == 200
    assert len(list(storage.root.iterdir())) == 1


def test_missing_and_corrupt_stored_file(client, headers, image_model, storage, db):
    image = upload(client, image_model, headers).json()["image"]
    record = db.get(DeviceReferenceImage, uuid.UUID(image["id"]))
    storage.path(record.storage_key).write_bytes(b"corrupted")
    assert client.get(image["content_url"]).status_code == 503
    storage.delete(record.storage_key)
    assert client.get(image["content_url"]).status_code == 404


@pytest.mark.parametrize(
    "key", ["../outside.png", "/tmp/outside.png", "a/b.png", "C:\\secret.png", "invalid", ""]
)
def test_storage_rejects_unsafe_keys(tmp_path, key):
    provider = LocalStorageProvider(tmp_path)
    with pytest.raises(StorageError):
        provider.put(key, b"anything")
    with pytest.raises(StorageError):
        provider.read(key)
    with pytest.raises(StorageError):
        provider.delete(key)


def test_storage_exclusive_and_symlink_safe(tmp_path):
    provider = LocalStorageProvider(tmp_path / "private")
    key = uuid.uuid4().hex + ".png"
    provider.put(key, b"original")
    with pytest.raises(StorageError):
        provider.put(key, b"overwrite")
    assert provider.read(key) == b"original"
    secret = tmp_path / "secret"
    secret.write_bytes(b"secret")
    other = uuid.uuid4().hex + ".png"
    provider.path(other).symlink_to(secret)
    with pytest.raises(StorageError):
        provider.read(other)
    provider.delete(other)
    assert secret.read_bytes() == b"secret"
    assert (provider.path(key).stat().st_mode & 0o777) == 0o600


def test_postgres_concurrent_uploads_serialize(client, headers, image_model, storage, factory, db):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: upload(client, image_model, headers).status_code, range(2))
        )
    assert sorted(results) == [201, 409]
    assert db.scalar(select(func.count()).select_from(DeviceReferenceImage)) == 1
    assert len(list(storage.root.iterdir())) == 1


def test_upload_cleanup_failure_is_retryable(
    client, headers, image_model, storage, db, monkeypatch
):
    original_put, original_delete = storage.put, storage.delete

    def fail_put(key, data):
        original_put(key, data)
        raise StorageError("synthetic partial write")

    def fail_delete(key):
        raise StorageError("synthetic cleanup failure")

    monkeypatch.setattr(storage, "put", fail_put)
    monkeypatch.setattr(storage, "delete", fail_delete)
    assert upload(client, image_model, headers).status_code == 503
    assert db.scalar(select(func.count()).select_from(DeviceReferenceImage)) == 0
    job = db.scalar(select(StorageCleanupJob))
    assert job is not None
    job.created_at = datetime.now(UTC) - timedelta(minutes=11)
    db.commit()
    monkeypatch.setattr(storage, "delete", original_delete)
    assert cleanup_pending(db, storage) == 1
    assert list(storage.root.iterdir()) == []


def test_collision_never_removes_existing_file(
    client, headers, image_model, storage, db, monkeypatch
):
    chosen_id = uuid.uuid4()
    key = chosen_id.hex + ".png"
    storage.put(key, b"existing private content")
    monkeypatch.setattr("app.image_service.uuid.uuid4", lambda: chosen_id)
    assert upload(client, image_model, headers).status_code == 503
    assert storage.read(key) == b"existing private content"
    assert db.scalar(select(func.count()).select_from(StorageCleanupJob)) == 0


def test_trailing_payload_is_removed(client, headers, image_model, storage):
    result = upload(
        client, image_model, headers, data=picture() + b"<script>private-marker</script>"
    )
    assert result.status_code == 201
    assert b"private-marker" not in client.get(result.json()["image"]["content_url"]).content


def test_backend_caps_chunked_multipart_before_parsing(
    client, headers, image_model, storage, monkeypatch
):
    monkeypatch.setattr(get_settings(), "image_max_bytes", 1024)

    def chunks():
        for _ in range(70):
            yield b"x" * 1024

    response = client.post(
        path(image_model),
        content=chunks(),
        headers=headers | {"Content-Type": "multipart/form-data; boundary=test"},
    )
    assert response.status_code == 413
    assert not storage.root.exists()

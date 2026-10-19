"""Optional real CPU/weights integration; generated photos only, no accuracy claims."""

import hashlib
import importlib.util
import io
import json
import math
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from PIL import Image

from app.catalog import DeviceCategory, DeviceModel, DeviceReferenceImage, Environment, Manufacturer
from app.recognition_encoder import EncoderUnavailable, TorchCPUEncoder, decode_image
from app.recognition_index import rebuild_index, search_models
from app.recognition_schemas import RebuildRequest, SearchRequest
from app.storage import LocalStorageProvider

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("torch") is None, reason="Optional CPU encoder image only"
)


@pytest.mark.parametrize(
    "name,dimensions", [("mobilenet_v3_small", 576), ("shufflenet_v2_x0_5", 1024)]
)
def test_cpu_adapter_local_weights_and_uncalibrated_index(db, user, tmp_path, name, dimensions):
    encoder = TorchCPUEncoder(name, Path("/opt/weights/hub/checkpoints"))
    assert encoder.spec.dimensions == dimensions
    assert (
        encoder.spec.preprocess_version
        == "fb3c39345e781c64a0f391dd2412de13232f6f373947464b0f5765e85038ceef"
    )
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), "orange").save(buffer, format="PNG")
    data = buffer.getvalue()
    with decode_image(data, "image/png") as image:
        vector = encoder.encode(image)
    assert len(vector) == dimensions and abs(math.fsum(x * x for x in vector) - 1) < 1e-6
    category = DeviceCategory(code="cpu-synthetic", name="Synthetic")
    maker = Manufacturer(name="CPU Synthetic")
    db.add_all([category, maker])
    db.flush()
    model = DeviceModel(
        category_id=category.id,
        manufacturer_id=maker.id,
        model_name="Generated only",
        environment=Environment.BOTH,
    )
    db.add(model)
    db.flush()
    storage = LocalStorageProvider(tmp_path / "private")
    key = "1" * 32 + ".png"
    storage.put(key, data)
    db.add(
        DeviceReferenceImage(
            device_model_id=model.id,
            storage_key=key,
            sha256=hashlib.sha256(data).hexdigest(),
            mime_type="image/png",
            byte_size=len(data),
            uploaded_by=user.id,
        )
    )
    db.commit()
    record = rebuild_index(
        db,
        storage,
        encoder,
        RebuildRequest(expected_version=1, reason="CPU integration only"),
        user.id,
    )
    result = search_models(db, encoder, data, "image/png", SearchRequest(), user.id)
    assert result.index_id == record.id and result.status == "UNCERTAIN"
    assert result.reason == "UNCALIBRATED_SIMILARITY_ONLY" and not result.calibrated
    assert abs(result.candidates[0].similarity - 1) < 1e-6


def test_cpu_adapter_never_downloads_and_rejects_invalid_weights(tmp_path, monkeypatch):
    import torch

    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(torch.hub, "download_url_to_file", forbidden)
    with pytest.raises(EncoderUnavailable):
        TorchCPUEncoder("unselected", tmp_path)
    with pytest.raises(EncoderUnavailable):
        TorchCPUEncoder("mobilenet_v3_small", tmp_path)
    (tmp_path / "mobilenet_v3_small-047dcff4.pth").write_bytes(b"bad weights")
    with pytest.raises(EncoderUnavailable, match="checksum"):
        TorchCPUEncoder("mobilenet_v3_small", tmp_path)


def test_real_cli_status_rebuild_search_on_isolated_sqlite(tmp_path, user):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models import User

    url = "sqlite:///" + str(tmp_path / "cli.db")
    engine = create_engine(url)
    with engine.connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.commit()
    with Session(engine) as session:
        actor = User(
            id=uuid.uuid4(),
            email="synthetic-cli@example.test",
            name="Synthetic CLI",
            role=user.role,
            password_hash=user.password_hash,
            is_active=True,
        )
        category = DeviceCategory(code="cli-synthetic", name="Synthetic CLI category")
        maker = Manufacturer(name="Synthetic CLI maker")
        session.add_all([actor, category, maker])
        session.flush()
        model = DeviceModel(
            category_id=category.id,
            manufacturer_id=maker.id,
            model_name="CLI generated",
            environment=Environment.BOTH,
        )
        session.add(model)
        session.flush()
        buffer = io.BytesIO()
        Image.new("RGB", (64, 64), "orange").save(buffer, format="PNG")
        data = buffer.getvalue()
        storage = LocalStorageProvider(tmp_path / "storage")
        key = "2" * 32 + ".png"
        storage.put(key, data)
        session.add(
            DeviceReferenceImage(
                device_model_id=model.id,
                storage_key=key,
                sha256=hashlib.sha256(data).hexdigest(),
                byte_size=len(data),
                mime_type="image/png",
                uploaded_by=actor.id,
            )
        )
        actor_id = str(actor.id)
        session.commit()
    env = {**os.environ, "DATABASE_URL": url, "IMAGE_STORAGE_ROOT": str(tmp_path / "storage")}
    base = [sys.executable, "-m", "app.recognition_cli", "--actor-id", actor_id]

    def run(arguments, code=0):
        result = subprocess.run(
            base + arguments, env=env, text=True, capture_output=True, check=False
        )
        assert result.returncode == code, result.stderr
        return json.loads(result.stdout) if code == 0 else result.stderr

    before = run(["status"])
    assert before["generation_version"] == 1 and before["active_reference_count"] == 1
    built = run(
        [
            "rebuild",
            "--encoder",
            "mobilenet_v3_small",
            "--expected-version",
            "1",
            "--reason",
            "CLI integration",
            "--confirm-rebuild",
        ]
    )
    assert (
        built["reference_count"] == 1
        and built["generation_version"] == 2
        and not built["calibrated"]
    )
    source = tmp_path / "query.png"
    source.write_bytes(data)
    result = run(
        [
            "search",
            "--encoder",
            "mobilenet_v3_small",
            "--image",
            str(source),
            "--mime-type",
            "image/png",
        ]
    )
    assert result["status"] == "UNCERTAIN" and len(result["candidates"]) == 1
    assert "rejected (409)" in run(
        [
            "rebuild",
            "--encoder",
            "mobilenet_v3_small",
            "--expected-version",
            "1",
            "--reason",
            "Stale CLI",
            "--confirm-rebuild",
        ],
        2,
    )
    engine.dispose()


@pytest.mark.parametrize("name", ["mobilenet_v3_small", "shufflenet_v2_x0_5"])
def test_http_process_encoder_local_cpu(name):
    from app.recognition_http_encoder import ProcessCPUEncoder

    encoder = ProcessCPUEncoder(name, Path("/opt/weights/hub/checkpoints"))
    with Image.new("RGB", (48, 32), "orange") as image:
        values = encoder.encode(image)
    assert len(values) == encoder.spec.dimensions
    assert abs(math.fsum(v * v for v in values) - 1) < 1e-6

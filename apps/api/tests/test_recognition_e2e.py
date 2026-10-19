"""Task3-06 scenario evaluation. Generated images/identifiers only, never accuracy data.

Real index/search is uncalibrated. Accepted visual cases explicitly inject the *post-search*
acceptance result to exercise fusion/review; no real-evaluation provenance is fabricated and
no calibration is persisted. HTTP/DB/storage/auth/normalization/fusion/review remain real.
"""

import hashlib
import io
import uuid
from datetime import datetime

import pytest
from conftest import session_headers, sign_in
from PIL import Image
from sqlalchemy import select

from app.asset_location_service import initial_placement
from app.assets import AssetIdentifier, AssetUnit
from app.catalog import DeviceCategory, DeviceModel, DeviceReferenceImage, Manufacturer
from app.locations import Location
from app.main import app
from app.models import AuditEvent
from app.ocr_schemas import OCRLine, OCRReading
from app.recognition_index import rebuild_index
from app.recognition_routes import get_encoder, get_ocr_engine
from app.recognition_schemas import EncoderSpec, RebuildRequest
from app.storage import LocalStorageProvider, get_storage


def picture(color):
    target = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(target, format="PNG")
    return target.getvalue()


class SyntheticEncoder:
    spec = EncoderSpec(
        name="synthetic-e2e-only",
        version="v1",
        weights_sha256="1" * 64,
        preprocess_version="2" * 64,
        dimensions=3,
    )

    def encode(self, image):
        return list(image.getpixel((0, 0)))


class SyntheticOCR:
    def recognize(self, image):
        # Deliberate OCR false positive: a plausible serial belongs to a different AP.
        return OCRReading(
            engine_version="synthetic-e2e-only",
            model_fingerprint="3" * 64,
            lines=(OCRLine(text="SN: EVAL000003", score=0.99),),
        )


@pytest.fixture()
def scenario(db, user, tmp_path, monkeypatch):
    import app.recognition_routes as routes

    storage = LocalStorageProvider(tmp_path / "photos")
    encoder = SyntheticEncoder()
    category = DeviceCategory(code="e2e-only", name="Synthetic AP")
    maker = Manufacturer(name="Synthetic evaluation only")
    db.add_all([category, maker])
    db.flush()
    models = []
    for n, color in enumerate(("red", "green", "blue", "gray")):
        model = DeviceModel(
            category_id=category.id,
            manufacturer_id=maker.id,
            model_name=f"Synthetic model {n}",
            environment="both",
        )
        db.add(model)
        db.flush()
        models.append(model)
        data = picture(color)
        key = uuid.uuid4().hex + ".png"
        storage.put(key, data)
        db.add(
            DeviceReferenceImage(
                device_model_id=model.id,
                storage_key=key,
                sha256=hashlib.sha256(data).hexdigest(),
                byte_size=len(data),
                mime_type="image/png",
                uploaded_by=user.id,
            )
        )
    locations = [
        Location(code=f"eval-{n}", name=name, kind="AREA")
        for n, name in enumerate(("Lounge", "Lobby", "Villa 1", "Villa 10", "Shared area"))
    ]
    db.add_all(locations)
    db.flush()
    assets = []
    for n in range(8):
        asset = AssetUnit(asset_code=f"EVAL-AP-{n + 1:03}", device_model_id=models[0].id)
        db.add(asset)
        db.flush()
        assets.append(asset)
        db.add(
            AssetIdentifier(
                asset_id=asset.id,
                identifier_type="SERIAL_NUMBER",
                raw_value=f"EVAL{n + 1:06}",
                normalized_value=f"EVAL{n + 1:06}",
                source="MANUAL",
                verification_status="VERIFIED",
            )
        )
    db.commit()
    for n, asset in enumerate(assets):
        initial_placement(
            db,
            asset.id,
            asset.version,
            locations[min(n, 4)].id,
            "Synthetic approved placement",
            user,
        )
    rebuild_index(
        db,
        storage,
        encoder,
        RebuildRequest(expected_version=1, reason="Synthetic uncalibrated E2E"),
        user.id,
    )
    original_search = routes.search_models

    def accepted_branch(*args, **kwargs):
        result = original_search(*args, **kwargs)
        assert result.reason == "UNCALIBRATED_SIMILARITY_ONLY"
        # Injection boundary is explicit: test conditional accepted visual branch only.
        return result.model_copy(
            update={
                "status": "KNOWN_MODEL_CANDIDATE",
                "calibrated": True,
                "reason": "SYNTHETIC_ACCEPTANCE_BRANCH_ONLY",
            }
        )

    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_encoder] = lambda: encoder
    app.dependency_overrides[get_ocr_engine] = lambda: SyntheticOCR()
    monkeypatch.setattr(routes, "search_models", accepted_branch)
    return assets, locations, maker, original_search


def get_json(response, status):
    assert response.status_code == status, response.text
    return response.json()


@pytest.mark.parametrize(
    "case",
    [
        "damaged_serial",
        "same_location",
        "eight_identical",
        "explicit_unknown",
        "location_conflict",
        "wrong_unit",
        "checked_match",
        "raw_ocr_false_positive",
        "uncalibrated",
    ],
)
def test_eight_ap_complete_observation_review(
    client, db, user, password, scenario, monkeypatch, case
):
    import app.recognition_routes as routes

    assets, locations, maker, original_search = scenario
    if case == "uncalibrated":
        monkeypatch.setattr(routes, "search_models", original_search)
    assert sign_in(client, password).status_code == 200
    headers = session_headers(client)
    before = [get_json(client.get(f"/api/v1/assets/{a.id}"), 200) for a in assets]
    job = get_json(
        client.post(
            "/api/v1/recognition/model-candidates",
            headers=headers,
            files={"file": ("synthetic.png", picture("red"), "image/png")},
        ),
        201,
    )
    assert len(job["result"]["candidates"]) == 3
    assert job["result"]["encoder"]["name"] == "synthetic-e2e-only"
    assert job["result"]["candidates"][0]["device_model_id"] == str(assets[0].device_model_id)
    assert client.get(job["content_url"]).status_code == 200
    payload = {
        "request_id": str(uuid.uuid4()),
        "device_job_id": job["id"],
        "notes": "Synthetic scenario " + case,
    }
    if case in {"damaged_serial", "checked_match", "raw_ocr_false_positive", "wrong_unit"}:
        payload["observed_location_id"] = str(locations[0].id)
    if case == "same_location":
        payload["observed_location_id"] = str(locations[4].id)
    if case == "location_conflict":
        payload["observed_location_id"] = str(locations[3].id)
        payload["correction"] = {"corrected_text": "SN: EVAL000003"}
    if case in {"checked_match", "wrong_unit", "raw_ocr_false_positive"}:
        payload["correction"] = {"corrected_text": "SN: EVAL000001"}
    if case == "explicit_unknown":
        payload["force_unknown"] = True
    if case == "raw_ocr_false_positive":
        label = get_json(
            client.post(
                "/api/v1/recognition/ocr",
                headers=headers,
                files={"file": ("label.png", picture("white"), "image/png")},
            ),
            201,
        )
        payload["label_job_id"] = label["id"]
    obs = get_json(
        client.post("/api/v1/recognition/observations", headers=headers, json=payload), 201
    )
    obs = get_json(client.get(f"/api/v1/recognition/observations/{obs['id']}"), 200)
    expected = {
        "damaged_serial": "PROBABLE_ASSET",
        "same_location": "AMBIGUOUS",
        "eight_identical": "AMBIGUOUS",
        "explicit_unknown": "UNKNOWN",
        "location_conflict": "AMBIGUOUS",
        "wrong_unit": "PROBABLE_ASSET",
        "checked_match": "PROBABLE_ASSET",
        "raw_ocr_false_positive": "AMBIGUOUS",
        "uncalibrated": "UNKNOWN",
    }[case]
    assert obs["evidence"]["fusion"]["status"] == expected
    assert obs["asset_id"] is None and obs["review"] is None
    if case == "eight_identical":
        assert len(obs["evidence"]["fusion"]["candidates"]) == 8
    if case == "same_location":
        assert len(obs["evidence"]["fusion"]["candidates"]) == 4
    if case == "damaged_serial":
        assert obs["evidence"]["fusion"]["candidates"][0]["asset_id"] == str(assets[0].id)
    if case == "uncalibrated":
        assert job["result"]["status"] == "UNCERTAIN" and not job["result"]["calibrated"]
    match = {
        "version": 1,
        "decision": "MATCH",
        "selected_asset_id": str(assets[0].id),
        "asset_version": assets[0].version,
        "manufacturer_id": str(maker.id),
        "checked_manual_indices": [0],
        "label_checked": True,
        "notes": "Synthetic check",
    }
    url = f"/api/v1/recognition/observations/{obs['id']}/review"
    if case == "location_conflict":
        match.update(selected_asset_id=str(assets[2].id), asset_version=assets[2].version)
    elif case == "wrong_unit":
        match.update(selected_asset_id=str(assets[1].id), asset_version=assets[1].version)
    if case not in {"checked_match", "raw_ocr_false_positive"}:
        response = client.post(url, headers=headers, json=match)
        assert response.status_code in {409, 422}, response.text
        unchanged = get_json(client.get(f"/api/v1/recognition/observations/{obs['id']}"), 200)
        assert unchanged == obs
        decision = "CONFLICT" if case in {"location_conflict", "wrong_unit"} else "MORE_PHOTOS"
        if case == "explicit_unknown":
            decision = "UNKNOWN"
        review = {"version": 1, "decision": decision, "notes": "Synthetic insufficient evidence"}
    else:
        if case == "raw_ocr_false_positive":
            false_match = {
                **match,
                "selected_asset_id": str(assets[2].id),
                "asset_version": assets[2].version,
            }
            assert client.post(url, headers=headers, json=false_match).status_code == 409
        review = match
    final = get_json(client.post(url, headers=headers, json=review), 200)
    assert final["evidence"] == obs["evidence"]
    assert final["review"]["reviewer_id"] == str(user.id)
    reviewed_at = datetime.fromisoformat(final["review"]["reviewed_at"])
    if db.bind.dialect.name == "postgresql":
        assert reviewed_at.tzinfo is not None
    else:
        assert reviewed_at.year >= 2026  # SQLite stores timezone-aware columns without offsets.
    if case in {"checked_match", "raw_ocr_false_positive"}:
        assert final["asset_id"] == str(assets[0].id)
        assert final["review"]["evidence"]["result_status"] == "VERIFIED_ASSET"
    else:
        assert final["asset_id"] is None
    if case == "raw_ocr_false_positive":
        assert final["evidence"]["ocr"]["raw_text"] == "SN: EVAL000003"
        assert final["evidence"]["ocr"]["corrected_text"] == "SN: EVAL000001"
        assert final["review"]["selected_asset_id"] != str(assets[2].id)
    assert [get_json(client.get(f"/api/v1/assets/{a.id}"), 200) for a in assets] == before
    audits = list(
        db.scalars(select(AuditEvent).where(AuditEvent.action == "recognition_observation_review"))
    )
    assert len(audits) == 1 and audits[0].actor_id == user.id

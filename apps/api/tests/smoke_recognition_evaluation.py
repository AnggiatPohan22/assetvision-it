"""Task3-06 real HTTP/proxy/PostGIS evaluation, generated fixtures, default NO_GO adapters."""

import json
import statistics
import time
import uuid

import httpx
from smoke_catalog import ROOT, create, expect, headers, image_bytes, login, run_id

from app.models import Role


def run() -> None:
    samples: dict[str, list[float]] = {}

    def request(client, method, path, code=200, **kwargs):
        start = time.perf_counter()
        response = expect(client.request(method, ROOT + path, **kwargs), code)
        elapsed = (time.perf_counter() - start) * 1000
        # Aggregate by operation only: no identifiers, photos, private paths or credentials.
        operation = (
            "upload"
            if path.endswith(("model-candidates", "/ocr"))
            else (
                "review"
                if path.endswith("/review")
                else "observation"
                if method == "POST"
                else "read"
            )
        )
        samples.setdefault(operation, []).append(elapsed)
        return response.json()

    with (
        httpx.Client(base_url="http://web-smoke:3000", timeout=30) as admin,
        httpx.Client(base_url="http://web-smoke:3000", timeout=30) as officer,
        httpx.Client(base_url="http://web-smoke:3000", timeout=30) as viewer,
    ):
        for client, role in [(admin, Role.ADMIN), (officer, Role.OFFICER), (viewer, Role.VIEWER)]:
            login(client, role)
            page = client.get("/recognition")
            assert page.status_code == 200 and "Observasi perangkat" in page.text
        category = create(
            admin, "device-categories", {"code": f"eval-{run_id}", "name": "Synthetic AP"}
        )
        maker = create(admin, "manufacturers", {"name": f"Synthetic E2E {run_id}"})
        model = create(
            admin,
            "device-models",
            {
                "category_id": category["id"],
                "manufacturer_id": maker["id"],
                "model_name": "Synthetic identical AP",
                "environment": "indoor",
            },
        )
        locations = [
            create(admin, "locations", {"code": f"eval-{n}-{run_id}", "name": name, "kind": "AREA"})
            for n, name in enumerate(("Lounge", "Lobby", "Villa 1", "Villa 10"))
        ]
        assets = []
        for n in range(8):
            asset = create(
                admin,
                "assets",
                {"asset_code": f"EVAL-AP-{n + 1:03}", "device_model_id": model["id"]},
            )
            create(
                admin,
                f"assets/{asset['id']}/identifiers",
                {
                    "asset_version": 1,
                    "identifier_type": "SERIAL_NUMBER",
                    "raw_value": f"EVAL{n + 1:06}",
                    "source": "MANUAL",
                    "verification_status": "VERIFIED",
                },
            )
            # Identifier mutation returns the new asset version inside its response.
            current = expect(admin.get(ROOT + f"/assets/{asset['id']}"), 200).json()
            create(
                admin,
                f"assets/{asset['id']}/initial-placement",
                {
                    "version": current["version"],
                    "location_id": locations[min(n, 3)]["id"],
                    "reason": "Synthetic approved placement",
                },
            )
            assets.append(expect(admin.get(ROOT + f"/assets/{asset['id']}"), 200).json())
        histories = [
            expect(admin.get(ROOT + f"/assets/{a['id']}/location"), 200).json() for a in assets
        ]
        h = headers(officer)
        job = request(
            officer,
            "POST",
            "/recognition/model-candidates",
            201,
            headers=h,
            files={"file": ("generated.png", image_bytes(), "image/png")},
        )
        assert (
            job["result"]["status"] == "UNKNOWN_MODEL" and job["result"]["reason"] == "EMPTY_INDEX"
        )
        label = request(
            officer,
            "POST",
            "/recognition/ocr",
            201,
            headers=h,
            files={"file": ("generated-label.png", image_bytes(), "image/png")},
        )
        assert not label["result"]["raw_text"]
        ah = headers(admin)
        outcomes = []
        for case in ["unknown", "location_conflict", "false_positive", "checked_match"]:
            target = assets[2] if case == "location_conflict" else assets[0]
            body = {
                "request_id": str(uuid.uuid4()),
                "device_job_id": job["id"],
                "label_job_id": label["id"],
                "notes": "Synthetic evaluation " + case,
                "observed_location_id": locations[3 if case == "location_conflict" else 0]["id"],
            }
            if case == "unknown":
                body["force_unknown"] = True
            else:
                body["correction"] = {
                    "corrected_text": "SN: EVAL000003"
                    if case == "location_conflict"
                    else "SN: EVAL000001"
                }
            obs = request(officer, "POST", "/recognition/observations", 201, headers=h, json=body)
            assert obs["asset_id"] is None
            assert obs["evidence"]["fusion"]["status"] == (
                "UNKNOWN" if case == "unknown" else "PROBABLE_ASSET"
            )
            url = f"/recognition/observations/{obs['id']}/review"
            if case in {"location_conflict", "false_positive", "checked_match"}:
                selected = assets[1] if case == "false_positive" else target
                match = {
                    "version": 1,
                    "decision": "MATCH",
                    "selected_asset_id": selected["id"],
                    "asset_version": selected["version"],
                    "manufacturer_id": maker["id"],
                    "checked_manual_indices": [0],
                    "label_checked": True,
                    "notes": "Synthetic label check",
                }
                expect(viewer.post(ROOT + url, headers=headers(viewer), json=match), 403)
                status = 200 if case == "checked_match" else 409
                result = request(admin, "POST", url, status, headers=ah, json=match)
                if status == 409:
                    pending = request(viewer, "GET", f"/recognition/observations/{obs['id']}")
                    assert pending == obs
            if case != "checked_match":
                decision = {
                    "unknown": "UNKNOWN",
                    "location_conflict": "CONFLICT",
                    "false_positive": "MORE_PHOTOS",
                }[case]
                result = request(
                    admin,
                    "POST",
                    url,
                    headers=ah,
                    json={"version": 1, "decision": decision, "notes": "Synthetic human review"},
                )
                assert result["asset_id"] is None
            else:
                assert result["asset_id"] == assets[0]["id"]
                assert result["review"]["evidence"]["result_status"] == "VERIFIED_ASSET"
            assert result["evidence"] == obs["evidence"]
            assert result["review"]["reviewer_id"] and result["review"]["reviewed_at"]
            assert (
                expect(viewer.get(job["content_url"]), 200).headers["content-type"] == "image/jpeg"
            )
            outcomes.append(case)
        for n, asset in enumerate(assets):
            assert expect(viewer.get(ROOT + f"/assets/{asset['id']}"), 200).json() == asset
            assert (
                expect(viewer.get(ROOT + f"/assets/{asset['id']}/location"), 200).json()
                == histories[n]
            )
        metric = request(admin, "GET", "/recognition/metrics")
        assert (
            metric["accuracy"] is None
            and metric["evaluation_status"] == "NO_GO_REAL_DATASET_REQUIRED"
        )
        assert metric["observations"] == metric["reviews"] == 4
        print(
            "PASS eight identical AP registry; four HTTP review scenarios; immutable master/history"
        )
        profile = {
            key: {
                "count": len(values),
                "p50_ms": statistics.median(values),
                "p95_ms": percentile(values, 0.95),
                "max_ms": max(values),
            }
            for key, values in samples.items()
        }
        print(
            "EVALUATION_JSON="
            + json.dumps(
                {
                    "schema_version": 1,
                    "synthetic": True,
                    "transport": "real HTTP Next proxy/FastAPI/PostGIS",
                    "visual": "default empty index",
                    "scenarios_passed": outcomes,
                    "physical_assets": 8,
                    "latency": profile,
                    "accuracy": None,
                    "production_go_no_go": "NO_GO_REAL_DATASET_REQUIRED",
                },
                sort_keys=True,
            )
        )


def percentile(values, quantile):
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


if __name__ == "__main__":
    run()

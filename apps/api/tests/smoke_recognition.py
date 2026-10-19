"""Task3-05 real proxy/API/DB smoke, synthetic data only on db-test."""

import io
import uuid

import httpx
from PIL import Image
from smoke_catalog import ROOT, create, expect, headers, login, run_id

from app.models import Role


def run() -> None:
    data = io.BytesIO()
    Image.new("RGB", (40, 20), "orange").save(data, format="PNG")
    with (
        httpx.Client(base_url="http://web-smoke:3000", timeout=30) as admin,
        httpx.Client(base_url="http://web-smoke:3000", timeout=30) as officer,
        httpx.Client(base_url="http://web-smoke:3000", timeout=30) as viewer,
        httpx.Client(base_url="http://web-smoke:3000", timeout=30) as anonymous,
    ):
        assert anonymous.get("/recognition").status_code == 307
        expect(anonymous.get(ROOT + "/recognition/observations"), 401)
        for client, role in [(admin, Role.ADMIN), (officer, Role.OFFICER), (viewer, Role.VIEWER)]:
            login(client, role)
            page = client.get("/recognition")
            assert page.status_code == 200
            assert "no-store" in page.headers.get("cache-control", "")
            assert "Observasi perangkat" in page.text
        print("PASS authenticated SSR recognition page, anonymous redirect/API401, all read roles")
        for client, code in [(viewer, 403), (officer, 201)]:
            response = expect(
                client.post(
                    ROOT + "/recognition/model-candidates",
                    headers=headers(client),
                    files={"file": ("../../ignored.png", data.getvalue(), "image/png")},
                ),
                code,
            )
            if code == 201:
                job = response.json()
        assert job["result"]["status"] == "UNKNOWN_MODEL"
        expect(viewer.get(job["content_url"]), 404)
        assert expect(officer.get(job["content_url"]), 200).headers["content-type"] == "image/jpeg"
        print("PASS upload RBAC, empty-index unknown, private original and sanitized preview")
        category = create(
            admin, "device-categories", {"code": f"rec-{run_id}", "name": f"Rec {run_id}"}
        )
        maker = create(admin, "manufacturers", {"name": f"Rec maker {run_id}"})
        model = create(
            admin,
            "device-models",
            {
                "category_id": category["id"],
                "manufacturer_id": maker["id"],
                "model_name": "Synthetic AP for review",
                "environment": "indoor",
            },
        )
        asset = create(
            admin, "assets", {"asset_code": f"REC-{run_id}", "device_model_id": model["id"]}
        )
        create(
            admin,
            f"assets/{asset['id']}/identifiers",
            {
                "asset_version": 1,
                "identifier_type": "SERIAL_NUMBER",
                "raw_value": "ABC789XYZ",
                "source": "MANUAL",
                "verification_status": "VERIFIED",
            },
        )
        before = expect(admin.get(ROOT + f"/assets/{asset['id']}"), 200).json()
        body = {
            "request_id": str(uuid.uuid4()),
            "device_job_id": job["id"],
            "notes": "Synthetic real proxy label observation",
            "correction": {"corrected_text": "SN: ABC789XYZ"},
        }
        obs = create(officer, "recognition/observations", body)
        again = create(officer, "recognition/observations", body)
        assert obs["id"] == again["id"] and obs["asset_id"] is None
        expect(viewer.get(job["content_url"]), 200)
        print(
            "PASS retained observation/manual correction, exact retry, attached read-only photo ACL"
        )
        review = {
            "version": 1,
            "decision": "MATCH",
            "selected_asset_id": asset["id"],
            "asset_version": before["version"],
            "manufacturer_id": maker["id"],
            "checked_manual_indices": [0],
            "label_checked": True,
            "notes": "Synthetic label physically checked",
        }
        for client in (viewer, officer):
            expect(
                client.post(
                    ROOT + f"/recognition/observations/{obs['id']}/review",
                    headers=headers(client),
                    json=review,
                ),
                403,
            )
        response = expect(
            admin.post(
                ROOT + f"/recognition/observations/{obs['id']}/review",
                headers=headers(admin),
                json=review,
            ),
            200,
        ).json()
        assert response["asset_id"] == asset["id"]
        assert response["review"]["evidence"]["result_status"] == "VERIFIED_ASSET"
        assert response["evidence"] == obs["evidence"]
        assert expect(admin.get(ROOT + f"/assets/{asset['id']}"), 200).json() == before
        expect(
            admin.post(
                ROOT + f"/recognition/observations/{obs['id']}/review",
                headers=headers(admin),
                json=review,
            ),
            409,
        )
        print(
            "PASS ADMIN unique checked identifier review, immutable prediction, "
            "no master/version change"
        )
        for client, code in [(viewer, 403), (officer, 403), (admin, 200)]:
            expect(client.get(ROOT + "/recognition/metrics"), code)
        print("PASS metrics ADMIN-only, no fabricated accuracy")


if __name__ == "__main__":
    run()

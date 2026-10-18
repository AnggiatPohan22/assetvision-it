"""Task 1B-04 SSR/role/history HTTP smoke using guarded synthetic test data only."""

import uuid

import httpx
from smoke_catalog import ROOT, create, expect, headers, login, run_id

from app.models import Role


def run() -> None:
    with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as admin:
        for page in ("/assets", "/assets/new", "/assets/import", f"/assets/{uuid.uuid4()}"):
            response = admin.get(page)
            assert response.status_code == 307 and response.headers["location"] == "/login"
        expect(admin.get(f"{ROOT}/assets/{uuid.uuid4()}/events"), 401)
        login(admin, Role.ADMIN)
        assert "Registry unit fisik" in admin.get("/dashboard").text
        assert "Aset fisik" in admin.get("/catalog/models").text
        page = admin.get("/assets")
        assert page.status_code == 200 and "Tambah aset" in page.text and "Impor CSV" in page.text
        assert "Unit fisik baru" in admin.get("/assets/new").text
        assert "Impor aset dari CSV" in admin.get("/assets/import").text
        category = create(
            admin, "device-categories", {"code": f"ui-{run_id}", "name": f"Synthetic {run_id}"}
        )
        maker = create(admin, "manufacturers", {"name": f"Synthetic UI Maker {run_id}"})
        model = create(
            admin,
            "device-models",
            {
                "category_id": category["id"],
                "manufacturer_id": maker["id"],
                "model_name": "Synthetic UI AP",
                "environment": "indoor",
            },
        )
        asset = create(
            admin, "assets", {"asset_code": f"UI-{run_id}", "device_model_id": model["id"]}
        )
        path = f"{ROOT}/assets/{asset['id']}"
        assert admin.get(f"/assets/{asset['id']}").status_code == 200
        events = expect(admin.get(path + "/events?page_size=1"), 200).json()
        assert events["total"] == 1
        assert events["items"][0]["after_json"]["asset"]["asset_code"] == asset["asset_code"]
        assert "password_hash" not in str(events)
        assert expect(admin.get(path), 200).json()["version"] == 1
        expect(admin.post(path + "/events", headers=headers(admin)), 405)
        print("PASS anonymous redirects, ADMIN SSR/navigation, detail and read-only history")
        for role in (Role.OFFICER, Role.VIEWER):
            with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as reader:
                login(reader, role)
                page = reader.get("/assets")
                assert page.status_code == 200 and "Tambah aset" not in page.text
                assert "Unduh CSV" not in page.text
                assert "Akses terbatas" in reader.get("/assets/new").text
                assert "Akses terbatas" in reader.get("/assets/import").text
                assert reader.get(f"/assets/{asset['id']}").status_code == 200
                assert expect(reader.get(path + "/events"), 200).json()["total"] == 1
                expect(
                    reader.patch(
                        path, headers=headers(reader), json={"version": 1, "notes": "denied"}
                    ),
                    403,
                )
        print("PASS OFFICER/VIEWER server page gates, history read and backend write denial")
        expect(admin.post(ROOT + "/auth/logout", headers=headers(admin)), 204)
        assert admin.get("/assets").status_code == 307
        print("PASS logout protection; development data untouched")


if __name__ == "__main__":
    run()

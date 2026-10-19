"""Sprint 2-05 real SSR/proxy role gates and optional synthetic browser fixture."""

import json
import os
from pathlib import Path

import httpx
from smoke_catalog import ROOT, create, expect, headers, login, password, run_id, users

from app.models import Role


def run() -> None:
    with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as admin:
        for path in ("/locations", "/movements"):
            response = admin.get(path)
            assert response.status_code == 307 and response.headers["location"] == "/login"
        login(admin, Role.ADMIN)
        for path, title in (("/locations", "Lokasi aset"), ("/movements", "Inbox perpindahan")):
            page = admin.get(path)
            assert page.status_code == 200 and title in page.text
        assert "Tambah lokasi" in admin.get("/locations").text
        assert 'href="/locations"' in admin.get("/assets").text
        assert 'href="/movements"' in admin.get("/dashboard").text
        print("PASS anonymous redirects, ADMIN location/inbox SSR and workspace navigation")

        site = create(admin, "locations", {"code": "uat-site", "name": "UAT Site", "kind": "SITE"})
        locations = {}
        for code, name, kind in (
            ("villa-1", "Villa 1", "BUILDING"),
            ("villa-10", "Villa 10", "BUILDING"),
            ("lounge", "Lounge", "AREA"),
            ("lobby", "Lobby", "ROOM"),
        ):
            locations[code] = create(
                admin,
                "locations",
                {"code": code, "name": name, "kind": kind, "parent_id": site["id"]},
            )
        category = create(
            admin, "device-categories", {"code": f"ui-{run_id}", "name": "Synthetic UAT AP"}
        )
        maker = create(admin, "manufacturers", {"name": f"Synthetic UAT maker {run_id}"})
        model = create(
            admin,
            "device-models",
            {
                "category_id": category["id"],
                "manufacturer_id": maker["id"],
                "model_name": "Synthetic UAT device",
                "environment": "indoor",
            },
        )
        asset = create(admin, "assets", {"asset_code": "AP-003", "device_model_id": model["id"]})
        path = ROOT + f"/assets/{asset['id']}"
        assert expect(admin.get(path + "/location-status"), 200).json()["status"] == "UNPLACED"
        assert expect(admin.get(path + "/timeline"), 200).json()["total"] == 1
        assert admin.get(f"/assets/{asset['id']}").status_code == 200
        print(
            "PASS guarded synthetic hierarchy/AP-003 fixture, "
            "unplaced and retained metadata history"
        )
        for role in (Role.OFFICER, Role.VIEWER):
            with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as reader:
                login(reader, role)
                page = reader.get("/locations")
                assert page.status_code == 200 and "Tambah lokasi" not in page.text
                assert "Akses terbatas" in reader.get("/movements").text
                assert 'href="/movements"' not in reader.get("/assets").text
                assert reader.get(f"/assets/{asset['id']}").status_code == 200
                expect(reader.get(path + "/timeline"), 200)
                expect(reader.get(ROOT + "/movements"), 403)
                expect(reader.post(ROOT + "/locations", headers=headers(reader), json={}), 403)
                expect(
                    reader.post(path + "/initial-placement", headers=headers(reader), json={}),
                    403,
                )
        print(
            "PASS OFFICER/VIEWER page gates, read-only hierarchy/history and backend write denial"
        )
        target = os.environ.get("UAT_FIXTURE_PATH")
        if target:
            # Random credentials for this tmpfs test DB only; never log or commit them.
            destination = Path(target)
            destination.write_text(
                json.dumps(
                    {
                        "asset_id": asset["id"],
                        "asset_code": asset["asset_code"],
                        "locations": {key: value["id"] for key, value in locations.items()},
                        "users": {role.value: users[role][1] for role in Role},
                        "password": password,
                    }
                )
            )
            destination.chmod(0o600)
        expect(admin.post(ROOT + "/auth/logout", headers=headers(admin)), 204)
        assert admin.get("/locations").status_code == 307
        assert admin.get("/movements").status_code == 307
        expect(admin.get(path + "/timeline"), 401)
        print("PASS logout revokes new pages and timeline; development data untouched")


if __name__ == "__main__":
    run()

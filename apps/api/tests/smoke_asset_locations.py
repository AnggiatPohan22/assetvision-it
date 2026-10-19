"""Task 2-02 real proxy/API/PG smoke; guarded synthetic database only."""

import uuid

import httpx
from smoke_catalog import ROOT, SessionLocal, create, expect, headers, login, run_id, users
from sqlalchemy import select

from app.asset_locations import AssetLocationEvent
from app.models import Role


def run() -> None:
    with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as admin:
        login(admin, Role.ADMIN)
        category = create(
            admin,
            "device-categories",
            {"code": f"placement-{run_id}", "name": f"Synthetic {run_id}"},
        )
        maker = create(admin, "manufacturers", {"name": f"Placement maker {run_id}"})
        model = create(
            admin,
            "device-models",
            {
                "category_id": category["id"],
                "manufacturer_id": maker["id"],
                "model_name": "Synthetic placement AP",
                "environment": "indoor",
            },
        )
        asset = create(admin, "assets", {"asset_code": "AP-003", "device_model_id": model["id"]})
        location = create(
            admin, "locations", {"code": f"villa-1-{run_id}", "name": "Villa 1", "kind": "BUILDING"}
        )
        path = ROOT + "/assets/" + asset["id"]
        body = {
            "version": 1,
            "location_id": location["id"],
            "reason": "Synthetic initial verification",
        }
        assert expect(admin.get(path + "/location"), 200).json()["current_location_id"] is None
        expect(admin.post(path + "/initial-placement", json=body), 403)
        placed = expect(
            admin.post(path + "/initial-placement", headers=headers(admin), json=body), 201
        ).json()
        assert placed["version"] == 2 and placed["current_location_id"] == location["id"]
        assert placed["location_verified_at"]
        expect(admin.post(path + "/initial-placement", headers=headers(admin), json=body), 409)
        expect(
            admin.post(
                path + "/initial-placement", headers=headers(admin), json={**body, "version": 2}
            ),
            409,
        )
        expect(
            admin.patch(
                path, headers=headers(admin), json={"version": 2, "current_location_id": None}
            ),
            422,
        )
        expect(
            admin.patch(path, headers=headers(admin), json={"version": 1, "notes": "stale"}), 409
        )
        with SessionLocal() as db:
            entry = db.scalar(
                select(AssetLocationEvent).where(
                    AssetLocationEvent.asset_id == uuid.UUID(asset["id"])
                )
            )
            assert (
                entry.event_type == "INITIAL_PLACEMENT" and entry.actor_id == users[Role.ADMIN][0]
            )
            assert entry.payload_json["from_location_id"] is None
            assert entry.payload_json["to_location_id"] == location["id"]
            assert entry.occurred_at and entry.recorded_at and entry.correlation_id
        print("PASS AP-003 initial placement, atomic event evidence, version and repeat conflicts")
        expect(
            admin.patch(
                ROOT + "/locations/" + location["id"],
                headers=headers(admin),
                json={"version": 1, "is_active": False},
            ),
            200,
        )
        for role in (Role.OFFICER, Role.VIEWER):
            with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as reader:
                login(reader, role)
                current = expect(reader.get(path + "/location"), 200).json()
                assert current["location"]["is_active"] is False
                expect(
                    reader.post(path + "/initial-placement", headers=headers(reader), json=body),
                    403,
                )
        expect(admin.post(ROOT + "/auth/logout", headers=headers(admin)), 204)
        expect(admin.get(path + "/location"), 401)
        print("PASS archived location lookup, role enforcement and session revocation")


if __name__ == "__main__":
    run()

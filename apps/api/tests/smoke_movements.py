"""Task 2-03 movement workflow over the real proxy/API and isolated PostgreSQL."""

import uuid

import httpx
from smoke_catalog import ROOT, SessionLocal, create, expect, headers, login, run_id, users
from sqlalchemy import select

from app.asset_locations import AssetLocationEvent
from app.models import Role
from app.movements import AssetMovement, MovementStatus


def run() -> None:
    with (
        httpx.Client(base_url="http://web-smoke:3000", timeout=30) as admin,
        httpx.Client(base_url="http://web-smoke:3000", timeout=30) as officer,
        httpx.Client(base_url="http://web-smoke:3000", timeout=30) as viewer,
    ):
        login(admin, Role.ADMIN)
        login(officer, Role.OFFICER)
        login(viewer, Role.VIEWER)
        category = create(
            admin,
            "device-categories",
            {"code": f"move-{run_id}", "name": f"Synthetic movement {run_id}"},
        )
        maker = create(admin, "manufacturers", {"name": f"Movement maker {run_id}"})
        model = create(
            admin,
            "device-models",
            {
                "category_id": category["id"],
                "manufacturer_id": maker["id"],
                "model_name": "Synthetic AP movement",
                "environment": "indoor",
            },
        )
        asset = create(admin, "assets", {"asset_code": "AP-003", "device_model_id": model["id"]})
        origin = create(
            admin, "locations", {"code": f"villa-1-{run_id}", "name": "Villa 1", "kind": "BUILDING"}
        )
        destination = create(
            admin,
            "locations",
            {"code": f"villa-10-{run_id}", "name": "Villa 10", "kind": "BUILDING"},
        )
        path = ROOT + "/assets/" + asset["id"]
        create(
            admin,
            f"assets/{asset['id']}/initial-placement",
            {"version": 1, "location_id": origin["id"], "reason": "Synthetic initial verification"},
        )
        body = {
            "asset_version": 2,
            "to_location_id": destination["id"],
            "reason": "Synthetic AP-003 move",
        }
        expect(officer.post(path + "/movements", json=body), 403)
        expect(viewer.post(path + "/movements", headers=headers(viewer), json=body), 403)
        pending = create(officer, f"assets/{asset['id']}/movements", body)
        stale = create(officer, f"assets/{asset['id']}/movements", body)
        assert pending["from_location_id"] == origin["id"] and pending["status"] == "PENDING"
        current = expect(admin.get(path + "/location"), 200).json()
        assert current["current_location_id"] == origin["id"] and current["version"] == 2
        assert expect(admin.get(ROOT + "/movements?status=PENDING"), 200).json()["total"] == 2
        review = {"version": 1, "reason": "Synthetic review"}
        for role_client in (officer, viewer):
            expect(role_client.get(ROOT + "/movements"), 403)
            expect(
                role_client.post(
                    ROOT + f"/movements/{pending['id']}/approve",
                    headers=headers(role_client),
                    json=review,
                ),
                403,
            )
            expect(
                role_client.post(
                    ROOT + f"/movements/{pending['id']}/reject",
                    headers=headers(role_client),
                    json=review,
                ),
                403,
            )
        approved = expect(
            admin.post(
                ROOT + f"/movements/{pending['id']}/approve", headers=headers(admin), json=review
            ),
            200,
        ).json()
        assert approved["status"] == "APPROVED" and approved["version"] == 2
        current = expect(officer.get(path + "/location"), 200).json()
        assert current["current_location_id"] == destination["id"] and current["version"] == 3
        assert current["location_verified_at"] == approved["effective_at"]
        expect(
            admin.post(
                ROOT + f"/movements/{pending['id']}/approve",
                headers=headers(admin),
                json={**review, "version": 2},
            ),
            409,
        )
        expect(
            admin.post(
                ROOT + f"/movements/{stale['id']}/approve", headers=headers(admin), json=review
            ),
            409,
        )
        rejected = expect(
            admin.post(
                ROOT + f"/movements/{stale['id']}/reject", headers=headers(admin), json=review
            ),
            200,
        ).json()
        assert rejected["status"] == "REJECTED"
        back = create(
            officer,
            f"assets/{asset['id']}/movements",
            {
                "asset_version": 3,
                "to_location_id": origin["id"],
                "reason": "Synthetic cancelled return",
            },
        )
        cancelled = expect(
            officer.post(
                ROOT + f"/movements/{back['id']}/cancel", headers=headers(officer), json=review
            ),
            200,
        ).json()
        assert cancelled["status"] == "CANCELLED"
        assert expect(viewer.get(path + "/location"), 200).json() == current
        expect(
            admin.patch(
                path,
                headers=headers(admin),
                json={"version": 3, "current_location_id": origin["id"]},
            ),
            422,
        )
        print("PASS OFFICER request keeps Villa 1; ADMIN moves AP-003 to Villa 10; conflicts 409")
        print("PASS ADMIN review/inbox, authenticated history and reject/cancel preserve location")
        own = create(
            admin,
            f"assets/{asset['id']}/movements",
            {
                "asset_version": 3,
                "to_location_id": origin["id"],
                "reason": "Synthetic self-approval pilot",
            },
        )
        expect(
            admin.post(
                ROOT + f"/movements/{own['id']}/approve", headers=headers(admin), json=review
            ),
            200,
        )
        for loc in (origin, destination):
            expect(
                admin.patch(
                    ROOT + "/locations/" + loc["id"],
                    headers=headers(admin),
                    json={"version": 1, "is_active": False},
                ),
                200,
            )
        history = expect(viewer.get(path + "/movements"), 200).json()
        assert history["total"] == 4
        with SessionLocal() as db:
            events = list(
                db.scalars(
                    select(AssetLocationEvent).where(
                        AssetLocationEvent.asset_id == uuid.UUID(asset["id"])
                    )
                )
            )
            approvals = [e for e in events if e.event_type == "MOVEMENT_APPROVED"]
            assert len(approvals) == 2
            first = next(e for e in approvals if e.payload_json["movement_id"] == pending["id"])
            assert first.actor_id == users[Role.ADMIN][0]
            assert first.payload_json["requested_by"] == str(users[Role.OFFICER][0])
            assert first.payload_json["from_location_id"] == origin["id"]
            assert first.payload_json["to_location_id"] == destination["id"]
            assert first.payload_json["self_approval"] is False
            assert any(e.payload_json["self_approval"] is True for e in approvals)
            assert all(e.recorded_at and e.occurred_at and e.correlation_id for e in events)
            assert len({e.correlation_id for e in events}) == len(events) == 9
            assert db.get(AssetMovement, uuid.UUID(back["id"])).status == MovementStatus.CANCELLED
        expect(admin.post(ROOT + "/auth/logout", headers=headers(admin)), 204)
        expect(admin.get(path + "/movements"), 401)
        print("PASS actor/time/event evidence, pilot self-approval, archive retention and logout")


if __name__ == "__main__":
    run()

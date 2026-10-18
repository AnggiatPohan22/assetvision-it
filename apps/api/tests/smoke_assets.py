"""Real HTTP asset smoke. Reuses guarded synthetic-user helpers; test DB only."""

import uuid

import httpx
from smoke_catalog import (
    ROOT,
    SessionLocal,
    create,
    expect,
    headers,
    login,
    run_id,
    users,
)
from sqlalchemy import select

from app.assets import AssetChangeEvent
from app.models import Role


def run() -> None:
    with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as admin:
        expect(admin.get(ROOT + "/assets"), 401)
        login(admin, Role.ADMIN)
        category = create(
            admin,
            "device-categories",
            {"code": f"asset-{run_id}", "name": f"Synthetic AP {run_id}"},
        )
        maker = create(admin, "manufacturers", {"name": f"Synthetic maker {run_id}"})
        model = create(
            admin,
            "device-models",
            {
                "category_id": category["id"],
                "manufacturer_id": maker["id"],
                "model_name": "Synthetic asset smoke",
                "environment": "indoor",
            },
        )
        asset = create(
            admin, "assets", {"asset_code": f"TEST-{run_id}-A", "device_model_id": model["id"]}
        )
        other = create(
            admin, "assets", {"asset_code": f"TEST-{run_id}-B", "device_model_id": model["id"]}
        )
        path = ROOT + "/assets/" + asset["id"]
        assert expect(admin.get(path), 200).json()["asset_code"] == asset["asset_code"]
        assert expect(admin.get(path + "/identifiers"), 200).json() == []
        expect(admin.patch(path, json={"version": 1, "notes": "denied"}), 403)
        expect(
            admin.patch(
                path,
                headers={**headers(admin), "Origin": "https://evil.invalid"},
                json={"version": 1, "notes": "denied"},
            ),
            403,
        )
        expect(
            admin.patch(path, headers=headers(admin), json={"version": 1, "asset_code": "CHANGED"}),
            422,
        )
        expect(
            admin.patch(
                path, headers=headers(admin), json={"version": 1, "notes": "Synthetic smoke"}
            ),
            200,
        )
        expect(
            admin.patch(path, headers=headers(admin), json={"version": 1, "notes": "stale"}), 409
        )
        claim = create(
            admin,
            f"assets/{asset['id']}/identifiers",
            {
                "asset_version": 2,
                "identifier_type": "MAC_LAN",
                "raw_value": "aabb.ccdd.eeff",
                "source": "MANUAL",
            },
        )
        assert (
            claim["asset_version"] == 3
            and claim["identifier"]["normalized_value"] == "AA:BB:CC:DD:EE:FF"
        )
        collided = create(
            admin,
            f"assets/{other['id']}/identifiers",
            {
                "asset_version": 1,
                "identifier_type": "MAC_LAN",
                "raw_value": "AA-BB-CC-DD-EE-FF",
                "source": "MANUAL",
            },
        )
        assert asset["id"] in collided["identifier"]["collision_asset_ids"]
        found = expect(
            admin.get(ROOT + "/assets", params={"search": "aabbccddeeff", "model_id": model["id"]}),
            200,
        ).json()
        assert found["total"] == 2
        detail = path + "/identifiers/" + claim["identifier"]["id"]
        expect(
            admin.patch(
                detail,
                headers=headers(admin),
                json={"version": 1, "asset_version": 3, "verification_status": "VERIFIED"},
            ),
            200,
        )
        removed = expect(
            admin.delete(detail, headers=headers(admin), params={"version": 2, "asset_version": 4}),
            200,
        ).json()
        assert removed["asset_version"] == 5 and removed["identifier"]["deleted_at"]
        assert expect(admin.get(path + "/identifiers"), 200).json() == []
        archived = expect(
            admin.post(path + "/archive", headers=headers(admin), json={"version": 5}), 200
        ).json()
        assert archived["version"] == 6 and archived["lifecycle_status"] == "ARCHIVED"
        expect(admin.delete(path, headers=headers(admin)), 405)
        print(
            "PASS asset CRUD, absent SN, immutable code, CSRF, stale version, "
            "search/collision, identifier soft-delete"
        )
        for role in (Role.OFFICER, Role.VIEWER):
            with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as reader:
                login(reader, role)
                expect(reader.get(path), 200)
                expect(reader.get(path + "/identifiers"), 200)
                expect(
                    reader.patch(
                        path, headers=headers(reader), json={"version": 6, "notes": "denied"}
                    ),
                    403,
                )
                expect(
                    reader.post(path + "/archive", headers=headers(reader), json={"version": 6}),
                    403,
                )
        with SessionLocal() as db:
            events = list(
                db.scalars(
                    select(AssetChangeEvent).where(
                        AssetChangeEvent.asset_id == uuid.UUID(asset["id"])
                    )
                )
            )
            assert len(events) == 6
            assert {e.event_type for e in events} == {
                "CREATE",
                "UPDATE",
                "ARCHIVE",
                "IDENTIFIER_ADD",
                "IDENTIFIER_UPDATE",
                "IDENTIFIER_REMOVE",
            }
            assert all(
                e.actor_id == users[Role.ADMIN][0] and e.recorded_at and e.after_json
                for e in events
            )
        print(
            "PASS OFFICER/VIEWER read-only and persisted snapshots for all six event types"
        )
        expect(admin.post(ROOT + "/auth/logout", headers=headers(admin)), 204)
        expect(admin.get(path), 401)
        print("PASS logout revokes asset access; all writes confined to synthetic test DB")


if __name__ == "__main__":
    run()

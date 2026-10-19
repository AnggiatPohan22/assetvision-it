"""Real proxy/API/PostgreSQL timeline and observation acceptance; test DB only."""

import uuid

import httpx
from smoke_catalog import ROOT, SessionLocal, create, expect, headers, login, run_id, users
from sqlalchemy import select

from app.asset_locations import AssetLocationEvent
from app.assets import AssetUnit
from app.models import AuditEvent, Role
from app.observations import LocationObservation


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
            {"code": f"obs-{run_id}", "name": f"Synthetic observations {run_id}"},
        )
        maker = create(admin, "manufacturers", {"name": f"Observation maker {run_id}"})
        model = create(
            admin,
            "device-models",
            {
                "category_id": category["id"],
                "manufacturer_id": maker["id"],
                "model_name": "Synthetic observed AP",
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
        movement = create(
            officer,
            f"assets/{asset['id']}/movements",
            {
                "asset_version": 2,
                "to_location_id": destination["id"],
                "reason": "Synthetic movement",
            },
        )
        expect(
            admin.post(
                ROOT + f"/movements/{movement['id']}/approve",
                headers=headers(admin),
                json={"version": 1, "reason": "Synthetic approve"},
            ),
            200,
        )
        official = expect(admin.get(path), 200).json()
        body = {
            "asset_id": asset["id"],
            "asset_version": 3,
            "observed_location_id": origin["id"],
            "evidence_note": "Synthetic AP-003 seen in Villa 1",
        }
        expect(officer.post(ROOT + "/location-observations", json=body), 403)
        expect(
            viewer.post(ROOT + "/location-observations", headers=headers(viewer), json=body), 403
        )
        observation = create(officer, "location-observations", body)
        assert observation["comparison_status"] == "LOCATION_CONFLICT"
        assert observation["official_location_id_at_recording"] == destination["id"]
        conflict = expect(viewer.get(path + "/location-status"), 200).json()
        assert conflict["status"] == "LOCATION_CONFLICT" and conflict["location_conflict"] is True
        assert (
            conflict["current_location_id"] == destination["id"] and conflict["asset_version"] == 3
        )
        assert expect(officer.get(path), 200).json() == official
        print(
            "PASS AP-003 observed in Villa 1 after approved Villa 10 move: "
            "conflict, no auto-revert/version change"
        )
        review_body = {
            "version": 1,
            "review_status": "ACKNOWLEDGED",
            "reason": "Synthetic acknowledgement",
        }
        for reader in (officer, viewer):
            expect(reader.get(ROOT + "/location-observations"), 403)
            expect(
                reader.post(
                    ROOT + f"/location-observations/{observation['id']}/review",
                    headers=headers(reader),
                    json=review_body,
                ),
                403,
            )
        acknowledged = expect(
            admin.post(
                ROOT + f"/location-observations/{observation['id']}/review",
                headers=headers(admin),
                json=review_body,
            ),
            200,
        ).json()
        assert acknowledged["version"] == 2 and acknowledged["review_status"] == "ACKNOWLEDGED"
        assert (
            expect(viewer.get(path + "/location-status"), 200).json()["location_conflict"] is True
        )
        expect(
            admin.post(
                ROOT + f"/location-observations/{observation['id']}/review",
                headers=headers(admin),
                json={**review_body, "version": 2},
            ),
            409,
        )
        corrected = create(
            officer,
            "location-observations",
            {
                **body,
                "observed_location_id": destination["id"],
                "evidence_note": "Synthetic newer matching observation",
            },
        )
        assert corrected["comparison_status"] == "MATCH"
        assert expect(viewer.get(path + "/location-status"), 200).json()["status"] == "MATCH"
        unknown = create(
            officer,
            "location-observations",
            {
                "observed_location_id": origin["id"],
                "evidence_note": "Synthetic unknown device; no claimed identity",
            },
        )
        assert unknown["comparison_status"] == "UNLINKED" and unknown["asset_id"] is None
        expect(
            admin.post(
                ROOT + f"/location-observations/{unknown['id']}/review",
                headers=headers(admin),
                json={
                    "version": 1,
                    "review_status": "DISMISSED",
                    "reason": "Synthetic duplicate field evidence",
                },
            ),
            200,
        )
        assert (
            expect(admin.get(ROOT + "/location-observations?review_status=PENDING"), 200).json()[
                "total"
            ]
            == 1
        )
        history = expect(viewer.get(path + "/timeline"), 200).json()
        assert history["total"] == 7
        kinds = {x["event_type"] for x in history["items"]}
        assert {
            "CREATE",
            "INITIAL_PLACEMENT",
            "MOVEMENT_REQUESTED",
            "MOVEMENT_APPROVED",
            "LOCATION_OBSERVED",
            "LOCATION_OBSERVATION_REVIEWED",
        } <= kinds
        assert expect(viewer.get(path + "/timeline?source=METADATA"), 200).json()["total"] == 1
        assert expect(officer.get(path + "/location-observations"), 200).json()["total"] == 2
        expect(
            admin.patch(
                ROOT + f"/location-observations/{observation['id']}",
                headers=headers(admin),
                json={"evidence_note": "Denied"},
            ),
            405,
        )
        expect(admin.delete(path + "/timeline", headers=headers(admin)), 405)
        print(
            "PASS authenticated immutable timeline, ADMIN-only review, "
            "explicit new evidence and unlinked observations"
        )
        for location in (origin, destination):
            expect(
                admin.patch(
                    ROOT + "/locations/" + location["id"],
                    headers=headers(admin),
                    json={"version": 1, "is_active": False, "name": "Archived synthetic location"},
                ),
                200,
            )
        assert expect(viewer.get(path + "/timeline"), 200).json() == history
        assert expect(admin.get(path), 200).json() == official
        with SessionLocal() as db:
            record = db.get(LocationObservation, uuid.UUID(observation["id"]))
            assert record.observed_by == users[Role.OFFICER][0]
            assert record.reviewed_by == users[Role.ADMIN][0]
            assert record.snapshot_json["observed_location"]["name"] == "Villa 1"
            assert record.snapshot_json["official_location"]["name"] == "Villa 10"
            unit = db.get(AssetUnit, uuid.UUID(asset["id"]))
            assert unit.version == 3 and str(unit.current_location_id) == destination["id"]
            events = list(
                db.scalars(select(AssetLocationEvent).where(AssetLocationEvent.asset_id == unit.id))
            )
            assert len(events) == 6 and len({x.correlation_id for x in events}) == 6
            audit = db.scalar(
                select(AuditEvent).where(AuditEvent.action == "location_observation_review")
            )
            assert audit.actor_id == users[Role.ADMIN][0]
        expect(admin.post(ROOT + "/auth/logout", headers=headers(admin)), 204)
        expect(admin.get(path + "/timeline"), 401)
        expect(admin.get(path + "/location-status"), 401)
        print(
            "PASS persisted actor/time/snapshot/event evidence, archive retention, "
            "unchanged master and logout"
        )


if __name__ == "__main__":
    run()

"""CSV through real Next proxy/API/PostgreSQL; synthetic data and guarded test DB only."""

import csv
import io
import uuid

import httpx
from smoke_catalog import ROOT, SessionLocal, create, expect, headers, login, run_id
from sqlalchemy import func, select

from app.asset_imports import AssetImportBatch
from app.assets import AssetChangeEvent, AssetUnit
from app.models import Role


def run() -> None:
    with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as admin:
        expect(admin.get(ROOT + "/assets/export.csv"), 401)
        login(admin, Role.ADMIN)
        category = create(
            admin, "device-categories", {"code": f"csv-{run_id}", "name": f"CSV {run_id}"}
        )
        maker = create(admin, "manufacturers", {"name": f"CSV manufacturer {run_id}"})
        model = create(
            admin,
            "device-models",
            {
                "category_id": category["id"],
                "manufacturer_id": maker["id"],
                "model_name": "Synthetic CSV AP",
                "environment": "indoor",
            },
        )
        source = io.StringIO(newline="")
        writer = csv.writer(source)
        writer.writerow(
            [
                "asset_code",
                "manufacturer",
                "model",
                "serial_number",
                "mac_address",
                "notes",
                "location_hint",
            ]
        )
        writer.writerow(
            [
                f"CSV-{run_id}-1",
                maker["name"],
                model["model_name"],
                "",
                "aabb.ccdd.eeff",
                "=1+1",
                "Staging only",
            ]
        )
        writer.writerow(
            [
                f"CSV-{run_id}-2",
                maker["name"],
                model["model_name"],
                "SYNTHETIC-123",
                "",
                "Quoted, note",
                "",
            ]
        )
        payload = {"csv_text": source.getvalue()}
        prefix = ROOT + "/assets/imports/"
        report = expect(
            admin.post(prefix + "preview", headers=headers(admin), json=payload), 200
        ).json()
        assert report["valid_rows"] == 2
        assert (
            expect(admin.get(ROOT + "/assets", params={"model_id": model["id"]}), 200).json()[
                "total"
            ]
            == 0
        )
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(AssetImportBatch)) == 0
        request = {**payload, "idempotency_key": str(uuid.uuid4())}
        result = expect(
            admin.post(prefix + "commit", headers=headers(admin), json=request), 200
        ).json()
        assert result["created_count"] == 2 and result["failed_count"] == 0
        assert result["rows"][0]["location_hint"] == "Staging only"
        assert (
            expect(admin.post(prefix + "commit", headers=headers(admin), json=request), 200).json()
            == result
        )
        expect(
            admin.post(
                prefix + "commit",
                headers=headers(admin),
                json={**request, "csv_text": source.getvalue() + "\n"},
            ),
            409,
        )
        expect(
            admin.post(
                prefix + "commit",
                headers=headers(admin),
                json={**request, "idempotency_key": str(uuid.uuid4())},
            ),
            409,
        )
        exported = expect(
            admin.get(ROOT + "/assets/export.csv", params={"model_id": model["id"]}), 200
        )
        assert "attachment" in exported.headers["content-disposition"]
        rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
        assert len(rows) == 2 and rows[0]["notes"] == "'=1+1" and rows[0]["location_hint"] == ""
        print(
            "PASS CSV preview read-only, create without SN, commit, "
            "persisted replay, key conflict, safe export"
        )
        for role in (Role.OFFICER, Role.VIEWER):
            with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as reader:
                login(reader, role)
                expect(reader.post(prefix + "preview", headers=headers(reader), json=payload), 403)
                expect(reader.post(prefix + "commit", headers=headers(reader), json=request), 403)
                expect(reader.get(ROOT + "/assets/export.csv"), 403)
        expect(admin.post(prefix + "preview", json=payload), 403)
        with SessionLocal() as db:
            receipt = db.get(AssetImportBatch, uuid.UUID(request["idempotency_key"]))
            assert receipt.result_json == result
            ids = [uuid.UUID(r["asset_id"]) for r in result["rows"]]
            assert (
                db.scalar(select(func.count()).select_from(AssetUnit).where(AssetUnit.id.in_(ids)))
                == 2
            )
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AssetChangeEvent)
                    .where(AssetChangeEvent.asset_id.in_(ids))
                )
                == 4
            )
        print("PASS ADMIN-only CSV, CSRF, receipt/audit persistence, no duplicate assets or events")


if __name__ == "__main__":
    run()

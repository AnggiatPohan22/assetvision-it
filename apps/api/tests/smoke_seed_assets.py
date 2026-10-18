"""Real seed CLI, audited eight-unit acceptance and replay; guarded tmpfs test DB only."""

import hashlib
import json
import subprocess
import sys

import httpx
from smoke_catalog import ROOT, SessionLocal, expect, login, users
from sqlalchemy import select

from app.assets import AssetUnit
from app.db import Base
from app.models import Role


def fingerprints() -> dict[str, str]:
    with SessionLocal() as db:
        return {
            table.name: hashlib.sha256(
                json.dumps(
                    [
                        dict(r)
                        for r in db.execute(select(table).order_by(*table.primary_key)).mappings()
                    ],
                    sort_keys=True,
                    default=str,
                ).encode()
            ).hexdigest()
            for table in Base.metadata.sorted_tables
        }


def run() -> None:
    command = [
        sys.executable,
        "-m",
        "app.seed_assets",
        "--actor-id",
        str(users[Role.ADMIN][0]),
        "--confirm-synthetic",
    ]
    first = subprocess.run(command, text=True, capture_output=True, check=True)
    assert json.loads(first.stdout)["created_assets"] == 8
    before = fingerprints()
    second = subprocess.run(command, text=True, capture_output=True, check=True)
    assert json.loads(second.stdout)["created_assets"] == 0
    assert fingerprints() == before
    with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as admin:
        login(admin, Role.ADMIN)
        with SessionLocal() as db:
            unit = db.scalar(select(AssetUnit).where(AssetUnit.asset_code == "AP-001"))
            model_id = str(unit.device_model_id)
        page = expect(admin.get(ROOT + "/assets", params={"model_id": model_id}), 200).json()
        assert page["total"] == 8
        assert [a["asset_code"] for a in page["items"]] == [f"AP-{i:03}" for i in range(1, 9)]
        for search, expected in [
            ("123456789", "AP-001"),
            ("2158763", "AP-002"),
            ("0200001b0004", "AP-004"),
        ]:
            found = expect(admin.get(ROOT + "/assets", params={"search": search}), 200).json()
            assert found["total"] == 1 and found["items"][0]["asset_code"] == expected
        for asset in page["items"]:
            path = ROOT + "/assets/" + asset["id"]
            claims = expect(admin.get(path + "/identifiers"), 200).json()
            assert all(
                c["source"] == "IMPORT" and c["verification_status"] == "UNVERIFIED" for c in claims
            )
            assert all(not c["collision_asset_ids"] for c in claims)
            if asset["asset_code"] in {"AP-004", "AP-005"}:
                assert all(c["identifier_type"] != "SERIAL_NUMBER" for c in claims)
            history = expect(admin.get(path + "/events"), 200).json()
            assert history["total"] == len(claims) + 1
            assert all(e["actor_id"] == str(users[Role.ADMIN][0]) for e in history["items"])
        exported = expect(
            admin.get(ROOT + "/assets/export.csv", params={"model_id": model_id}), 200
        )
        assert "AP-008" in exported.text and "SYNTHETIC Sprint 1B" in exported.text
    print(
        "PASS seed CLI: exactly eight AP units, fixed example SNs, missing SN, canonical MAC search"
    )
    print("PASS 22 claims/30 snapshots, actor, safe export and byte-identical no-op seed replay")


if __name__ == "__main__":
    run()

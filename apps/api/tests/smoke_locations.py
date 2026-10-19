"""Location-only HTTP/proxy smoke on guarded db-test, never development data."""

import httpx
from smoke_catalog import ROOT, create, expect, headers, login, run_id

from app.models import Role


def run() -> None:
    with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as admin:
        expect(admin.get(ROOT + "/locations"), 401)
        expect(admin.get(ROOT + "/locations/tree"), 401)
        login(admin, Role.ADMIN)
        site = create(
            admin,
            "locations",
            {
                "code": f"synthetic-{run_id}",
                "name": "Synthetic Site",
                "kind": "SITE",
            },
        )
        children = []
        for code, name, kind in (
            ("lounge", "Lounge", "ROOM"),
            ("lobby", "Lobby", "ROOM"),
            ("villa-1", "Villa 1", "BUILDING"),
            ("villa-10", "Villa 10", "BUILDING"),
        ):
            children.append(
                create(
                    admin,
                    "locations",
                    {
                        "code": code,
                        "name": name,
                        "kind": kind,
                        "parent_id": site["id"],
                    },
                )
            )
        items = expect(admin.get(ROOT + f"/locations?parent_id={site['id']}"), 200).json()
        assert items["total"] == 4
        assert {x["name"] for x in items["items"]} == {"Lounge", "Lobby", "Villa 1", "Villa 10"}
        path = ROOT + "/locations/" + site["id"]
        expect(
            admin.patch(
                path, headers=headers(admin), json={"version": 1, "parent_id": children[0]["id"]}
            ),
            409,
        )
        expect(
            admin.patch(path, headers=headers(admin), json={"version": 1, "is_active": False}), 200
        )
        expect(admin.patch(path, headers=headers(admin), json={"version": 1, "name": "Stale"}), 409)
        tree = expect(admin.get(ROOT + "/locations/tree"), 200).json()
        assert any(x["id"] == site["id"] and not x["is_active"] for x in tree["items"])
        expect(admin.delete(path, headers=headers(admin)), 405)
        print(
            "PASS real proxy hierarchy, four example locations, "
            "cycle/version conflict and archive retention"
        )
        for role in (Role.OFFICER, Role.VIEWER):
            with httpx.Client(base_url="http://web-smoke:3000", timeout=30) as reader:
                login(reader, role)
                expect(reader.get(ROOT + "/locations/tree"), 200)
                expect(reader.get(path), 200)
                expect(
                    reader.patch(
                        path, headers=headers(reader), json={"version": 2, "name": "Denied"}
                    ),
                    403,
                )
                expect(
                    reader.post(
                        ROOT + "/locations",
                        headers=headers(reader),
                        json={"code": "denied", "name": "Denied", "kind": "SITE"},
                    ),
                    403,
                )
        expect(admin.post(ROOT + "/auth/logout", headers=headers(admin)), 204)
        expect(admin.get(path), 401)
        print("PASS authenticated role reads, ADMIN-only writes and revoked-session denial")


if __name__ == "__main__":
    run()

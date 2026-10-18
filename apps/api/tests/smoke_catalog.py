"""Repeatable HTTP end-to-end catalog smoke: real Next proxy/API/PostgreSQL/private storage.

Only test users are inserted directly; every catalog mutation goes through HTTP.
No existing records are deleted/reset. Run with infra/smoke-catalog.sh, not pytest.
"""

import hashlib
import io
import os
import secrets
import sys
import uuid
from collections import Counter

import httpx
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

test_url = make_url(os.environ["TEST_DATABASE_URL"])
if (test_url.get_backend_name(), test_url.host, test_url.database, test_url.username) != (
    "postgresql",
    "db-test",
    "assetvision_test",
    "test_runner",
):
    raise SystemExit("Catalog smoke requires db-test/assetvision_test as test_runner")
os.environ["DATABASE_URL"] = test_url.set(
    password=os.environ["POSTGRES_PASSWORD"]
).render_as_string(hide_password=False)
sys.path.insert(0, os.getcwd())
from app.db import SessionLocal  # noqa: E402
from app.models import AuditEvent, DeviceReferenceImage, Role, StorageCleanupJob, User  # noqa: E402
from app.security import hash_password  # noqa: E402

ROOT = "/api/v1"
ORIGIN = "http://localhost:3002"
run_id = uuid.uuid4().hex[:12]
password = secrets.token_urlsafe(24)
users = {}
with SessionLocal.begin() as db:
    for role in Role:
        user = User(
                email=f"catalog-{run_id}-{role.lower()}@example.com",
            name=f"Smoke {role}",
            role=role,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()
        users[role] = (user.id, user.email)


def expect(response: httpx.Response, status: int) -> httpx.Response:
    # Never print response bodies, login payloads, cookies, or credentials on failure.
    assert response.status_code == status, (
        f"{response.request.method} {response.request.url.path}: "
        f"{response.status_code}, expected {status}"
    )
    assert response.headers.get("cache-control") == "no-store"
    return response


def headers(client: httpx.Client) -> dict[str, str]:
    token = expect(client.get(ROOT + "/auth/session"), 200).json()["csrf_token"]
    return {"Origin": ORIGIN, "X-CSRF-Token": token}


def login(client: httpx.Client, role: Role) -> None:
    csrf = expect(client.get(ROOT + "/auth/csrf"), 200).json()["csrf_token"]
    response = expect(
        client.post(
            ROOT + "/auth/login",
            json={"email": users[role][1], "password": password},
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
        ),
        200,
    )
    assert len(response.headers.get_list("set-cookie")) == 2
    assert all(
        "HttpOnly" in cookie and "SameSite=lax" in cookie
        for cookie in response.headers.get_list("set-cookie")
    )
    assert response.json()["role"] == role.value


def create(client: httpx.Client, resource: str, data: dict) -> dict:
    return expect(client.post(f"{ROOT}/{resource}", json=data, headers=headers(client)), 201).json()


def image_bytes() -> bytes:
    target = io.BytesIO()
    Image.new("RGB", (32, 24), "orange").save(target, format="PNG")
    return target.getvalue()


def run() -> None:
    with httpx.Client(
        base_url="http://web-smoke:3000", timeout=30, follow_redirects=False
    ) as admin:
        for page in ("/catalog/models", "/catalog/models/new", "/catalog/settings"):
            response = admin.get(page)
            assert response.status_code == 307 and response.headers["location"] == "/login"
        expect(admin.get(ROOT + "/device-models"), 401)
        expect(admin.get(ROOT + "/ready"), 200)
        login(admin, Role.ADMIN)
        assert admin.get("/catalog/models").status_code == 200
        assert "Tambah model" in admin.get("/catalog/models/new").text
        assert "Kategori &amp; produsen" in admin.get("/catalog/settings").text
        print("PASS anonymous redirects, login, cookie forwarding, authenticated SSR")

        category = create(
            admin,
            "device-categories",
            {"code": f"smoke-{run_id}", "name": f"Access Point {run_id}"},
        )
        maker = create(admin, "manufacturers", {"name": f"Ruijie {run_id}"})
        other = create(admin, "manufacturers", {"name": f"Other {run_id}"})
        data = {
            "model_name": "Ruijie AP680-L",
            "manufacturer_id": maker["id"],
            "category_id": category["id"],
            "environment": "outdoor",
            "aliases": [f"synthetic-{run_id}", "Outdoor AP"],
            "specs": {"poe": True, "ports": 2},
        }
        model = create(admin, "device-models", data)
        path = f"{ROOT}/device-models/{model['id']}"
        expect(
            admin.post(
                ROOT + "/device-models",
                json=data | {"model_name": " ruijie   ap680-l "},
                headers=headers(admin),
            ),
            409,
        )
        create(admin, "device-models", data | {"manufacturer_id": other["id"]})
        for number in range(3):
            create(admin, "device-models", data | {"model_name": f"Similar AP {number}"})
        expect(
            admin.post(
                ROOT + "/device-models",
                json=data | {"specs": {"invalid": {"nested": 1}}},
                headers=headers(admin),
            ),
            422,
        )
        expect(admin.patch(path, json={"version": 1, "description": "CSRF denied"}), 403)
        changed = expect(
            admin.patch(
                path, json={"version": 1, "description": "Smoke approved"}, headers=headers(admin)
            ),
            200,
        ).json()
        expect(
            admin.patch(
                path, json={"version": 1, "description": "Stale draft"}, headers=headers(admin)
            ),
            409,
        )
        assert (
            changed["version"] == 2
            and expect(admin.get(path), 200).json()["description"] == "Smoke approved"
        )
        query = {
            "category_id": category["id"],
            "search": f"synthetic-{run_id}",
            "is_active": "true",
            "page_size": 2,
        }
        pages = [
            expect(admin.get(ROOT + "/device-models", params=query | {"page": n}), 200).json()
            for n in (1, 2, 3)
        ]
        assert all(p["total"] == 5 and p["total_pages"] == 3 for p in pages)
        assert len({item["id"] for page in pages for item in page["items"]}) == 5
        assert (
            expect(admin.get(ROOT + "/device-models", params=query | {"page": 99}), 200).json()[
                "items"
            ]
            == []
        )
        empty = expect(
            admin.get(ROOT + "/device-models", params=query | {"search": f"absent-{run_id}"}), 200
        ).json()
        assert empty["total_pages"] == empty["total"] == 0 and not empty["items"]
        expect(admin.get(ROOT + "/device-models?page_size=101"), 422)
        print(
            "PASS CRUD, duplicates, cross-manufacturer, CSRF/version, filters/pagination/empty"
        )

        image_path = path + "/reference-images"
        version = 2
        images = []
        for number in range(5):
            result = expect(
                admin.post(
                    image_path,
                    files={"file": ("synthetic.png", image_bytes(), "image/png")},
                    data={"version": str(version), "angle": f"View {number}"},
                    headers=headers(admin),
                ),
                201,
            ).json()
            version = result["model_version"]
            images.append(result["image"])
        listed = expect(admin.get(image_path), 200).json()
        assert len(listed["items"]) == 5 and listed["model_version"] == 7
        assert sum(item["is_primary"] for item in listed["items"]) == 1
        for image in listed["items"]:
            assert "storage_key" not in image
            content = expect(admin.get(image["content_url"]), 200)
            assert content.headers["x-content-type-options"] == "nosniff"
            assert hashlib.sha256(content.content).hexdigest() == image["sha256"]
        expect(
            admin.post(
                image_path,
                files={"file": ("invalid.png", b"invalid", "image/png")},
                data={"version": str(version)},
                headers=headers(admin),
            ),
            415,
        )
        expect(
            admin.post(
                image_path,
                files={"file": ("large.png", b"x" * (8 * 1024 * 1024 + 1), "image/png")},
                data={"version": str(version)},
                headers=headers(admin),
            ),
            413,
        )
        assert expect(admin.get(image_path), 200).json()["model_version"] == version
        print("PASS five uploads, private content/hash, invalid/oversized rejection")

        for role in (Role.OFFICER, Role.VIEWER):
            with httpx.Client(
                base_url="http://web-smoke:3000", timeout=30, follow_redirects=False
            ) as reader:
                login(reader, role)
                assert reader.get("/catalog/models").status_code == 200
                assert "Akses terbatas" in reader.get("/catalog/models/new").text
                assert "Akses terbatas" in reader.get("/catalog/settings").text
                assert reader.get(f"/catalog/models/{model['id']}").status_code == 200
                for resource in ("device-categories", "manufacturers", "device-models"):
                    expect(reader.get(f"{ROOT}/{resource}"), 200)
                expect(reader.get(images[0]["content_url"]), 200)
                mutations = [
                    (
                        "POST",
                        ROOT + "/device-categories",
                        {"json": {"name": "Denied", "code": "denied"}},
                    ),
                    (
                        "PATCH",
                        f"{ROOT}/device-categories/{category['id']}",
                        {"json": {"version": 1, "is_active": False}},
                    ),
                    ("POST", ROOT + "/manufacturers", {"json": {"name": "Denied"}}),
                    (
                        "PATCH",
                        f"{ROOT}/manufacturers/{maker['id']}",
                        {"json": {"version": 1, "is_active": False}},
                    ),
                    ("POST", ROOT + "/device-models", {"json": data}),
                    ("PATCH", path, {"json": {"version": version, "is_active": False}}),
                    ("POST", path + "/archive", {"json": {"version": version}}),
                    (
                        "POST",
                        image_path,
                        {
                            "files": {"file": ("test.png", image_bytes(), "image/png")},
                            "data": {"version": str(version)},
                        },
                    ),
                    (
                        "DELETE",
                        image_path + "/" + images[0]["id"],
                        {"params": {"version": version}},
                    ),
                ]
                for method, endpoint, kwargs in mutations:
                    expect(reader.request(method, endpoint, headers=headers(reader), **kwargs), 403)
                expect(reader.post(ROOT + "/auth/logout", headers=headers(reader)), 204)
                expect(reader.get(path), 401)
        print(
            "PASS OFFICER/VIEWER reads, every mutation 403, SSR ADMIN gates, logout"
        )

        archived = expect(
            admin.post(path + "/archive", json={"version": version}, headers=headers(admin)), 200
        ).json()
        version = archived["version"]
        assert not archived["is_active"] and archived["id"] == model["id"]
        expect(
            admin.post(path + "/archive", json={"version": version}, headers=headers(admin)), 200
        )
        assert len(expect(admin.get(image_path), 200).json()["items"]) == 5
        expect(admin.get(images[0]["content_url"]), 200)
        expect(
            admin.post(
                image_path,
                files={"file": ("test.png", image_bytes(), "image/png")},
                data={"version": str(version)},
                headers=headers(admin),
            ),
            409,
        )
        deletion = expect(
            admin.delete(
                image_path + "/" + images[0]["id"],
                params={"version": version},
                headers=headers(admin),
            ),
            204,
        )
        assert not deletion.content and deletion.headers["x-model-version"] == "9"
        expect(admin.get(images[0]["content_url"]), 404)
        remaining = expect(admin.get(image_path), 200).json()
        assert (
            len(remaining["items"]) == 4 and sum(i["is_primary"] for i in remaining["items"]) == 1
        )
        with httpx.Client(base_url="http://web-smoke:3000") as anonymous:
            expect(anonymous.get(images[1]["content_url"]), 401)
        expect(admin.post(ROOT + "/auth/logout", headers=headers(admin)), 204)
        expect(admin.get(path), 401)
        print(
            "PASS archive/history/images, idempotency, delete/primary promotion, anonymous denial"
        )

    with SessionLocal() as db:
        events = list(
            db.scalars(select(AuditEvent).where(AuditEvent.actor_id == users[Role.ADMIN][0]))
        )
        counts = Counter(event.action for event in events)
        assert counts == {
            "login": 1,
            "catalog_create": 8,
            "catalog_update": 1,
            "reference_image_upload": 5,
            "catalog_archive": 1,
            "reference_image_delete": 1,
            "logout": 1,
        }, counts
        for event in events:
            assert event.created_at is not None
            expected = (
                {"table", "id", "version"}
                if event.action.startswith("catalog_")
                else {"model_id", "image_id", "version"}
                if event.action.startswith("reference_image_")
                else set()
            )
            if expected:
                assert set(event.details) == expected
        assert (
            db.scalar(
                select(func.count())
                .select_from(DeviceReferenceImage)
                .where(DeviceReferenceImage.device_model_id == uuid.UUID(model["id"]))
            )
            == 4
        )
        assert db.scalar(select(func.count()).select_from(StorageCleanupJob)) == 0
        for role in (Role.OFFICER, Role.VIEWER):
            actions = list(
                db.scalars(select(AuditEvent.action).where(AuditEvent.actor_id == users[role][0]))
            )
            assert Counter(actions) == {"login": 1, "logout": 1}
    print(
        "PASS persisted audit actions/actor/keys/timestamps, no false success audit, empty cleanup"
    )


if __name__ == "__main__":
    run()

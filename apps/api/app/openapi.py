"""Describe the existing cookie/CSRF contract without changing runtime authorization."""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def catalog_openapi(app: FastAPI) -> dict[str, Any]:
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=(
            "Local device model catalog and separate physical asset registry. "
            "Login issues HttpOnly cookies; obtain CSRF from /auth/csrf before login, "
            "then /auth/session for authenticated writes. Catalog and asset writes require ADMIN; "
            "OFFICER and VIEWER are read-only. PATCH/archive/upload/delete require the "
            "current record/model version; stale versions return 409 without overwriting. "
            "List order has UUID tie-breakers. Offset pagination is not a snapshot across "
            "requests; concurrent inserts/renames/archives may shift pages. "
            "Empty results have total_pages=0; an out-of-range page returns items=[]. "
            "Reference images are private, JPEG/PNG/WebP, at most 8 MiB per file "
            "(workspace limits may be lower). No host storage paths are exposed."
        ),
        routes=app.routes,
    )
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            if method not in {"post", "patch", "delete"}:
                continue
            operation.setdefault("parameters", []).extend(
                [
                    {
                        "name": "Origin",
                        "in": "header",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Exact allowed browser origin, e.g. http://localhost:3000.",
                    },
                    {
                        "name": "X-CSRF-Token",
                        "in": "header",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Token matching av_csrf cookie and current session.",
                    },
                ]
            )
            operation.setdefault("responses", {}).setdefault(
                "403",
                {
                    "description": "Role, Origin, or session CSRF rejected",
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/ErrorOutput"}}
                    },
                },
            )
            if path.startswith("/api/v1/device-") or path.startswith("/api/v1/manufacturers"):
                operation["description"] = (
                    operation.get("description", "") + " ADMIN only."
                ).strip()
            if path.startswith("/api/v1/assets"):
                policy = (
                    " ADMIN only. CSV preview is read-only; commit revalidates the full CSV and "
                    "requires a UUID idempotency_key. Replays return the stored result."
                    if "/imports/" in path
                    else " ADMIN only. Asset mutations require current version; identifier writes "
                    "require asset_version and PATCH/DELETE also require identifier version. "
                    "Successful identifier writes return the new asset_version."
                )
                operation["description"] = (operation.get("description", "") + policy).strip()
            if path.endswith("/imports/commit"):
                operation["responses"]["409"]["content"]["application/json"]["schema"] = {
                    "anyOf": [
                        {"$ref": "#/components/schemas/CsvCommitResult"},
                        {"$ref": "#/components/schemas/ErrorOutput"},
                    ]
                }
    app.openapi_schema = schema
    return schema

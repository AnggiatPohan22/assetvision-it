"""ADMIN CSV endpoints registered before the dynamic asset UUID route."""

import csv
import io
import json
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.asset_csv import COLUMNS, commit_csv, preview_csv
from app.asset_csv_schemas import (
    MAX_REQUEST_BYTES,
    CsvCommit,
    CsvCommitResult,
    CsvInput,
    CsvPreview,
)
from app.asset_routes import Admin, AssetFilters, asset_statement
from app.asset_schemas import IdentifierOutput
from app.assets import AssetIdentifier, IdentifierType
from app.catalog import DeviceModel, Manufacturer
from app.catalog_schemas import ErrorOutput
from app.dependencies import Database


class CsvRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            if request.method == "POST":
                media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if media != "application/json":
                    raise HTTPException(415, "CSV endpoints require JSON with csv_text")
                body = bytearray()
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                        raise HTTPException(413, "CSV request exceeds 1 MiB")
                    body.extend(chunk)
                request._body = bytes(body)
            return await original(request)

        return bounded


router = APIRouter(
    prefix="/api/v1/assets",
    tags=["Asset CSV"],
    route_class=CsvRoute,
    responses={
        401: {"model": ErrorOutput},
        403: {"model": ErrorOutput},
        413: {"model": ErrorOutput},
        415: {"model": ErrorOutput},
        422: {"model": ErrorOutput},
    },
)


@router.post("/imports/preview", response_model=CsvPreview)
def preview(data: CsvInput, db: Database, user: Admin) -> CsvPreview:
    return preview_csv(db, data.csv_text)


@router.post(
    "/imports/commit",
    response_model=CsvCommitResult,
    responses={
        409: {
            "model": CsvCommitResult,
            "description": "Batch rejected; no rows committed, or key conflict",
        }
    },
)
def commit(data: CsvCommit, db: Database, user: Admin) -> CsvCommitResult | JSONResponse:
    result = commit_csv(db, data, user)
    if result.status == "REJECTED":
        return JSONResponse(status_code=409, content=result.model_dump(mode="json"))
    return result


def safe_cell(value: str) -> str:
    # Quote alone does not prevent spreadsheet formula execution. Prefix hazardous cells.
    if value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def claim_values(claims: list[AssetIdentifier], kind: IdentifierType) -> str:
    return "\n".join(c.normalized_value for c in claims if c.identifier_type == kind)


@router.get(
    "/export.csv",
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}},
            "description": "ADMIN export; safe cells, all active claims in identifiers_json",
        }
    },
)
def export(db: Database, user: Admin, query: Annotated[AssetFilters, Query()]) -> Response:
    records = list(db.scalars(asset_statement(db, query).limit(5001)))
    if len(records) > 5000:
        raise HTTPException(413, "Export exceeds 5000 assets; narrow filters")
    target = io.StringIO(newline="")
    writer = csv.writer(target, lineterminator="\r\n")
    writer.writerow(
        COLUMNS + ["id", "version", "purchase_date", "installed_at", "identifiers_json"]
    )
    for asset in records:
        model = db.get(DeviceModel, asset.device_model_id)
        maker = db.get(Manufacturer, model.manufacturer_id)
        claims = list(
            db.scalars(
                select(AssetIdentifier)
                .where(
                    AssetIdentifier.asset_id == asset.id,
                    AssetIdentifier.deleted_at.is_(None),
                )
                .order_by(
                    AssetIdentifier.identifier_type,
                    AssetIdentifier.normalized_value,
                    AssetIdentifier.id,
                )
            )
        )

        row = [
            asset.asset_code,
            maker.name,
            model.model_name,
            claim_values(claims, IdentifierType.SERIAL_NUMBER),
            claim_values(claims, IdentifierType.MAC_LAN),
            claim_values(claims, IdentifierType.HOSTNAME),
            asset.condition,
            asset.lifecycle_status,
            asset.notes or "",
            "",
            str(asset.id),
            str(asset.version),
            str(asset.purchase_date or ""),
            asset.installed_at.isoformat() if asset.installed_at else "",
            json.dumps(
                [
                    IdentifierOutput.model_validate(c).model_dump(
                        mode="json", exclude={"collision_asset_ids"}
                    )
                    for c in claims
                ],
                ensure_ascii=False,
            ),
        ]
        writer.writerow([safe_cell(str(value)) for value in row])
        if target.tell() > 16 * 1024 * 1024:
            raise HTTPException(413, "Export exceeds 16 MiB character limit; narrow filters")
    content = ("\ufeff" + target.getvalue()).encode("utf-8")
    if len(content) > 16 * 1024 * 1024:
        raise HTTPException(413, "Export exceeds 16 MiB; narrow filters")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="assets.csv"'},
    )

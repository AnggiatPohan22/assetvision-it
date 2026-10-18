"""Create-only CSV validation and atomic, durable idempotent batch commits."""

import csv
import hashlib
import io
import json
from collections import defaultdict
from dataclasses import dataclass

from fastapi import HTTPException
from pydantic import Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.asset_csv_schemas import (
    MAX_ROWS,
    CsvCollision,
    CsvCommit,
    CsvCommitResult,
    CsvPreview,
    CsvRowResult,
)
from app.asset_imports import AssetImportBatch
from app.asset_schemas import AssetCode, AssetCreate, IdentifierCreate, RawValue
from app.asset_service import audit, snapshot
from app.assets import (
    AssetCondition,
    AssetEventType,
    AssetIdentifier,
    AssetUnit,
    IdentifierSource,
    IdentifierType,
    LifecycleStatus,
    VerificationStatus,
    normalize_identifier,
)
from app.catalog import DeviceModel, Manufacturer
from app.catalog_schemas import Description, Input, Name150, Name200
from app.models import User

REQUIRED = {"asset_code", "manufacturer", "model"}
COLUMNS = [
    "asset_code",
    "manufacturer",
    "model",
    "serial_number",
    "mac_address",
    "hostname",
    "condition",
    "status",
    "notes",
    "location_hint",
]
CLAIM_COLUMNS = {
    "serial_number": IdentifierType.SERIAL_NUMBER,
    "mac_address": IdentifierType.MAC_LAN,
    "hostname": IdentifierType.HOSTNAME,
}


class CsvRow(Input):
    asset_code: AssetCode
    manufacturer: Name150
    model: Name200
    serial_number: RawValue | None = None
    mac_address: RawValue | None = None
    hostname: RawValue | None = None
    condition: AssetCondition = AssetCondition.UNKNOWN
    status: LifecycleStatus = LifecycleStatus.IN_STOCK
    notes: Description | None = None
    location_hint: Description | None = Field(default=None, max_length=1000)


@dataclass
class PreparedRow:
    result: CsvRowResult
    data: CsvRow | None = None
    asset: AssetCreate | None = None
    claims: list[IdentifierCreate] | None = None


def parse_csv(csv_text: str) -> list[PreparedRow]:
    reader = csv.reader(io.StringIO(csv_text.lstrip("\ufeff"), newline=""), strict=True)
    try:
        header = [name.strip() for name in next(reader)]
        if (
            len(set(header)) != len(header)
            or not REQUIRED <= set(header)
            or set(header) - set(COLUMNS)
        ):
            raise HTTPException(
                422, "CSV requires unique known headers: asset_code, manufacturer, model"
            )
        rows: list[PreparedRow] = []
        for number, cells in enumerate(reader, 2):
            if not cells or not any(value.strip() for value in cells):
                continue
            if len(rows) == MAX_ROWS:
                raise HTTPException(422, "CSV exceeds 500 data rows")
            values = dict(zip(header, cells, strict=False))
            result = CsvRowResult(row=number, asset_code=values.get("asset_code", "")[:50])
            prepared = PreparedRow(result=result)
            rows.append(prepared)
            if len(cells) != len(header):
                result.errors.append("Column count differs from header")
                continue
            # An empty optional claim is absence of evidence, never a placeholder claim.
            values = {
                key: value for key, value in values.items() if value.strip() or key in REQUIRED
            }
            try:
                data = CsvRow.model_validate(values)
                prepared.data = data
                result.asset_code = data.asset_code
                result.location_hint = data.location_hint
                prepared.claims = [
                    IdentifierCreate(
                        asset_version=1,
                        identifier_type=kind,
                        raw_value=getattr(data, key),
                        source=IdentifierSource.IMPORT,
                        verification_status=VerificationStatus.UNVERIFIED,
                    )
                    for key, kind in CLAIM_COLUMNS.items()
                    if getattr(data, key) is not None
                ]
            except ValidationError as exc:
                fields = sorted(
                    {str(e["loc"][0]) if e["loc"] else "identifier" for e in exc.errors()}
                )
                result.errors.append("Invalid CSV fields: " + ", ".join(fields))
        if not rows:
            raise HTTPException(422, "CSV contains no data rows")
        return rows
    except (StopIteration, csv.Error):
        raise HTTPException(422, "Malformed or empty CSV") from None


def validate_rows(db: Session, rows: list[PreparedRow], *, lock: bool = False) -> CsvPreview:
    codes: dict[str, list[int]] = defaultdict(list)
    claims: dict[tuple[IdentifierType, str], list[int]] = defaultdict(list)
    for row in rows:
        if row.data is None:
            continue
        data, result = row.data, row.result
        codes[data.asset_code].append(result.row)
        statement = (
            select(DeviceModel)
            .join(Manufacturer)
            .where(
                Manufacturer.normalized_name == data.manufacturer.lower(),
                DeviceModel.normalized_model_name == data.model.lower(),
            )
        )
        if lock:
            statement = statement.with_for_update(read=True).execution_options(
                populate_existing=True
            )
        model = db.scalar(statement)
        if model is None:
            result.errors.append(
                "Unknown manufacturer/model; catalog is never created automatically"
            )
        elif not model.is_active:
            result.errors.append("Device model is inactive")
        else:
            row.asset = AssetCreate(
                asset_code=data.asset_code,
                device_model_id=model.id,
                lifecycle_status=data.status,
                condition=data.condition,
                notes=data.notes,
            )
        if (
            db.scalar(select(AssetUnit.id).where(AssetUnit.asset_code == data.asset_code))
            is not None
        ):
            result.errors.append(
                "Asset code already exists/reserved; import never updates existing units"
            )
        for claim in row.claims or []:
            normalized = normalize_identifier(claim.identifier_type, claim.raw_value)
            claims[(claim.identifier_type, normalized)].append(result.row)
    for row in rows:
        result = row.result
        if row.data is not None and len(codes[row.data.asset_code]) > 1:
            result.errors.append("Duplicate asset code within CSV")
        for claim in row.claims or []:
            normalized = normalize_identifier(claim.identifier_type, claim.raw_value)
            others = list(
                db.scalars(
                    select(AssetIdentifier.asset_id)
                    .where(
                        AssetIdentifier.identifier_type == claim.identifier_type,
                        AssetIdentifier.normalized_value == normalized,
                        AssetIdentifier.deleted_at.is_(None),
                    )
                    .distinct()
                    .order_by(AssetIdentifier.asset_id)
                )
            )
            csv_rows = [n for n in claims[(claim.identifier_type, normalized)] if n != result.row]
            if others or csv_rows:
                result.collisions.append(
                    CsvCollision(
                        identifier_type=claim.identifier_type,
                        normalized_value=normalized,
                        asset_ids=others,
                        csv_rows=csv_rows,
                    )
                )
        result.valid = not result.errors
    valid = sum(row.result.valid for row in rows)
    return CsvPreview(
        total_rows=len(rows),
        valid_rows=valid,
        invalid_rows=len(rows) - valid,
        has_collisions=any(row.result.collisions for row in rows),
        rows=[row.result for row in rows],
    )


def preview_csv(db: Session, csv_text: str) -> CsvPreview:
    return validate_rows(db, parse_csv(csv_text))


def receipt(db: Session, request: CsvCommit, user: User, digest: str) -> CsvCommitResult | None:
    batch = db.get(AssetImportBatch, request.idempotency_key)
    if batch is None:
        return None
    if batch.actor_id != user.id or batch.request_sha256 != digest:
        raise HTTPException(409, "Idempotency key belongs to another actor or payload")
    return CsvCommitResult.model_validate(batch.result_json)


def commit_csv(db: Session, request: CsvCommit, user: User) -> CsvCommitResult:
    digest = hashlib.sha256(
        json.dumps(
            {
                "csv_text": request.csv_text,
                "allow_identifier_collisions": request.allow_identifier_collisions,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    previous = receipt(db, request, user, digest)
    if previous is not None:
        return previous
    rows = parse_csv(request.csv_text)
    try:
        # Reserve the key before domain writes. The placeholder is never committed/visible.
        batch = AssetImportBatch(
            id=request.idempotency_key, actor_id=user.id, request_sha256=digest, result_json={}
        )
        db.add(batch)
        db.flush()
        preview = validate_rows(db, rows, lock=True)
        if preview.invalid_rows or (
            preview.has_collisions and not request.allow_identifier_collisions
        ):
            db.rollback()
            return CsvCommitResult(
                import_id=request.idempotency_key,
                status="REJECTED",
                created_count=0,
                failed_count=preview.total_rows,
                rows=preview.rows,
                errors=[
                    "Whole batch rejected; fix row errors and explicitly acknowledge "
                    "identifier collisions"
                ],
            )
        # Deterministic insertion order avoids opposite-order uniqueness waits between batches.
        for row in sorted(rows, key=lambda item: item.result.asset_code):
            assert row.asset is not None
            asset = AssetUnit(**row.asset.model_dump())
            db.add(asset)
            audit(db, asset, user, AssetEventType.CREATE, None)
            for data in row.claims or []:
                before = snapshot(asset)
                claim = AssetIdentifier(
                    asset_id=asset.id, **data.model_dump(exclude={"asset_version"})
                )
                db.add(claim)
                asset.version += 1
                audit(db, asset, user, AssetEventType.IDENTIFIER_ADD, before, claim)
            row.result.asset_id, row.result.version = asset.id, asset.version
        result = CsvCommitResult(
            import_id=batch.id,
            status="COMMITTED",
            created_count=len(rows),
            failed_count=0,
            rows=[row.result for row in rows],
        )
        batch.result_json = result.model_dump(mode="json")
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        # Concurrent same-key commits wait on the PK then replay the committed receipt.
        previous = receipt(db, request, user, digest)
        if previous is not None:
            return previous
        for row in rows:
            row.result.asset_id = None
            row.result.version = None
        return CsvCommitResult(
            import_id=request.idempotency_key,
            status="REJECTED",
            created_count=0,
            failed_count=len(rows),
            rows=[row.result for row in rows],
            errors=[
                "Whole batch rolled back: concurrent asset/reference conflict or audit failure; "
                "preview again"
            ],
        )
    except Exception:
        db.rollback()
        raise

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.asset_imports import AssetImportBatch
from app.asset_locations import AssetLocationEvent
from app.assets import AssetChangeEvent, AssetIdentifier, AssetUnit
from app.catalog import (
    DeviceCategory,
    DeviceModel,
    DeviceReferenceImage,
    Manufacturer,
    StorageCleanupJob,
)
from app.config import get_settings
from app.dependencies import CurrentUser, Database, current_session, require_roles
from app.locations import Location
from app.models import AuditEvent, AuthSession, Role, User
from app.movements import AssetMovement
from app.observations import LocationObservation
from app.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    DUMMY_HASH,
    csrf_digest,
    issue_token,
    new_csrf,
    session_expiry,
    set_cookie,
    valid_csrf,
    verify_password,
)

router = APIRouter(prefix="/api/v1")


class LoginInput(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class UserOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    name: str
    role: Role


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Database) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT PostGIS_Version()"))
        version = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if version != "0009_observations":
            raise ValueError("Schema not current")
        db.execute(select(User.id).limit(1))
        db.execute(select(AuthSession.id).limit(1))
        db.execute(select(AuditEvent.id).limit(1))
        for model in (
            DeviceCategory,
            Manufacturer,
            DeviceModel,
            DeviceReferenceImage,
            StorageCleanupJob,
            AssetUnit,
            AssetIdentifier,
            AssetChangeEvent,
            AssetImportBatch,
            Location,
            AssetLocationEvent,
            AssetMovement,
            LocationObservation,
        ):
            db.execute(select(model).limit(1))
    except (SQLAlchemyError, ValueError):
        raise HTTPException(503, "Database or schema is not ready") from None
    return {"status": "ready"}


@router.get("/auth/csrf")
def csrf(response: Response, request: Request) -> dict[str, str]:
    existing = request.cookies.get(CSRF_COOKIE, "")
    if valid_csrf(existing):
        return {"csrf_token": existing}
    token = new_csrf()
    set_cookie(response, CSRF_COOKIE, token, 3600)
    return {"csrf_token": token}


@router.post("/auth/login", response_model=UserOutput)
def login(data: LoginInput, response: Response, db: Database) -> User:
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    valid_password = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid_password or not user.is_active:
        db.add(AuditEvent(action="login_failed"))
        db.commit()
        raise HTTPException(401, "Invalid email or password")
    token = new_csrf()
    session = AuthSession(
        user_id=user.id, csrf_hash=csrf_digest(token), expires_at=session_expiry()
    )
    db.add(session)
    db.add(AuditEvent(actor_id=user.id, action="login"))
    db.commit()
    seconds = get_settings().access_token_expire_minutes * 60
    set_cookie(
        response, ACCESS_COOKIE, issue_token(user.id, session.id, session.expires_at), seconds
    )
    set_cookie(response, CSRF_COOKIE, token, seconds)
    return user


@router.get("/auth/me", response_model=UserOutput)
def me(user: CurrentUser) -> User:
    return user


@router.post("/auth/logout", status_code=204)
def logout(
    response: Response,
    db: Database,
    user: CurrentUser,
    session: Annotated[AuthSession, Depends(current_session)],
) -> None:
    session.revoked = True
    db.add(AuditEvent(actor_id=user.id, action="logout"))
    db.commit()
    for name in (ACCESS_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            name,
            path="/",
            secure=get_settings().cookie_secure,
            httponly=True,
            samesite="lax",
        )


@router.get("/auth/session")
def session_csrf(
    user: CurrentUser,
    session: Annotated[AuthSession, Depends(current_session)],
    request: Request,
) -> dict[str, str]:
    token = request.cookies.get(CSRF_COOKIE, "")
    if csrf_digest(token) != session.csrf_hash:
        raise HTTPException(403, "Session CSRF cookie missing; sign in again")
    return {"csrf_token": token}


@router.get("/admin/status")
def admin_status(user: Annotated[User, Depends(require_roles(Role.ADMIN))]) -> dict[str, str]:
    return {"status": "ok", "role": user.role.value}

"""Explicit, idempotent initial admin creation. Password comes only from getpass."""

import argparse
from getpass import getpass

from pydantic import BaseModel, EmailStr, Field, ValidationError
from sqlalchemy import func, select, text

from app.db import SessionLocal
from app.models import AuditEvent, Role, User
from app.security import hash_password


class AdminInput(BaseModel):
    email: EmailStr = Field(max_length=254)
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    password: str = Field(min_length=12, max_length=128)


def bootstrap_admin(email: str, name: str, password: str) -> bool:
    data = AdminInput(email=email, name=name, password=password)
    with SessionLocal.begin() as db:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(649237801)"))
        existing = db.scalar(select(User).where(User.email == str(data.email).lower()))
        if existing:
            if existing.role != Role.ADMIN or not existing.is_active:
                raise ValueError("Existing account is not an active administrator; no changes made")
            return False
        if db.scalar(select(func.count()).select_from(User)):
            raise ValueError("Initial bootstrap requires an empty users table; no changes made")
        user = User(
            email=str(data.email).lower(),
            name=data.name.strip(),
            password_hash=hash_password(data.password),
            role=Role.ADMIN,
        )
        db.add(user)
        db.flush()
        db.add(AuditEvent(actor_id=user.id, action="admin_bootstrap"))
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    password = getpass("Initial admin password (12-128 characters): ")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords do not match")
    try:
        created = bootstrap_admin(args.email, args.name, password)
    except ValidationError:
        raise SystemExit("Invalid email, name, or password length; no changes made") from None
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print("Initial admin created" if created else "Active admin already exists; unchanged")


if __name__ == "__main__":
    main()

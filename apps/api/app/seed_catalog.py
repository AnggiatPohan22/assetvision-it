"""Explicit synthetic category/manufacturer seed. Never run automatically on startup."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.catalog import DeviceCategory, Manufacturer
from app.db import SessionLocal

CATEGORIES = (
    ("access-point", "Access Point"),
    ("router", "Router"),
    ("switch", "Switch"),
    ("cctv", "CCTV"),
    ("printer", "Printer"),
)
MANUFACTURERS = ("Ruijie", "Ubiquiti", "MikroTik")


def seed_catalog(db: Session) -> None:
    """Caller owns the transaction; existing rows, including archives, are preserved."""
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(649237802)"))
    for code, name in CATEGORIES:
        if db.scalar(select(DeviceCategory.id).where(DeviceCategory.code == code)) is None:
            db.add(DeviceCategory(code=code, name=name))
    for name in MANUFACTURERS:
        if db.scalar(
            select(Manufacturer.id).where(Manufacturer.normalized_name == name.lower())
        ) is None:
            db.add(Manufacturer(name=name))
    db.flush()


def main() -> None:
    with SessionLocal.begin() as db:
        seed_catalog(db)
    print("Synthetic catalog seed complete; existing records unchanged")


if __name__ == "__main__":
    main()

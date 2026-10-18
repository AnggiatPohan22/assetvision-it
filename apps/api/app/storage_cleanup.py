"""Retry up to 100 persisted cleanup intents older than ten minutes; no file scanning."""

from app.db import SessionLocal
from app.image_service import cleanup_pending
from app.storage import get_storage


def main() -> None:
    with SessionLocal() as db:
        completed = cleanup_pending(db, get_storage())
    print(f"Completed cleanup intents: {completed}")


if __name__ == "__main__":
    main()

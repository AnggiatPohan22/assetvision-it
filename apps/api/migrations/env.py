from typing import Any

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection

from app import models  # noqa: F401
from app.config import get_settings
from app.db import Base

target_metadata = Base.metadata


def include_object(obj: Any, name: str, type_: str, reflected: bool, compare_to: Any) -> bool:
    return not (type_ == "table" and name == "spatial_ref_sys")


def migrate(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations() -> None:
    if context.is_offline_mode():
        context.configure(
            url=get_settings().db_url, target_metadata=target_metadata, literal_binds=True
        )
        with context.begin_transaction():
            context.run_migrations()
    elif context.config.attributes.get("connection") is not None:
        migrate(context.config.attributes["connection"])
    else:
        connectable = create_engine(get_settings().db_url, poolclass=pool.NullPool)
        with connectable.connect() as connection:
            migrate(connection)
        connectable.dispose()


run_migrations()

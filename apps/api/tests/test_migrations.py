from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def test_migration_roundtrip(factory) -> None:
    with factory.kw["bind"].connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.check(config)
        assert {"users", "auth_sessions", "audit_events"} <= set(
            inspect(connection).get_table_names()
        )
        connection.commit()
        command.downgrade(config, "base")
        assert "users" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0001_sprint0"
        )
        command.check(config)

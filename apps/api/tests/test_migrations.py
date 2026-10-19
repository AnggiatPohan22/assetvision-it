from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text


def test_migration_roundtrip(factory) -> None:
    with factory.kw["bind"].connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.check(config)
        catalog_tables = {
            "device_categories",
            "manufacturers",
            "device_models",
            "device_reference_images",
            "storage_cleanup_jobs",
            "assets",
            "asset_identifiers",
            "asset_change_events",
            "asset_import_batches",
            "locations",
            "asset_events",
            "asset_movements",
            "location_observations",
            "embedding_indexes",
            "image_embeddings",
            "embedding_index_state",
        }
        assert {"users", "auth_sessions", "audit_events"} | catalog_tables <= set(
            inspect(connection).get_table_names()
        )
        connection.commit()
        command.downgrade(config, "base")
        assert not ({"users"} | catalog_tables) & set(inspect(connection).get_table_names())
        command.upgrade(config, "head")
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0010_embedding_index"
        )
        command.check(config)


def test_catalog_migration_preserves_sprint0_data(factory, user) -> None:
    with factory.kw["bind"].connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.downgrade(config, "0001_sprint0")
        assert "device_models" not in inspect(connection).get_table_names()
        assert connection.execute(text("SELECT email FROM users")).scalar_one() == user.email
        connection.commit()
        command.upgrade(config, "head")
        assert connection.execute(text("SELECT email FROM users")).scalar_one() == user.email
        command.check(config)


def test_image_cleanup_migration_preserves_catalog(factory, db) -> None:
    from app.catalog import DeviceCategory

    category = DeviceCategory(code="synthetic", name="Synthetic category")
    db.add(category)
    db.commit()
    with factory.kw["bind"].connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.downgrade(config, "0002_device_catalog")
        assert "storage_cleanup_jobs" not in inspect(connection).get_table_names()
        assert (
            connection.execute(text("SELECT name FROM device_categories")).scalar_one()
            == category.name
        )
        connection.commit()
        command.upgrade(config, "head")
        command.check(config)
        assert (
            connection.execute(text("SELECT name FROM device_categories")).scalar_one()
            == category.name
        )

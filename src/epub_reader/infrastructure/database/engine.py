from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL

from epub_reader.infrastructure.database import sync_models  # noqa: F401 - registers tables
from epub_reader.infrastructure.database.models import Base


def create_database(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite", database=str(path)),
        connect_args={"check_same_thread": False, "timeout": 15},
    )

    @event.listens_for(engine, "connect")
    def configure(connection: Any, _: Any) -> None:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")

    with engine.begin() as connection:
        version = int(connection.exec_driver_sql("PRAGMA user_version").scalar_one())
        if version not in (0, 1, 2, 3, 4, 5):
            raise RuntimeError("This library database needs a newer version of Epubify.")
        if version == 1:
            connection.exec_driver_sql(
                "ALTER TABLE books ADD COLUMN location TEXT NOT NULL DEFAULT ''"
            )
        Base.metadata.create_all(connection)
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(books)")}
        if "categories" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE books ADD COLUMN categories TEXT NOT NULL DEFAULT '[]'"
            )
        if "classification_version" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE books ADD COLUMN classification_version INTEGER NOT NULL DEFAULT 0"
            )
        if "favorite" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE books ADD COLUMN favorite BOOLEAN NOT NULL DEFAULT 0"
            )
        connection.exec_driver_sql("PRAGMA user_version=5")
    return engine

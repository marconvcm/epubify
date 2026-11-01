from pathlib import Path

import pytest

from epub_reader.infrastructure.database.engine import create_database
from epub_reader.infrastructure.database.repositories import SqlBookRepository
from tests.fixtures.epub_factory import make_epub


@pytest.fixture
def epub(tmp_path: Path) -> Path:
    return make_epub(tmp_path / "quiet.epub")


@pytest.fixture
def repository(tmp_path: Path):
    engine = create_database(tmp_path / "data/library.sqlite3")
    yield SqlBookRepository(engine)
    engine.dispose()

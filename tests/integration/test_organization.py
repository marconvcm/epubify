from pathlib import Path

import pytest
from PySide6.QtCore import QObject

from epub_reader.bootstrap import create_runtime
from epub_reader.core.paths import AppPaths
from epub_reader.infrastructure.database.engine import create_database
from epub_reader.infrastructure.database.repositories import SqlBookRepository
from epub_reader.services.classification_service import CLASSIFICATION_VERSION
from epub_reader.services.epub_import_service import EpubImportService
from tests.fixtures.epub_factory import make_epub


@pytest.mark.gui
def test_categories_favorites_and_search_combine_and_survive_restart(qtbot, tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "app")
    runtime = create_runtime(paths)
    try:
        first = runtime.library.importer.import_book(
            make_epub(tmp_path / "python.epub", title="Python Robotics Projects")
        )
        second = runtime.library.importer.import_book(
            make_epub(tmp_path / "plc.epub", title="Mastering PLC Programming")
        )
        for book in (first, second):
            runtime.library.model.upsert(book)
        assert {r["categoryId"] for r in runtime.library.categories} == {
            "robotics",
            "automation",
            "programming",
        }
        runtime.library.selectCategory("robotics")
        assert runtime.library.filtered.rowCount() == 1
        runtime.library.filtered.search("PLc")
        assert runtime.library.filtered.rowCount() == 0
        runtime.library.filtered.search("")
        runtime.library.toggleFavorite(first.id)
        assert runtime.library.favoriteCount == 1
        runtime.library.selectFavorites()
        assert runtime.library.filtered.rowCount() == 1
        runtime.library.toggleFavorite(first.id)
        assert runtime.library.filtered.rowCount() == 0
        runtime.library.toggleFavorite(second.id)
        assert runtime.library.filtered.rowCount() == 1
        assert (
            runtime.library.filtered.data(
                runtime.library.filtered.index(0, 0),
                next(
                    int(role)
                    for role, name in runtime.library.model.ROLES.items()
                    if name == b"bookTitle"
                ),
            )
            == second.title
        )
    finally:
        runtime.dispose()
    restored = create_runtime(paths)
    try:
        assert restored.library.favoriteCount == 1
        assert {c.id for c in restored.library.importer.repository.get(first.id).categories} == {
            "robotics",
            "programming",
        }
        root = restored.engine.rootObjects()[0]
        assert root.findChild(QObject, "favoritesButton") is not None
        assert root.findChild(QObject, "settingsButton") is not None
    finally:
        restored.dispose()


@pytest.mark.gui
def test_legacy_books_are_classified_in_background_without_losing_reading_state(
    qtbot, tmp_path: Path
) -> None:
    paths = AppPaths(tmp_path / "app")
    paths.create()
    engine = create_database(paths.database)
    repository = SqlBookRepository(engine)
    book = EpubImportService(repository, paths.books).import_book(
        make_epub(tmp_path / "legacy.epub", title="Practical Arduino Robotics")
    )
    repository.save_categories(book.id, (), 0)
    repository.set_favorite(book.id, True)
    engine.dispose()
    runtime = create_runtime(paths)
    try:
        qtbot.waitUntil(
            lambda: runtime.library.model.books[0].classification_version == CLASSIFICATION_VERSION,
            timeout=5000,
        )
        saved = runtime.library.importer.repository.get(book.id)
        assert saved.favorite
        assert {c.id for c in saved.categories} == {"robotics", "electronics"}
        assert runtime.library.favoriteCount == 1
    finally:
        runtime.dispose()

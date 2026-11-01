from pathlib import Path

import pytest

from epub_reader.domain.models.reading_progress import ReadingLocation
from epub_reader.infrastructure.database.engine import create_database
from epub_reader.infrastructure.database.repositories import PreferenceRepository, SqlBookRepository
from epub_reader.infrastructure.epub.extraction import EpubError
from epub_reader.services.epub_import_service import EpubImportService
from epub_reader.services.library_service import LibraryService
from epub_reader.services.reading_service import ReadingService


def test_import_is_idempotent_and_source_can_be_removed(
    repository, epub: Path, tmp_path: Path
) -> None:
    service = EpubImportService(repository, tmp_path / "books")
    first = service.import_book(epub)
    second = service.import_book(epub)
    assert first.id == second.id
    assert len(repository.list()) == 1
    epub.unlink()
    assert (first.storage_path / first.package_path).is_file()
    assert first.cover_path and first.cover_path.is_file()


def test_repository_crud_and_unknown_id(repository, epub: Path, tmp_path: Path) -> None:
    book = EpubImportService(repository, tmp_path / "books").import_book(epub)
    assert repository.get(book.id) == book
    assert repository.get("unknown") is None
    repository.mark_opened(book.id)
    assert repository.get(book.id).last_opened_at is not None
    repository.delete(book.id)
    assert repository.list() == []
    repository.delete(book.id)
    with pytest.raises(KeyError):
        repository.mark_opened(book.id)


def test_library_and_location_survive_database_restart(epub: Path, tmp_path: Path) -> None:
    path = tmp_path / "library.sqlite3"
    engine = create_database(path)
    repo = SqlBookRepository(engine)
    book = EpubImportService(repo, tmp_path / "books").import_book(epub)
    reading = ReadingService(repo)
    reading.open(book.id)
    location = ReadingLocation("EPUB/chapter2.xhtml", 12).encode()
    reading.save(book.id, location, 0.45)
    PreferenceRepository(engine).set("dark", False)
    engine.dispose()
    restored = create_database(path)
    try:
        loaded = SqlBookRepository(restored).get(book.id)
        assert loaded.location == location
        assert loaded.progress == 0.45
        assert loaded.last_opened_at is not None
        assert PreferenceRepository(restored).get("dark", True) is False
    finally:
        restored.dispose()


def test_preferences_types_and_defaults(repository) -> None:
    prefs = PreferenceRepository(repository.engine)
    assert prefs.get("font_size", 20) == 20
    prefs.set("font_size", 24)
    prefs.set("reduced_motion", True)
    assert prefs.get("font_size", 20) == 24
    assert prefs.get("reduced_motion", False) is True
    prefs.set("font_size", "invalid")
    assert prefs.get("font_size", 20) == 20


def test_search_matches_title_or_author_case_insensitively(
    repository, epub: Path, tmp_path: Path
) -> None:
    book = EpubImportService(repository, tmp_path / "books").import_book(epub)
    assert LibraryService.matches(book, "QUIET")
    assert LibraryService.matches(book, " contributors ")
    assert LibraryService.matches(book, "")
    assert not LibraryService.matches(book, "another author")


def test_failed_import_does_not_pollute_storage_or_database(repository, tmp_path: Path) -> None:
    path = tmp_path / "broken.epub"
    path.write_bytes(b"not an epub")
    storage = tmp_path / "books"
    with pytest.raises(EpubError):
        EpubImportService(repository, storage).import_book(path)
    assert repository.list() == []
    assert list(storage.iterdir()) == []


def test_schema_one_migrates_without_deleting_books_or_legacy_locations(
    epub: Path, tmp_path: Path
) -> None:
    path = tmp_path / "legacy.sqlite3"
    engine = create_database(path)
    book = EpubImportService(SqlBookRepository(engine), tmp_path / "books").import_book(epub)
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE books DROP COLUMN location")
        connection.exec_driver_sql("UPDATE books SET cfi='legacy-position', progress=0.25")
        connection.exec_driver_sql("PRAGMA user_version=1")
    engine.dispose()
    upgraded = create_database(path)
    try:
        loaded = SqlBookRepository(upgraded).get(book.id)
        assert loaded.title == book.title
        assert loaded.location == ""
        assert loaded.progress == 0.25
        with upgraded.connect() as connection:
            assert (
                connection.exec_driver_sql("SELECT cfi FROM books").scalar_one()
                == "legacy-position"
            )
            assert connection.exec_driver_sql("PRAGMA user_version").scalar_one() == 5
    finally:
        upgraded.dispose()

from pathlib import Path

import pytest
from PySide6.QtCore import QMetaObject, QObject

from epub_reader.bootstrap import create_runtime
from epub_reader.core.paths import AppPaths
from epub_reader.infrastructure.database.repositories import PreferenceRepository
from tests.fixtures.navigation_factory import make_navigation_epub


@pytest.mark.gui
def test_notes_edit_jump_and_persist_and_sync_panel_opens(qtbot, tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "app")
    runtime = create_runtime(paths)
    try:
        book = runtime.library.importer.import_book(make_navigation_epub(tmp_path / "book.epub"))
        runtime.reader.openBook(book.id)
        root = runtime.engine.rootObjects()[0]
        qtbot.waitUntil(lambda: root.findChild(QObject, "notesButton") is not None)
        runtime.reader.navigate("EPUB/chapter2.xhtml#p12")
        saved_location = runtime.reader.engine.location
        runtime.reader.addNote("A local note")
        note = runtime.reader.notes[0]
        assert note["location"] == saved_location.encode()
        runtime.reader.updateNote(note["id"], "Edited offline")
        runtime.reader.navigate("EPUB/chapter1.xhtml")
        runtime.reader.navigateNote(note["location"])
        assert runtime.reader.engine.location == saved_location
        assert QMetaObject.invokeMethod(root.findChild(QObject, "notesButton"), "clicked")
        qtbot.waitUntil(lambda: root.findChild(QObject, "notesPanel").property("opened"))
        QMetaObject.invokeMethod(root.findChild(QObject, "notesPanel"), "close")
        settings = root.findChild(QObject, "readerSettings")
        QMetaObject.invokeMethod(settings, "open")
        qtbot.waitUntil(lambda: settings.property("opened"))
        panel = settings.findChild(QObject, "syncPanel")
        assert QMetaObject.invokeMethod(panel, "open")
        qtbot.waitUntil(lambda: panel.property("opened"))
        assert runtime.sync.available and not runtime.sync.enabled
        assert not list((paths.root / "sync").glob("**/identity-key.pem"))
    finally:
        runtime.dispose()
    restored = create_runtime(paths)
    try:
        restored.reader.openBook(book.id)
        assert restored.reader.notes[0]["text"] == "Edited offline"
        restored.reader.removeNote(note["id"])
        assert not restored.reader.notes
    finally:
        restored.dispose()


@pytest.mark.gui
def test_remote_preferences_and_new_books_refresh_qml_without_restart(
    qtbot, tmp_path: Path
) -> None:
    paths = AppPaths(tmp_path / "app")
    runtime = create_runtime(paths)
    try:
        root = runtime.engine.rootObjects()[0]
        # The network worker emits this queued boundary after committing SQLite.
        book = runtime.library.importer.import_book(make_navigation_epub(tmp_path / "new.epub"))
        assert runtime.library.count == 0
        repository = PreferenceRepository(runtime.database)
        repository.set("language", "pt")
        repository.set("color_scheme", "macos")
        runtime.sync.dataChanged.emit(
            {"books": [book.id], "preferences": ["language", "color_scheme"]}
        )
        qtbot.waitUntil(lambda: runtime.library.count == 1)
        assert runtime.reader.preferences.colorScheme == "macos"
        assert root.findChild(QObject, "importEpubButton").property("text") == "Importar EPUBs"
    finally:
        runtime.dispose()

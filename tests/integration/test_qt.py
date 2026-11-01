from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QSize, QUrl
from PySide6.QtGui import QImage, QTextDocument

from epub_reader.bootstrap import create_runtime
from epub_reader.core.paths import AppPaths
from epub_reader.infrastructure.database.repositories import SqlBookRepository
from epub_reader.presentation.models.book_list_model import BookFilterModel, BookListModel
from epub_reader.rendering.document import PublicationDocument
from epub_reader.rendering.engine import NativeBookEngine
from epub_reader.services.epub_import_service import EpubImportService


@pytest.mark.gui
def test_qml_window_loads(qtbot, tmp_path: Path) -> None:
    runtime = create_runtime(AppPaths(tmp_path), library_only=True)
    try:
        root = runtime.engine.rootObjects()[0]
        assert root.objectName() == "mainWindow"
        assert root.property("visible") is True
        assert runtime.library.count == 0
    finally:
        runtime.dispose()


@pytest.mark.gui
def test_qt_model_filters_and_updates_one_row(
    qtbot, repository, epub: Path, tmp_path: Path
) -> None:
    book = EpubImportService(repository, tmp_path / "books").import_book(epub)
    model = BookListModel([])
    proxy = BookFilterModel(model)
    with qtbot.waitSignal(model.rowsInserted):
        model.upsert(book)
    assert proxy.rowCount() == 1
    proxy.search("missing")
    assert proxy.rowCount() == 0
    proxy.search("CONTRIBUTORS")
    assert proxy.rowCount() == 1
    with qtbot.waitSignal(model.dataChanged):
        model.upsert(book)
    assert model.rowCount() == 1


@pytest.mark.gui
def test_import_worker_updates_qml_model(qtbot, tmp_path: Path, epub: Path) -> None:
    runtime = create_runtime(AppPaths(tmp_path / "app"), library_only=True)
    try:
        runtime.library.importFile(QUrl.fromLocalFile(str(epub)))
        qtbot.waitUntil(lambda: not runtime.library.busy, timeout=10_000)
        assert runtime.library.count == 1
        assert len(list((tmp_path / "app/covers").glob("*.png"))) == 1
    finally:
        runtime.dispose()


@pytest.mark.gui
@pytest.mark.parametrize("version", [2, 3])
def test_native_pagination_links_and_exact_restore(qtbot, tmp_path: Path, version: int) -> None:
    from tests.fixtures.epub_factory import make_epub

    runtime = create_runtime(AppPaths(tmp_path / "app"))
    try:
        epub = make_epub(tmp_path / "book.epub", version=version)
        book = runtime.library.importer.import_book(epub)
        runtime.reader.openBook(book.id)
        engine = runtime.reader.engine
        assert runtime.reader.active
        assert not runtime.reader.error
        assert not engine.image.isNull()
        assert engine.pages > 2
        assert len(runtime.reader.toc) == 2
        runtime.reader.next()
        location = engine.location
        assert engine.page == 1
        assert location.offset > 0
        runtime.reader.flush()
        saved = SqlBookRepository(runtime.database).get(book.id)
        assert saved.location == location.encode()
        runtime.reader.close()
        runtime.reader.openBook(book.id)
        assert engine.location == location
        assert engine.page == 1
        runtime.reader.navigate(runtime.reader.toc[1]["href"])
        assert engine.chapter_index == 1
        runtime.reader.navigate("#p5")
        assert engine.anchor_offset > 0
        runtime.reader.previous()
        assert not engine.image.isNull()
    finally:
        runtime.dispose()


@pytest.mark.gui
def test_native_reflow_preserves_text_offset_and_high_dpi(
    qtbot, repository, epub: Path, tmp_path: Path
) -> None:
    book = EpubImportService(repository, tmp_path / "books").import_book(epub)
    engine = NativeBookEngine()
    engine.open(book)
    engine.next()
    location = engine.location
    engine.configure(26, False)
    assert engine.location == location
    engine.set_viewport(620, 540, 2)
    assert engine.location == location
    assert engine.image.width() == 1240
    assert engine.image.height() == 1080
    assert engine.image.pixelColor(0, 0).name() == "#edede9"
    restored = NativeBookEngine()
    restored.configure(26, False)
    restored.set_viewport(620, 540, 2)
    restored.open(replace(book, location=location.encode()))
    assert restored.page == engine.page
    assert restored.location == location


@pytest.mark.gui
def test_actual_qml_reader_and_restart_resume(qtbot, tmp_path: Path, epub: Path) -> None:
    paths = AppPaths(tmp_path / "app")
    runtime = create_runtime(paths)
    try:
        book = runtime.library.importer.import_book(epub)
        runtime.reader.openBook(book.id)
        root = runtime.engine.rootObjects()[0]
        qtbot.waitUntil(lambda: root.findChild(QObject, "nativeBookPage") is not None)
        qtbot.wait(150)  # Allow the view's debounced viewport layout.
        runtime.reader.next()
        location = runtime.reader.engine.location
        runtime.reader.flush()
        assert root.grabWindow().isNull() is False
    finally:
        runtime.dispose()
    restored = create_runtime(paths)
    try:
        restored.reader.openBook(book.id)
        assert restored.reader.engine.location == location
        assert not restored.reader.error
    finally:
        restored.dispose()


@pytest.mark.gui
def test_qml_theme_updates_and_preferences_survive_restart(qtbot, tmp_path: Path) -> None:
    paths = AppPaths(tmp_path / "app")
    runtime = create_runtime(paths, library_only=True)
    try:
        preferences = runtime.reader.preferences
        root = runtime.engine.rootObjects()[0]
        assert root.property("color").name() == "#24211f"
        preferences.toggleTheme()
        preferences.setFontSize(26)
        qtbot.waitUntil(lambda: root.property("color").name() == "#edede9", timeout=2000)
    finally:
        runtime.dispose()
    restored = create_runtime(paths, library_only=True)
    try:
        assert restored.reader.preferences.dark is False
        assert restored.reader.preferences.fontSize == 26
    finally:
        restored.dispose()


@pytest.mark.gui
def test_native_resource_loader_confines_images_and_blocks_remote(qtbot, tmp_path: Path) -> None:
    from tests.fixtures.epub_factory import cover_png

    (tmp_path / "cover.png").write_bytes(cover_png())
    document = PublicationDocument(tmp_path, "chapter.xhtml", QSize(300, 400))
    good = document.loadResource(
        QTextDocument.ResourceType.ImageResource, QUrl("epub://publication/cover.png")
    )
    assert isinstance(good, QImage) and not good.isNull()
    for url in (
        "file:///etc/passwd",
        "https://example.org/image.png",
        "epub://publication/../private.png",
    ):
        denied = document.loadResource(QTextDocument.ResourceType.ImageResource, QUrl(url))
        assert not isinstance(denied, QImage) or denied.isNull()


@pytest.mark.gui
def test_oversized_cover_fits_one_native_page(qtbot, repository, tmp_path: Path) -> None:
    from tests.fixtures.epub_factory import make_epub

    cover = b"""<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Cover</title></head>
<body><p><img src="cover.png" width="2000" height="4000" alt="Cover"/></p></body></html>"""
    epub = make_epub(tmp_path / "cover.epub", extra={"EPUB/chapter1.xhtml": cover})
    book = EpubImportService(repository, tmp_path / "books").import_book(epub)
    engine = NativeBookEngine()
    engine.open(book)
    assert engine.pages == 1
    engine.next()
    assert engine.chapter_index == 1

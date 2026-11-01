from pathlib import Path

import pytest
from PySide6.QtCore import QObject

from epub_reader.bootstrap import create_runtime
from epub_reader.core.paths import AppPaths
from epub_reader.rendering.engine import NativeBookEngine
from epub_reader.services.epub_import_service import EpubImportService
from tests.fixtures.navigation_factory import make_navigation_epub


@pytest.mark.gui
@pytest.mark.parametrize("declared", [True, False])
def test_figures_jump_to_native_image_anchors(qtbot, tmp_path: Path, declared: bool) -> None:
    runtime = create_runtime(AppPaths(tmp_path / "app"))
    try:
        source = make_navigation_epub(tmp_path / "book.epub", declared_figures=declared)
        book = runtime.library.importer.import_book(source)
        runtime.reader.openBook(book.id)
        qtbot.waitUntil(lambda: not runtime.reader.figuresLoading, timeout=5000)
        assert runtime.reader.figureCount == 2
        runtime.reader.setNavigationSection("figures")
        row = runtime.reader.navigationRows[0]
        runtime.reader.navigate(row["href"])
        engine = runtime.reader.engine
        assert engine.anchor_offset > 0
        assert engine.page > 0
        assert "epubify-image-1" in engine.anchors
        assert "illustration" in engine.anchors
        assert runtime.reader.navigationRows[0]["active"]
        runtime.reader.navigate(runtime.reader.navigationRows[1]["href"])
        assert engine.chapter_index == 1
    finally:
        runtime.dispose()


@pytest.mark.gui
def test_nested_outline_collapses_searches_and_follows_current_section(
    qtbot, tmp_path: Path
) -> None:
    runtime = create_runtime(AppPaths(tmp_path / "app"))
    try:
        book = runtime.library.importer.import_book(make_navigation_epub(tmp_path / "book.epub"))
        runtime.reader.openBook(book.id)
        root = runtime.engine.rootObjects()[0]
        qtbot.waitUntil(lambda: root.findChild(QObject, "navigationList") is not None)
        assert [r["depth"] for r in runtime.reader.navigationRows] == [0, 1, 2, 0, 1]
        runtime.reader.toggleOutline(0)
        assert len(runtime.reader.navigationRows) == 3
        runtime.reader.setNavigationQuery("morning")
        assert [r["nodeId"] for r in runtime.reader.navigationRows] == [0, 1, 2]
        runtime.reader.navigate("EPUB/chapter1.xhtml#p10")
        assert runtime.reader.navigationRows[-1]["active"]
        assert root.findChild(QObject, "navigationSearch").property("text") == "morning"
    finally:
        runtime.dispose()


@pytest.mark.gui
def test_native_links_are_underlined_and_hit_testable(qtbot, repository, tmp_path: Path) -> None:
    source = make_navigation_epub(tmp_path / "book.epub")
    book = EpubImportService(repository, tmp_path / "books").import_book(source)
    engine = NativeBookEngine()
    engine.configure(20, False, "paper")
    engine.open(book)
    cursor = engine.document.find("Go to Working with images")
    assert not cursor.isNull()
    assert cursor.charFormat().fontUnderline()
    assert cursor.charFormat().anchorHref() == "chapter2.xhtml#p12"
    assert cursor.charFormat().foreground().color().name() == "#715443"
    block = cursor.block()
    line = block.layout().lineForTextPosition(cursor.selectionStart() - block.position())
    x = line.cursorToX(cursor.selectionStart() - block.position())[0]
    bounds = engine.document.documentLayout().blockBoundingRect(block)
    assert (
        engine.link_at(
            (engine.width - engine.text_width) / 2 + x + 2,
            32 + bounds.top() + line.y() + line.height() / 2,
        )
        == "chapter2.xhtml#p12"
    )


@pytest.mark.gui
def test_clickable_qml_navigation_and_reading_surfaces(qtbot, tmp_path: Path) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    runtime = create_runtime(AppPaths(tmp_path / "app"))
    try:
        book = runtime.library.importer.import_book(make_navigation_epub(tmp_path / "book.epub"))
        runtime.reader.openBook(book.id)
        root = runtime.engine.rootObjects()[0]
        qtbot.waitUntil(lambda: root.findChild(QObject, "appearanceButton") is not None)
        qtbot.wait(300)  # Wait for native screen and viewport transitions before hit testing.

        def click(name: str) -> None:
            # View delegates have visual parents without QObject ownership parents.
            pending = [root.contentItem()]
            while pending:
                item = pending.pop()
                if item.objectName() == name:
                    point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
                    QTest.mouseClick(root, Qt.MouseButton.LeftButton, pos=point)
                    return
                pending.extend(item.childItems())
            raise AssertionError(f"Missing visual item: {name}")

        click("navigation-toggle-0")
        qtbot.waitUntil(lambda: len(runtime.reader.navigationRows) == 3)
        click("navigation-toggle-0")
        qtbot.waitUntil(lambda: len(runtime.reader.navigationRows) == 5)
        click("navigation-entry-4")
        qtbot.waitUntil(lambda: runtime.reader.engine.chapter_index == 1)
        assert root.findChild(QObject, "navigationSidebar").width() > 0
        location = runtime.reader.engine.location
        click("appearanceButton")
        popup = root.findChild(QObject, "readingAppearance")
        qtbot.waitUntil(lambda: popup.property("opened"))
        click("surface-grid")
        qtbot.waitUntil(lambda: runtime.reader.preferences.readingSurface == "grid")
        assert runtime.reader.engine.location == location
        click("appearanceButton")
        qtbot.waitUntil(lambda: not popup.property("opened"))
        click("appearanceButton")
        qtbot.waitUntil(lambda: popup.property("opened"))
        QTest.keyClick(root, Qt.Key.Key_Escape)
        qtbot.waitUntil(lambda: not popup.property("opened"))
        assert runtime.reader.active
        click("figuresTab")
        qtbot.waitUntil(lambda: runtime.reader.navigationSection == "figures")
        click("navigation-entry-0")
        qtbot.waitUntil(lambda: runtime.reader.engine.chapter_index == 0)
        assert runtime.reader.engine.anchor_offset > 0
    finally:
        runtime.dispose()


@pytest.mark.gui
def test_isolated_image_anchors_point_to_image_instead_of_following_paragraph(
    qtbot, repository, tmp_path: Path
) -> None:
    from tests.fixtures.epub_factory import make_epub

    chapter = b"""<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Images</title></head>
<body><p>Before the image</p><p id="figure-one"><img id="photo" src="cover.png"/></p>
<p>After the image</p><p><img src="cover.png"/></p><p>End</p></body></html>"""
    source = make_epub(tmp_path / "images.epub", extra={"EPUB/chapter1.xhtml": chapter})
    book = EpubImportService(repository, tmp_path / "books").import_book(source)
    engine = NativeBookEngine()
    engine.open(book)
    positions = []
    block = engine.document.begin()
    while block.isValid():
        fragments = block.begin()
        while not fragments.atEnd():
            fragment = fragments.fragment()
            if fragment.charFormat().isImageFormat():
                positions.append(fragment.position())
            fragments += 1
        block = block.next()
    assert len(positions) == 2
    assert engine.anchors["epubify-image-1"] == positions[0]
    assert engine.anchors["epubify-image-2"] == positions[1]
    assert engine.anchors["photo"] == positions[0]
    assert engine.anchors["figure-one"] == positions[0]
    engine.navigate("#figure-one")
    assert engine.anchor_offset == positions[0]

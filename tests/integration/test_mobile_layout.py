from pathlib import Path

import pytest
from PySide6.QtCore import QMetaObject, QObject, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from epub_reader.bootstrap import create_runtime
from epub_reader.core.paths import AppPaths
from epub_reader.presentation.native_page import BookPage
from epub_reader.rendering.engine import NativeBookEngine
from tests.fixtures.epub_factory import make_epub


def click(window, item: QQuickItem) -> None:
    position = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=position.toPoint())


def inside(window, item: QQuickItem) -> None:
    point = item.mapToScene(QPointF())
    assert point.x() >= -1 and point.y() >= -1
    assert point.x() + item.width() <= window.width() + 1
    assert point.y() + item.height() <= window.height() + 1


@pytest.mark.gui
@pytest.mark.parametrize("direction", [1, -1])
def test_higher_pages_slide_over_stationary_earlier_pages(qtbot, direction: int) -> None:
    page = BookPage()
    page.setWidth(200)
    page.setHeight(300)
    renderer = NativeBookEngine()
    first, second = ("red", "blue") if direction > 0 else ("blue", "red")

    def solid(color):
        image = QImage(200, 300, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        if color in ("red", "blue"):
            painter = QPainter(image)
            painter.fillRect(0, 0, 12, 300, QColor("yellow" if color == "red" else "green"))
            painter.end()
        return image

    renderer.image = solid(first)
    page.set_renderer(renderer)
    page.prepareTurn(direction)
    renderer.image = solid(second)

    def frame(progress):
        page.set_slide_progress(progress)
        output = solid("black")
        painter = QPainter(output)
        page.paint(painter)
        painter.end()
        return output

    assert frame(0).pixelColor(100, 150) == QColor(first)
    middle = frame(0.5)
    assert middle.pixelColor(20, 150) == QColor("red")
    assert middle.pixelColor(180, 150) == QColor("blue")
    # Distinct left-edge markers distinguish which sheet actually moves.
    # Solid page colors alone cannot detect an inverted stack.
    for progress in (0.25, 0.5, 0.75):
        intermediate = frame(progress)
        edge = round(200 * (1 - progress if direction > 0 else progress))
        assert intermediate.pixelColor(5, 150) == QColor("yellow")
        assert intermediate.pixelColor(edge + 5, 150) == QColor("green")
    assert frame(1).pixelColor(100, 150) == QColor(second)
    page.finishTurn()
    assert page.get_slide_progress() == 1
    page.set_renderer(None)


@pytest.mark.gui
def test_reduced_motion_and_first_page_do_not_animate(qtbot, tmp_path: Path) -> None:
    runtime = create_runtime(AppPaths(tmp_path / "data"), preview_size=(411, 914))
    try:
        book = runtime.library.importer.import_book(make_epub(tmp_path / "book.epub"))
        runtime.reader.openBook(book.id)
        root = runtime.engine.rootObjects()[0]
        qtbot.waitUntil(lambda: root.findChild(QQuickItem, "nativeBookPage") is not None)
        page = root.findChild(QQuickItem, "nativeBookPage")
        qtbot.wait(150)
        runtime.reader.previous()
        assert page.property("slideProgress") == 1
        runtime.reader.next()
        qtbot.waitUntil(lambda: 0 < page.property("slideProgress") < 1)
        qtbot.waitUntil(lambda: page.property("slideProgress") == 1)
        runtime.reader.preferences.toggleReducedMotion()
        runtime.reader.previous()
        assert page.property("slideProgress") == 1
    finally:
        runtime.dispose()


@pytest.mark.gui
@pytest.mark.parametrize("size", [(320, 640), (411, 914), (480, 800), (914, 411)])
def test_library_fits_phone_and_drawer_selection_closes(qtbot, tmp_path: Path, size) -> None:
    runtime = create_runtime(AppPaths(tmp_path / "data"), preview_size=size)
    try:
        root = runtime.engine.rootObjects()[0]
        qtbot.wait(50)
        assert (root.width(), root.height()) == size
        for name in ("importEpubButton", "librarySearch", "bookGrid"):
            inside(root, root.findChild(QQuickItem, name))
        if root.property("compactLayout"):
            assert not root.findChild(QQuickItem, "desktopLibrarySidebar").isVisible()
            menu = root.findChild(QQuickItem, "libraryMenuButton")
            assert menu.width() >= 48 and menu.height() >= 48
            click(root, menu)
            drawer = root.findChild(QObject, "libraryDrawer")
            qtbot.waitUntil(lambda: drawer.property("opened"))
            content = drawer.property("contentItem")
            click(root, content.findChild(QQuickItem, "favoritesButton"))
            qtbot.waitUntil(lambda: not drawer.property("visible"))
            assert runtime.library.favoritesOnly
        assert not root.grabWindow().isNull()
    finally:
        runtime.dispose()


@pytest.mark.gui
def test_phone_reader_swipe_drawer_and_settings_keep_page_usable(qtbot, tmp_path: Path) -> None:
    runtime = create_runtime(AppPaths(tmp_path / "data"), preview_size=(411, 914))
    try:
        book = runtime.library.importer.import_book(make_epub(tmp_path / "book.epub"))
        runtime.reader.openBook(book.id)
        root = runtime.engine.rootObjects()[0]
        qtbot.waitUntil(lambda: root.findChild(QQuickItem, "nativeBookPage") is not None)
        page = root.findChild(QQuickItem, "nativeBookPage")
        qtbot.waitUntil(lambda: runtime.reader.engine.width == round(page.width()))
        assert page.width() == root.width()
        inside(root, root.findChild(QQuickItem, "readerContentsButton"))
        inside(root, root.findChild(QQuickItem, "readerMoreButton"))
        start = page.mapToScene(QPointF(320, 200)).toPoint()
        end = page.mapToScene(QPointF(80, 200)).toPoint()
        QTest.mousePress(root, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(root, end)
        QTest.mouseRelease(root, Qt.MouseButton.LeftButton, pos=end)
        qtbot.waitUntil(lambda: runtime.reader.engine.page == 1)
        location = runtime.reader.engine.location
        click(root, root.findChild(QQuickItem, "readerContentsButton"))
        drawer = root.findChild(QObject, "readerContentsDrawer")
        qtbot.waitUntil(lambda: drawer.property("opened"))
        assert page.width() == root.width()  # Drawer overlays rather than squeezing the text.
        QTest.keyClick(root, Qt.Key.Key_Escape)
        qtbot.waitUntil(lambda: not drawer.property("visible"))
        assert runtime.reader.active
        click(root, root.findChild(QQuickItem, "readerContentsButton"))
        qtbot.waitUntil(lambda: drawer.property("opened"))
        pending = [drawer.property("contentItem")]
        target = None
        while pending:
            item = pending.pop()
            if item.objectName() == "navigation-entry-1":
                target = item
                break
            pending.extend(item.childItems())
        assert target is not None
        click(root, target)
        qtbot.waitUntil(lambda: runtime.reader.engine.chapter_index == 1)
        qtbot.waitUntil(lambda: not drawer.property("visible"))
        location = runtime.reader.engine.location
        appearance = root.findChild(QObject, "readingAppearance")
        QMetaObject.invokeMethod(appearance, "open")
        qtbot.waitUntil(lambda: appearance.property("opened"))
        assert appearance.property("width") <= root.width() - 24
        click(root, root.findChild(QQuickItem, "mobileFontIncrease"))
        assert runtime.reader.engine.location == location
        QMetaObject.invokeMethod(appearance, "close")
        # Reflow in landscape, then ensure the scrollable popup stays inside the window.
        root.resize(914, 411)
        qtbot.wait(100)
        QMetaObject.invokeMethod(appearance, "open")
        qtbot.waitUntil(lambda: appearance.property("opened"))
        assert appearance.property("height") <= root.height() - 32
        assert not root.grabWindow().isNull()
    finally:
        runtime.dispose()

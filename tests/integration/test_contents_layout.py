from pathlib import Path

import pytest
from PySide6.QtGui import QFont, QTextFormat

from epub_reader.rendering.engine import NativeBookEngine
from epub_reader.services.epub_import_service import EpubImportService
from tests.fixtures.contents_factory import make_contents_epub


@pytest.mark.gui
@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("font_size", [17, 26])
def test_visible_contents_are_compact_and_follow_canonical_depths(
    qtbot, repository, tmp_path: Path, nested: bool, font_size: int
) -> None:
    source = make_contents_epub(tmp_path / "book.epub", nested=nested)
    book = EpubImportService(repository, tmp_path / "books").import_book(source)
    engine = NativeBookEngine()
    engine.configure(font_size, True)
    engine.open(book)
    for label, depth in (
        ("Chapter One", 0),
        ("Finding a quiet place", 1),
        ("A garden for reading", 2),
    ):
        cursor = engine.document.find(label)
        assert not cursor.isNull()
        block = cursor.block()
        fmt = block.blockFormat()
        assert fmt.leftMargin() == pytest.approx(depth * font_size * 1.25)
        assert fmt.indent() == 0
        assert block.textList() is None
        assert fmt.topMargin() <= font_size * 0.6
        assert fmt.bottomMargin() <= font_size * 0.2
        assert fmt.lineHeight() == 125
        assert cursor.charFormat().fontPointSize() == font_size * 0.75
        assert cursor.charFormat().font().pointSizeF() == font_size * 0.75
        assert not cursor.charFormat().hasProperty(QTextFormat.Property.FontSizeAdjustment)
        assert not cursor.charFormat().hasProperty(QTextFormat.Property.FontPixelSize)
        if depth > 0:
            assert cursor.charFormat().fontWeight() == QFont.Weight.Normal
        assert cursor.charFormat().fontUnderline()
    cursor = engine.document.find("A garden for reading")
    block = cursor.block()
    line = block.layout().lineForTextPosition(cursor.selectionStart() - block.position())
    bounds = engine.document.documentLayout().blockBoundingRect(block)
    href = engine.link_at(
        (engine.width - engine.text_width) / 2
        + bounds.left()
        + line.cursorToX(cursor.selectionStart() - block.position())[0]
        + 2,
        32 + bounds.top() + line.y() + line.height() / 2,
    )
    assert href == "chapter2.xhtml#detail"
    engine.navigate(href)
    assert engine.chapter_index == 1
    assert engine.anchor_offset == engine.anchors["detail"]
    prose = engine.document.find("The garden changes")
    assert prose.blockFormat().lineHeight() == 165
    assert prose.blockFormat().leftMargin() == 0


@pytest.mark.gui
@pytest.mark.parametrize("nested", [False, True])
def test_navigation_layout_preserves_plain_text_and_existing_offsets(
    qtbot, repository, tmp_path: Path, monkeypatch, nested: bool
) -> None:
    import epub_reader.rendering.document as document_module

    source = make_contents_epub(tmp_path / "book.epub", nested=nested)
    book = EpubImportService(repository, tmp_path / "books").import_book(source)
    layout = document_module.prepare_navigation
    monkeypatch.setattr(document_module, "prepare_navigation", lambda *args: {})
    before = NativeBookEngine()
    before.open(book)
    text = before.document.toPlainText()
    anchors = before.anchors.copy()
    before.navigate("#section-link")
    location = before.location
    monkeypatch.setattr(document_module, "prepare_navigation", layout)
    after = NativeBookEngine()
    after.open(book)
    assert after.document.toPlainText() == text
    assert {k: after.anchors[k] for k in anchors} == anchors
    after.navigate("#section-link")
    assert after.location == location
    assert after.document.find("Finding a quiet place").blockFormat().leftMargin() > 0


@pytest.mark.gui
def test_ordinary_linked_headings_keep_normal_reading_layout(
    qtbot, repository, tmp_path: Path
) -> None:
    source = make_contents_epub(tmp_path / "book.epub", semantic=False)
    book = EpubImportService(repository, tmp_path / "books").import_book(source)
    engine = NativeBookEngine()
    engine.open(book)
    heading = engine.document.find("Finding a quiet place")
    assert heading.blockFormat().lineHeight() == 165
    assert heading.blockFormat().leftMargin() == 0
    assert heading.blockFormat().topMargin() == 45
    assert heading.charFormat().fontPointSize() > engine.font_size * 0.75

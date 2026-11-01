from pathlib import Path

import pytest

from epub_reader.infrastructure.epub.extraction import extract_archive
from epub_reader.presentation.models.navigation import navigation_rows
from epub_reader.rendering.publication import load_publication, scan_figures
from tests.fixtures.navigation_factory import make_navigation_epub


@pytest.mark.parametrize("version", [2, 3])
def test_navigation_preserves_nested_order_and_parents(tmp_path: Path, version: int) -> None:
    source = make_navigation_epub(tmp_path / "navigation.epub", version=version)
    root = tmp_path / "book"
    extract_archive(source, root)
    publication = load_publication(root, "EPUB/book.opf")
    assert [e.depth for e in publication.contents] == [0, 1, 2, 0, 1]
    assert [e.parent for e in publication.contents] == [-1, 0, 1, -1, 3]
    assert publication.contents[2].href == "EPUB/chapter1.xhtml#p10"
    entries = list(publication.contents)
    assert len(navigation_rows(entries, {0}, "", 2)) == 3
    rows = navigation_rows(entries, {0}, "morning", 2)
    assert [row["nodeId"] for row in rows] == [0, 1, 2]
    assert rows[2]["active"]
    assert rows[0]["inActivePath"]
    assert rows[0]["expanded"]
    assert navigation_rows(entries, set(), "missing", -1) == []


def test_declared_illustration_navigation_is_read(tmp_path: Path) -> None:
    source = make_navigation_epub(tmp_path / "navigation.epub")
    root = tmp_path / "book"
    extract_archive(source, root)
    publication = load_publication(root, "EPUB/book.opf")
    assert len(publication.figures) == 2
    assert publication.figures[0].href == "EPUB/chapter1.xhtml#figure-a"
    assert "reading garden" in publication.figures[0].label


def test_fallback_figures_use_captions_and_stable_image_anchors(tmp_path: Path) -> None:
    source = make_navigation_epub(tmp_path / "navigation.epub", declared_figures=False)
    root = tmp_path / "book"
    extract_archive(source, root)
    publication = load_publication(root, "EPUB/book.opf")
    assert not publication.figures
    figures = scan_figures(publication)
    assert len(figures) == 2  # Decorative alt="" images are excluded.
    assert figures[0].label == "Figure 1 — The reading garden"
    assert figures[0].href == "EPUB/chapter1.xhtml#epubify-image-1"


def test_multiple_illustration_lists_are_combined(tmp_path: Path) -> None:
    source = make_navigation_epub(tmp_path / "navigation.epub")
    root = tmp_path / "book"
    extract_archive(source, root)
    nav = root / "EPUB/nav.xhtml"
    content = nav.read_text().replace(
        "</ol></nav></body>",
        '</ol></nav><nav epub:type="loi"><ol>'
        '<li><a href="chapter2.xhtml#illustration">Another illustration</a></li>'
        "</ol></nav></body>",
    )
    nav.write_text(content)
    publication = load_publication(root, "EPUB/book.opf")
    assert len(publication.figures) == 3
    assert publication.figures[-1].label == "Another illustration"
    assert len(publication.contents) == 5

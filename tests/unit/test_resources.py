from pathlib import Path

import pytest

from epub_reader.infrastructure.epub.extraction import EpubError, contained_resource


def test_resource_is_confined_to_book(tmp_path: Path) -> None:
    book = tmp_path / "book"
    book.mkdir()
    chapter = book / "chapter.xhtml"
    chapter.write_text("<html/>")
    assert contained_resource(book, "chapter.xhtml") == chapter
    with pytest.raises(EpubError):
        contained_resource(book, "../private.txt")
    with pytest.raises(EpubError):
        contained_resource(book, "/etc/passwd")
    with pytest.raises(EpubError):
        contained_resource(book, "missing.xhtml")


def test_resource_symlink_cannot_escape(tmp_path: Path) -> None:
    root = tmp_path / "book"
    root.mkdir()
    secret = tmp_path / "private.txt"
    secret.write_text("private")
    try:
        (root / "resource").symlink_to(secret)
    except OSError:
        pytest.skip("Symlink creation is unavailable for this user")
    with pytest.raises(EpubError):
        contained_resource(root, "resource")

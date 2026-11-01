from pathlib import Path

import pytest

from epub_reader.infrastructure.epub.extraction import EpubError, extract_archive
from epub_reader.infrastructure.epub.parser import parse_metadata, sanitize_documents
from tests.fixtures.epub_factory import make_epub


@pytest.mark.parametrize("version", [2, 3])
def test_metadata_and_cover_for_epub2_and_epub3(tmp_path: Path, version: int) -> None:
    archive = make_epub(tmp_path / "book.epub", version=version)
    root = tmp_path / "content"
    extract_archive(archive, root)
    metadata = parse_metadata(root)
    assert metadata.title == "The Quiet Library"
    assert metadata.author == "Epubify Contributors"
    assert metadata.cover == "EPUB/cover.png"
    assert metadata.package_path == "EPUB/book.opf"


def test_active_content_removed_but_text_and_images_survive(tmp_path: Path) -> None:
    archive = make_epub(tmp_path / "active.epub", active_content=True)
    root = tmp_path / "content"
    extract_archive(archive, root)
    sanitize_documents(root)
    content = (root / "EPUB/chapter1.xhtml").read_text()
    assert "<script" not in content
    assert "onerror" not in content
    assert "A quiet room" in content
    assert "cover.png" in content


def test_xml_external_entities_are_rejected(epub: Path, tmp_path: Path) -> None:
    root = tmp_path / "content"
    extract_archive(epub, root)
    (root / "META-INF/container.xml").write_text(
        """<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>"""
    )
    with pytest.raises(EpubError, match="malformed"):
        parse_metadata(root)


def test_missing_spine_is_rejected(epub: Path, tmp_path: Path) -> None:
    root = tmp_path / "content"
    extract_archive(epub, root)
    package = root / "EPUB/book.opf"
    package.write_text(package.read_text().replace('idref="c1"', 'idref="missing"'))
    with pytest.raises(EpubError, match="missing manifest"):
        parse_metadata(root)


def test_encrypted_publications_have_clear_error(epub: Path, tmp_path: Path) -> None:
    root = tmp_path / "content"
    extract_archive(epub, root)
    (root / "META-INF/encryption.xml").write_text("<encryption/>")
    with pytest.raises(EpubError, match="Encrypted"):
        parse_metadata(root)


def test_harmless_epub2_doctype_is_supported(epub: Path, tmp_path: Path) -> None:
    root = tmp_path / "content"
    extract_archive(epub, root)
    chapter = root / "EPUB/chapter1.xhtml"
    chapter.write_text(
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" '
        '"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">' + chapter.read_text()
    )
    sanitize_documents(root)
    assert "A quiet room" in chapter.read_text()

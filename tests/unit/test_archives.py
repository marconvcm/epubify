import stat
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from epub_reader.infrastructure.epub.extraction import (
    ArchiveLimits,
    EpubError,
    extract_archive,
    resolve_reference,
    safe_relative_path,
)
from tests.fixtures.epub_factory import make_epub


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/tmp/escape",
        "C:/escape",
        "a\\escape",
        "a/../b",
        "a//b",
        "./a",
        "NUL.txt",
        "dir/COM1",
        "dir/a.",
        "dir/a ",
        "a\x00b",
    ],
)
def test_rejects_nonportable_and_traversal_paths(name: str) -> None:
    with pytest.raises(EpubError):
        safe_relative_path(name)


@pytest.mark.parametrize("name", ["../outside.txt", "/outside.txt", "a\\b", "C:/outside"])
def test_zip_traversal_cannot_write_outside_staging(tmp_path: Path, name: str) -> None:
    epub = make_epub(tmp_path / "bad.epub", extra={name: b"unsafe"})
    with pytest.raises(EpubError):
        extract_archive(epub, tmp_path / "content")
    assert not (tmp_path / "content").exists()
    assert not (tmp_path / "outside.txt").exists()


def test_rejects_symlinks(tmp_path: Path) -> None:
    path = make_epub(tmp_path / "link.epub")
    info = ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(path, "a") as archive:
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(EpubError, match="Links"):
        extract_archive(path, tmp_path / "content")


def test_rejects_bombs_before_extracting(tmp_path: Path) -> None:
    path = tmp_path / "bomb.epub"
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", b"application/epub+zip")
        archive.writestr("large", b"0" * 1_000_000)
    with pytest.raises(EpubError, match="decompression"):
        extract_archive(path, tmp_path / "content", ArchiveLimits(ratio=20))
    assert not (tmp_path / "content").exists()


def test_member_count_limit(epub: Path, tmp_path: Path) -> None:
    with pytest.raises(EpubError, match="too many"):
        extract_archive(epub, tmp_path / "content", ArchiveLimits(members=2))


def test_case_collisions_are_rejected(tmp_path: Path) -> None:
    path = make_epub(tmp_path / "collision.epub", extra={"EPUB/COVER.png": b"duplicate"})
    with pytest.raises(EpubError, match="duplicate"):
        extract_archive(path, tmp_path / "content")


@pytest.mark.parametrize(
    "href",
    [
        "../../outside",
        "file:///etc/passwd",
        "https://example.org/a",
        "%2e%2e/%2e%2e/private",
        "/absolute",
    ],
)
def test_metadata_references_cannot_escape(href: str) -> None:
    with pytest.raises(EpubError):
        resolve_reference("EPUB/book.opf", href)


def test_parent_reference_within_publication_is_valid() -> None:
    assert resolve_reference("EPUB/package/book.opf", "../cover.png#image") == "EPUB/cover.png"


def test_invalid_zip_is_a_user_facing_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.epub"
    path.write_bytes(b"this is not a zip")
    with pytest.raises(EpubError, match="damaged"):
        extract_archive(path, tmp_path / "content")

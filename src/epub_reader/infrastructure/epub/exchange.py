"""Portable publication identities and bounded archives for device exchange."""

import hashlib
import os
import zipfile
from pathlib import Path

from epub_reader.infrastructure.epub.extraction import ArchiveLimits, EpubError, safe_relative_path


def publication_files(root: Path) -> list[Path]:
    resolved = root.resolve()
    files: list[Path] = []
    total = 0
    limits = ArchiveLimits()
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.resolve().is_relative_to(resolved):
            raise EpubError("Publication exchange cannot include links outside the book.")
        if not path.is_file():
            continue
        safe_relative_path(path.relative_to(root).as_posix())
        size = path.stat().st_size
        total += size
        if (
            size > limits.member_bytes
            or total > limits.expanded_bytes
            or len(files) >= limits.members
        ):
            raise EpubError("The publication exceeds exchange limits.")
        files.append(path)
    return files


def content_id(root: Path) -> str:
    digest = hashlib.sha256()
    for path in publication_files(root):
        name = path.relative_to(root).as_posix().encode()
        digest.update(len(name).to_bytes(4, "big") + name + path.stat().st_size.to_bytes(8, "big"))
        with path.open("rb") as stream:
            while chunk := stream.read(65536):
                digest.update(chunk)
    return digest.hexdigest()


def export_publication(root: Path, target: Path) -> tuple[int, str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    files = publication_files(root)
    temporary = target.with_suffix(".part")
    stored: set[str] = {"mimetype"}
    try:
        for _ in range(2):
            with zipfile.ZipFile(temporary, "w") as archive:
                for path in sorted(
                    files, key=lambda p: (p.name != "mimetype", p.relative_to(root).as_posix())
                ):
                    name = path.relative_to(root).as_posix()
                    info = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
                    info.compress_type = (
                        zipfile.ZIP_STORED if name in stored else zipfile.ZIP_DEFLATED
                    )
                    info.external_attr = 0o100644 << 16
                    with path.open("rb") as incoming, archive.open(info, "w") as outgoing:
                        while chunk := incoming.read(65536):
                            outgoing.write(chunk)
            with zipfile.ZipFile(temporary) as archive:
                offenders = {
                    item.filename
                    for item in archive.infolist()
                    if item.file_size > max(1, item.compress_size) * ArchiveLimits().ratio
                }
            if not offenders:
                break
            stored.update(offenders)
        size = temporary.stat().st_size
        if size > ArchiveLimits().compressed_bytes:
            raise EpubError("The book exceeds the synchronization transfer limit.")
        digest = hashlib.sha256()
        with temporary.open("rb") as stream:
            while chunk := stream.read(65536):
                digest.update(chunk)
        temporary.replace(target)
        if os.name != "nt":
            target.chmod(0o600)
        return size, digest.hexdigest()
    finally:
        temporary.unlink(missing_ok=True)

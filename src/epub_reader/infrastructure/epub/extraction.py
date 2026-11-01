"""Bounded extraction into a new, application-owned directory."""

import re
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


class EpubError(ValueError):
    """An invalid, unsupported, or unsafe publication."""


@dataclass(frozen=True)
class ArchiveLimits:
    compressed_bytes: int = 128 * 1024 * 1024
    expanded_bytes: int = 300 * 1024 * 1024
    member_bytes: int = 32 * 1024 * 1024
    members: int = 10_000
    ratio: int = 500


def safe_relative_path(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\x00" in name or ":" in name or name.startswith("/"):
        raise EpubError("The EPUB contains an unsafe resource path.")
    # Check raw components: PurePath normalizes away '.' and repeated separators.
    parts = name.rstrip("/").split("/")
    reserved = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)
    if any(
        p in ("", ".", "..")
        or p.endswith((".", " "))
        or reserved.match(p)
        or any(ord(c) < 32 for c in p)
        for p in parts
    ):
        raise EpubError("The EPUB contains a nonportable or unsafe resource path.")
    return PurePosixPath(*parts)


def resolve_reference(base: str, href: str) -> str:
    url = urlsplit(href)
    if url.scheme or url.netloc or not url.path or "\\" in url.path:
        raise EpubError("The EPUB references an unsupported resource.")
    # Legitimate relative '../' references may stay inside the publication.
    parts = list(PurePosixPath(base).parent.parts)
    for part in unquote(url.path).split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise EpubError("A resource reference escapes the publication.")
            parts.pop()
        else:
            parts.append(part)
    if url.path.startswith("/"):
        raise EpubError("Absolute resource paths are unsupported.")
    return str(safe_relative_path("/".join(parts)))


def contained_resource(root: Path, name: str) -> Path:
    relative = safe_relative_path(name)
    target = root.joinpath(*relative.parts).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise EpubError("Resource is outside the active publication or does not exist.")
    return target


DEFAULT_LIMITS = ArchiveLimits()


def extract_archive(
    source: Path, destination: Path, limits: ArchiveLimits = DEFAULT_LIMITS
) -> None:
    if source.stat().st_size > limits.compressed_bytes:
        raise EpubError("The EPUB exceeds the 128 MiB import limit.")
    try:
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > limits.members:
                raise EpubError("The EPUB contains too many resources.")
            seen: set[str] = set()
            total = 0
            for entry in entries:
                path = safe_relative_path(entry.filename)
                key = str(path).casefold()
                if key in seen:
                    raise EpubError("The EPUB contains duplicate resource paths.")
                seen.add(key)
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise EpubError("Links and special files are not allowed in EPUB archives.")
                if entry.flag_bits & 1:
                    raise EpubError("Encrypted ZIP archives are not supported.")
                total += entry.file_size
                if (
                    total > limits.expanded_bytes
                    or entry.file_size > limits.member_bytes
                    or entry.file_size > max(1, entry.compress_size) * limits.ratio
                ):
                    raise EpubError("The EPUB exceeds safe decompression limits.")
            try:
                if archive.read("mimetype") != b"application/epub+zip":
                    raise EpubError("This ZIP archive is not an EPUB publication.")
            except KeyError as exc:
                raise EpubError("The EPUB has no mimetype declaration.") from exc
            destination.mkdir(parents=True, exist_ok=False)
            for entry in entries:
                target = destination.joinpath(*safe_relative_path(entry.filename).parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                # ZipExtFile verifies CRC and limits output to the declared size.
                with archive.open(entry) as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, length=64 * 1024)
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError) as exc:
        shutil.rmtree(destination, ignore_errors=True)
        raise EpubError("The EPUB archive is damaged or uses unsupported compression.") from exc

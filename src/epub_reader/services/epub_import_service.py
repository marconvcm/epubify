import hashlib
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from epub_reader.domain.models.book import Book
from epub_reader.domain.repositories.book_repository import BookRepository
from epub_reader.infrastructure.epub.exchange import content_id
from epub_reader.infrastructure.epub.extraction import ArchiveLimits, EpubError, extract_archive
from epub_reader.infrastructure.epub.parser import parse_metadata, sanitize_documents
from epub_reader.services.classification_service import CLASSIFICATION_VERSION, classify


class EpubImportService:
    def __init__(self, repository: BookRepository, storage: Path) -> None:
        self.repository, self.storage = repository, storage
        self.storage.mkdir(parents=True, exist_ok=True)

    def import_book(self, source: Path, *, expected_content_id: str | None = None) -> Book:
        if source.suffix.lower() != ".epub" or not source.is_file():
            raise EpubError("Choose an existing .epub file.")
        limit = ArchiveLimits().compressed_bytes
        # Snapshot and hash the exact same bytes, so source changes cannot bypass deduplication.
        with tempfile.TemporaryDirectory(prefix=".import-", dir=self.storage) as staging:
            stage = Path(staging)
            snapshot = stage / "original.epub"
            digest = hashlib.sha256()
            total = 0
            with source.open("rb") as incoming, snapshot.open("xb") as outgoing:
                while chunk := incoming.read(64 * 1024):
                    total += len(chunk)
                    if total > limit:
                        raise EpubError("The EPUB exceeds the 128 MiB import limit.")
                    digest.update(chunk)
                    outgoing.write(chunk)
            book_id = digest.hexdigest()
            existing = self.repository.get(book_id)
            if existing and (existing.storage_path / existing.package_path).is_file():
                if expected_content_id and content_id(existing.storage_path) != expected_content_id:
                    raise EpubError("The received book does not match its content identity.")
                return existing
            content = stage / "content"
            extract_archive(snapshot, content)
            metadata = parse_metadata(content)
            sanitize_documents(content)
            if expected_content_id and content_id(content) != expected_content_id:
                raise EpubError("The received book does not match its content identity.")
            destination = self.storage / book_id
            if destination.exists():
                shutil.rmtree(destination)
            content.replace(destination)
            cover = destination / metadata.cover if metadata.cover else None
            # QML only uses raster cover images; untrusted SVG never reaches its image provider.
            if cover and cover.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                cover = None
            book = Book(
                book_id,
                metadata.title,
                metadata.author,
                destination,
                metadata.package_path,
                datetime.now(UTC),
                cover,
                categories=classify(metadata),
                classification_version=CLASSIFICATION_VERSION,
            )
            try:
                return self.repository.add(book)
            except Exception:
                if existing is None:
                    shutil.rmtree(destination, ignore_errors=True)
                raise

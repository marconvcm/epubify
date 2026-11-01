import logging
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal

from epub_reader.domain.repositories.book_repository import BookRepository
from epub_reader.infrastructure.epub.parser import EpubMetadata, parse_metadata
from epub_reader.services.classification_service import CLASSIFICATION_VERSION, classify

logger = logging.getLogger(__name__)


class ClassificationSignals(QObject):
    classified = Signal(object)
    completed = Signal()


class ClassificationJob(QRunnable):
    def __init__(self, repository: BookRepository, identifiers: list[str]) -> None:
        super().__init__()
        self.repository, self.identifiers = repository, identifiers
        self.signals = ClassificationSignals()
        self._stop = Event()

    def cancel_pending(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            for identifier in self.identifiers:
                if self._stop.is_set():
                    break
                try:
                    book = self.repository.get(identifier)
                    if book is None or book.classification_version >= CLASSIFICATION_VERSION:
                        continue
                    try:
                        metadata = parse_metadata(book.storage_path)
                    except (ValueError, OSError):
                        metadata = EpubMetadata(book.title, book.author, book.package_path, None)
                    updated = self.repository.save_categories(
                        identifier, classify(metadata), CLASSIFICATION_VERSION
                    )
                    self.signals.classified.emit(updated)
                except Exception:
                    logger.exception("Could not classify book %s", identifier)
        finally:
            self.signals.completed.emit()

import logging
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event

from PySide6.QtCore import Property, QObject, QRunnable, QThreadPool, QUrl, Signal, Slot

from epub_reader.core.localization import tr
from epub_reader.domain.models.book import Book
from epub_reader.domain.models.category import Category
from epub_reader.infrastructure.epub.thumbnails import create_thumbnail
from epub_reader.platforms import android
from epub_reader.presentation.controllers.classification_worker import ClassificationJob
from epub_reader.presentation.models.book_list_model import BookFilterModel, BookListModel
from epub_reader.services.classification_service import CLASSIFICATION_VERSION
from epub_reader.services.epub_import_service import EpubImportService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportRequest:
    source: str
    path: Path | None
    uri: str | None = None


@dataclass(frozen=True)
class ImportResult:
    source: str
    status: str
    detail: str
    book: Book | None = None


class ImportSignals(QObject):
    started = Signal(int, str)
    processed = Signal(object)
    completed = Signal()


class ImportJob(QRunnable):
    def __init__(
        self, service: EpubImportService, requests: list[ImportRequest], known: set[str]
    ) -> None:
        super().__init__()
        self.service, self.requests, self.known = service, requests, known
        self.signals = ImportSignals()
        self._stop = Event()

    def cancel_pending(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            for index, request in enumerate(self.requests, start=1):
                if self._stop.is_set():
                    break
                self.signals.started.emit(index, request.source)
                cleanup = None
                try:
                    path = request.path
                    if path is None and request.uri and request.uri.startswith("content://"):
                        path, cleanup = android.stage_content_uri(request.uri)
                    if path is None:
                        raise ValueError("Choose a local EPUB file.")
                    book = self.service.import_book(path)
                    try:
                        create_thumbnail(book)
                    except (OSError, ValueError, RuntimeError):
                        logger.exception("Cover thumbnail could not be cached")
                    status = "existing" if book.id in self.known else "added"
                    self.known.add(book.id)
                    result = ImportResult(request.source, status, book.title, book)
                except Exception as exc:
                    if isinstance(exc, ValueError):
                        logger.warning("EPUB import failed: %s: %s", request.source, exc)
                    else:
                        logger.exception("EPUB import failed: %s", request.source)
                    message = (
                        str(exc)
                        if isinstance(exc, ValueError)
                        else "Unable to import this EPUB. "
                        "Check available storage and the application log."
                    )
                    result = ImportResult(request.source, "failed", message)
                finally:
                    if cleanup:
                        cleanup()
                self.signals.processed.emit(result)
        finally:
            self.signals.completed.emit()


class LibraryController(QObject):
    busyChanged = Signal()
    messageChanged = Signal()
    countChanged = Signal()
    batchChanged = Signal()
    categoriesChanged = Signal()

    def __init__(
        self, model: BookListModel, importer: EpubImportService, filtered: BookFilterModel
    ) -> None:
        super().__init__()
        self.model, self.importer = model, importer
        self.filtered = filtered
        self._category_books: dict[str, tuple[Category, ...]] = {}
        self._category_counts: Counter[str] = Counter()
        self._category_names: dict[str, str] = {"uncategorized": "Uncategorized"}
        self._active_category = ""
        self._favorite_ids: set[str] = set()
        self._classification_job: ClassificationJob | None = None
        self._classifying = False
        for book in model.books:
            self._book_changed(book)
        model.bookChanged.connect(self._book_changed)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self._busy = False
        self._message = ""
        self._message_values: dict[str, object] = {}
        self._summary = False
        self._job: ImportJob | None = None
        self._results: list[dict[str, str]] = []
        self._total = 0
        self._closing = False

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=messageChanged)
    def message(self) -> str:
        if self._summary:
            counts = Counter(result["status"] for result in self._results)
            parts = []
            for status, source in (
                ("added", "Added: {count}"),
                ("existing", "Already in library: {count}"),
                ("failed", "Failed: {count}"),
            ):
                if counts[status]:
                    parts.append(tr(source, count=counts[status]))
            return " · ".join(parts)
        return tr(self._message, **self._message_values)

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return self.model.rowCount()

    @Property(list, notify=categoriesChanged)
    def categories(self) -> list[dict[str, str | int]]:
        return [
            {"categoryId": key, "label": self._category_names[key], "count": count}
            for key, count in sorted(
                self._category_counts.items(),
                key=lambda item: (-item[1], self._category_names[item[0]].casefold()),
            )
            if count > 0
        ]

    @Property(str, notify=categoriesChanged)
    def activeCategory(self) -> str:
        return self._active_category

    @Property(str, notify=categoriesChanged)
    def activeCategoryName(self) -> str:
        return self._category_names.get(self._active_category, "")

    @Property(int, notify=categoriesChanged)
    def categoryCount(self) -> int:
        if self.filtered.favorites_only:
            return len(self._favorite_ids)
        return (
            self._category_counts[self._active_category]
            if self._active_category
            else self.model.rowCount()
        )

    @Property(bool, notify=categoriesChanged)
    def favoritesOnly(self) -> bool:
        return self.filtered.favorites_only

    @Property(int, notify=categoriesChanged)
    def favoriteCount(self) -> int:
        return len(self._favorite_ids)

    @Slot()
    def selectFavorites(self) -> None:
        self._active_category = ""
        self.filtered.favorites_only = True
        self.filtered.select_category("")
        self.categoriesChanged.emit()

    @Slot(str)
    def toggleFavorite(self, identifier: str) -> None:
        book = self.importer.repository.get(identifier)
        if book is not None:
            self.model.upsert(self.importer.repository.set_favorite(identifier, not book.favorite))

    @Property(bool, notify=categoriesChanged)
    def classifying(self) -> bool:
        return self._classifying

    @Slot(str)
    def selectCategory(self, identifier: str) -> None:
        if identifier and self._category_counts[identifier] <= 0:
            return
        self._active_category = identifier
        self.filtered.favorites_only = False
        self.filtered.select_category(identifier)
        self.categoriesChanged.emit()

    @Slot(object)
    def _book_changed(self, book: Book) -> None:
        was_favorite = book.id in self._favorite_ids
        if book.favorite:
            self._favorite_ids.add(book.id)
        else:
            self._favorite_ids.discard(book.id)
        old = self._category_books.get(book.id)
        if old == book.categories:
            if was_favorite != book.favorite:
                self.categoriesChanged.emit()
            return
        if old is not None:
            self._category_counts.subtract([c.id for c in old] if old else ["uncategorized"])
        self._category_books[book.id] = book.categories
        self._category_counts.update(
            [c.id for c in book.categories] if book.categories else ["uncategorized"]
        )
        for category in book.categories:
            self._category_names[category.id] = category.name
        if self._active_category and self._category_counts[self._active_category] <= 0:
            self._active_category = ""
            self.filtered.select_category("")
        self.categoriesChanged.emit()

    @Slot()
    def classifyExisting(self) -> None:
        if self._closing or self._classification_job is not None:
            return
        pending = [
            book.id
            for book in self.model.books
            if book.classification_version < CLASSIFICATION_VERSION
        ]
        if not pending:
            return
        self._classifying = True
        job = ClassificationJob(self.importer.repository, pending)
        job.signals.classified.connect(self._classified)
        job.signals.completed.connect(self._classification_complete)
        self._classification_job = job
        self.categoriesChanged.emit()
        self.pool.start(job)

    @Slot(object)
    def _classified(self, book: Book) -> None:
        if self._closing:
            return
        current = next((item for item in self.model.books if item.id == book.id), None)
        if current:
            self.model.upsert(
                replace(
                    current,
                    categories=book.categories,
                    classification_version=book.classification_version,
                )
            )

    @Slot()
    def _classification_complete(self) -> None:
        self._classification_job = None
        self._classifying = False
        self.categoriesChanged.emit()

    @Property(int, notify=batchChanged)
    def importTotal(self) -> int:
        return self._total

    @Property(int, notify=batchChanged)
    def importCompleted(self) -> int:
        return len(self._results)

    @Property(list, notify=batchChanged)
    def importResults(self) -> list[dict[str, str]]:
        return list(self._results)

    @Slot(QUrl)
    def importFile(self, url: QUrl) -> None:
        self.importFiles([url])

    @Slot("QList<QUrl>")
    def importFiles(self, urls: list[QUrl]) -> None:
        if self._busy or self._closing or not urls:
            return
        requests = [
            ImportRequest(
                Path(url.toLocalFile()).name if url.isLocalFile() else url.toString(),
                Path(url.toLocalFile()) if url.isLocalFile() else None,
                None if url.isLocalFile() else url.toString(),
            )
            for url in urls
        ]
        self._results = []
        self._total = len(requests)
        self._busy = True
        self._message = "Importing {count} EPUB file(s)…"
        self._message_values = {"count": self._total}
        self._summary = False
        self.busyChanged.emit()
        self.batchChanged.emit()
        self.messageChanged.emit()
        job = ImportJob(self.importer, requests, {book.id for book in self.model.books})
        job.signals.started.connect(self._started)
        job.signals.processed.connect(self._processed)
        job.signals.completed.connect(self._completed)
        self._job = job
        self.pool.start(job)

    @Slot(int, str)
    def _started(self, index: int, source: str) -> None:
        if self._closing:
            return
        self._message = "Importing {index}/{total} · {source}"
        self._message_values = {"index": index, "total": self._total, "source": source}
        self.messageChanged.emit()

    @Slot(object)
    def _processed(self, result: ImportResult) -> None:
        if self._closing:
            return
        if result.book is not None:
            self.model.upsert(result.book)
            self.countChanged.emit()
        self._results.append(
            {"source": result.source, "status": result.status, "detail": result.detail}
        )
        self.batchChanged.emit()

    @Slot()
    def _completed(self) -> None:
        if self._closing:
            return
        self._summary = True
        self._busy = False
        self._job = None
        self.busyChanged.emit()
        self.messageChanged.emit()
        self.batchChanged.emit()

    def shutdown(self) -> None:
        self._closing = True
        if self._job is not None:
            self._job.cancel_pending()
        if self._classification_job is not None:
            self._classification_job.cancel_pending()
        self.pool.waitForDone()

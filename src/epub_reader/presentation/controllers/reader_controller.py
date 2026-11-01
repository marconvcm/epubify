import logging
from typing import Any
from uuid import uuid4

from PySide6.QtCore import Property, QObject, QThreadPool, QTimer, Signal, Slot

from epub_reader.core.localization import tr
from epub_reader.core.preferences import Preferences
from epub_reader.domain.models.book import Book
from epub_reader.presentation.controllers.figure_index import FigureIndexJob
from epub_reader.presentation.models.book_list_model import BookListModel
from epub_reader.presentation.models.navigation import navigation_rows
from epub_reader.rendering.engine import NativeBookEngine
from epub_reader.rendering.publication import NavigationEntry
from epub_reader.services.annotation_service import AnnotationService
from epub_reader.services.reading_service import ReadingService

logger = logging.getLogger(__name__)


class ReaderController(QObject):
    changed = Signal()
    tocChanged = Signal()
    errorChanged = Signal()
    navigationChanged = Signal()
    annotationsChanged = Signal()
    pageTurnStarted = Signal(int)
    pageTurnFinished = Signal(bool)

    def __init__(
        self,
        service: ReadingService,
        preferences: Preferences,
        library: BookListModel,
        annotations: AnnotationService,
    ) -> None:
        super().__init__()
        self.service, self.preferences, self.library = service, preferences, library
        self.annotations = annotations
        self.engine = NativeBookEngine()
        self.engine.setParent(self)
        self.engine.relocated.connect(self._position_changed)
        self.book: Book | None = None
        self._immersive = False
        self._direction = 1
        self._toc: list[NavigationEntry] = []
        self._figures: list[NavigationEntry] = []
        self._navigation_section = "contents"
        self._navigation_query = ""
        self._collapsed: dict[str, set[int]] = {"contents": set(), "figures": set()}
        self._session = ""
        self._figures_loading = False
        self._figure_cache: dict[str, tuple[NavigationEntry, ...]] = {}
        self._figure_jobs: dict[str, FigureIndexJob] = {}
        self._figure_pool = QThreadPool(self)
        self._figure_pool.setMaxThreadCount(1)
        self._error = ""
        self._pending: tuple[str, float] | None = None
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.flush)
        preferences.changed.connect(self._settings)

    @Property(QObject, constant=True)
    def renderer(self) -> QObject:
        return self.engine

    @Property(bool, notify=changed)
    def active(self) -> bool:
        return self.book is not None

    @Property(str, notify=changed)
    def title(self) -> str:
        return self.book.title if self.book else ""

    @Property(str, notify=changed)
    def author(self) -> str:
        return self.book.author if self.book else ""

    @Property(list, notify=annotationsChanged)
    def notes(self) -> list[dict[str, str]]:
        return self.annotations.notes(self.book.id) if self.book else []

    @Slot(str)
    def addNote(self, text: str) -> None:
        if self.book:
            try:
                self.annotations.add(self.book.id, self.engine.location.encode(), text)
            except ValueError as exc:
                self.reportError(str(exc))
            self.annotationsChanged.emit()

    @Slot(str)
    def removeNote(self, identifier: str) -> None:
        if self.book:
            self.annotations.remove(self.book.id, identifier)
            self.annotationsChanged.emit()

    @Slot(str, str)
    def updateNote(self, identifier: str, text: str) -> None:
        if self.book:
            try:
                self.annotations.update(self.book.id, identifier, text)
            except ValueError as exc:
                self.reportError(str(exc))
            self.annotationsChanged.emit()

    @Slot(str)
    def navigateNote(self, location: str) -> None:
        from epub_reader.domain.models.reading_progress import ReadingLocation

        try:
            position = ReadingLocation.decode(location)
            self.engine.seek(position)
        except ValueError as exc:
            self.reportError(str(exc))

    @Property(float, notify=changed)
    def progress(self) -> float:
        return self._pending[1] if self._pending else self.book.progress if self.book else 0.0

    @Property(str, notify=changed)
    def pageLabel(self) -> str:
        return f"{self.engine.page + 1} / {self.engine.pages}"

    @Property(str, notify=changed)
    def pageText(self) -> str:
        return self.engine.page_text()

    @Property(int, notify=changed)
    def turnDirection(self) -> int:
        return self._direction

    @Property(bool, notify=changed)
    def immersive(self) -> bool:
        return self._immersive

    @Property(list, notify=tocChanged)
    def toc(self) -> list[dict[str, Any]]:
        return [{"label": e.label, "href": e.href, "depth": e.depth} for e in self._toc]

    @Property(int, notify=navigationChanged)
    def contentsCount(self) -> int:
        return len(self._toc)

    @Property(int, notify=navigationChanged)
    def figureCount(self) -> int:
        return len(self._figures)

    @Property(bool, notify=navigationChanged)
    def figuresLoading(self) -> bool:
        return self._figures_loading

    @Property(str, notify=navigationChanged)
    def navigationSection(self) -> str:
        return self._navigation_section

    @Property(str, notify=navigationChanged)
    def navigationQuery(self) -> str:
        return self._navigation_query

    @Property(list, notify=navigationChanged)
    def navigationRows(self) -> list[dict[str, Any]]:
        entries = self._toc if self._navigation_section == "contents" else self._figures
        active = -1
        candidates: list[tuple[int, int, int]] = []
        if self.engine.publication:
            chapter = self.engine.location.chapter
            for index, entry in enumerate(entries):
                path, _, fragment = entry.href.partition("#")
                if path == chapter:
                    position = self.engine.anchors.get(fragment) if fragment else 0
                    if position is not None and position <= self.engine.anchor_offset:
                        candidates.append((position, entry.depth, index))
            if candidates:
                active = max(candidates)[2]
        collapsed = self._collapsed[self._navigation_section]
        return navigation_rows(entries, collapsed, self._navigation_query, active)

    @Slot(str)
    def setNavigationSection(self, section: str) -> None:
        if section in ("contents", "figures") and section != self._navigation_section:
            self._navigation_section = section
            self._navigation_query = ""
            self.navigationChanged.emit()

    @Slot(str)
    def setNavigationQuery(self, query: str) -> None:
        self._navigation_query = query[:1000]
        self.navigationChanged.emit()

    @Slot(int)
    def toggleOutline(self, node_id: int) -> None:
        entries = self._toc if self._navigation_section == "contents" else self._figures
        collapsed = self._collapsed[self._navigation_section]
        if 0 <= node_id < len(entries):
            if node_id in collapsed:
                collapsed.remove(node_id)
            else:
                collapsed.add(node_id)
            self.navigationChanged.emit()

    @Property(str, notify=errorChanged)
    def error(self) -> str:
        return tr(self._error)

    @Slot(str)
    def openBook(self, book_id: str) -> None:
        self.flush()
        self._pending = None
        self._session = uuid4().hex
        self._toc, self._figures = [], []
        for collapsed in self._collapsed.values():
            collapsed.clear()
        self._navigation_query = ""
        self._figures_loading = False
        try:
            book = self.service.open(book_id)
            self.engine.configure(*self.preferences.reading_settings())
            self.book = book
            self.engine.open(book)
            self._toc = list(self.engine.publication.contents) if self.engine.publication else []
            self._load_figures()
            self._error = ""
        except (ValueError, KeyError, OSError) as exc:
            self.engine.close()
            self.book = None
            self.reportError(str(exc))
        self.changed.emit()
        self.tocChanged.emit()
        self.annotationsChanged.emit()
        self.errorChanged.emit()
        self.navigationChanged.emit()

    def _load_figures(self) -> None:
        publication = self.engine.publication
        if publication is None or self.book is None:
            return
        if publication.figures or self.book.id in self._figure_cache:
            self._figures = list(publication.figures or self._figure_cache[self.book.id])
            return
        self._figures_loading = True
        job = FigureIndexJob(self._session, publication)
        job.signals.finished.connect(self._figures_ready)
        self._figure_jobs[self._session] = job
        self._figure_pool.start(job)

    @Slot(str, object)
    def _figures_ready(self, session: str, figures: tuple[NavigationEntry, ...]) -> None:
        self._figure_jobs.pop(session, None)
        if session != self._session or self.book is None:
            return
        self._figures = list(figures)
        self._figure_cache[self.book.id] = figures
        self._figures_loading = False
        self.navigationChanged.emit()

    @Slot()
    def _settings(self) -> None:
        self.engine.configure(*self.preferences.reading_settings())

    @Slot(str, float)
    def _position_changed(self, location: str, fraction: float) -> None:
        if self.book is not None:
            self._pending = (location, fraction)
            self.save_timer.start()
            self.changed.emit()
            self.navigationChanged.emit()

    @Slot()
    def next(self) -> None:
        self._turn_page(1)

    @Slot()
    def previous(self) -> None:
        self._turn_page(-1)

    def _turn_page(self, direction: int) -> None:
        if self.book is None:
            return
        before = self.engine.location
        self._direction = direction
        self.pageTurnStarted.emit(direction)
        if direction > 0:
            self.engine.next()
        else:
            self.engine.previous()
        self.pageTurnFinished.emit(self.engine.location != before)

    @Slot(str)
    def navigate(self, href: str) -> None:
        try:
            self.engine.navigate(href)
        except (ValueError, OSError) as exc:
            self.reportError(str(exc))

    @Slot()
    def toggleImmersive(self) -> None:
        self._immersive = not self._immersive
        self.changed.emit()

    @Slot(str)
    def reportError(self, message: str) -> None:
        logger.warning("Reader error: %s", message)
        self._error = message
        self.errorChanged.emit()

    @Slot()
    def flush(self) -> None:
        self.save_timer.stop()
        if self.book and self._pending:
            try:
                self.book = self.service.save(self.book.id, *self._pending)
            except Exception:
                logger.exception("Could not save reading progress")
                self.reportError(
                    "Your reading position could not be saved. Check available storage."
                )
                return
            self._pending = None
            self.library.upsert(self.book)

    @Slot()
    def close(self) -> None:
        self.flush()
        self.engine.close()
        self.book = None
        self._pending = None
        self._immersive = False
        self._toc = []
        self._figures = []
        self._session = ""
        self._figures_loading = False
        self.changed.emit()
        self.tocChanged.emit()
        self.annotationsChanged.emit()
        self.navigationChanged.emit()

    def shutdown(self) -> None:
        self.flush()
        self._figure_pool.waitForDone()

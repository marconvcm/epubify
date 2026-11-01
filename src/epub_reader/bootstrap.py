import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QIcon, QImageReader
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtSvg import QSvgRenderer  # noqa: F401 - include SVG support in Android deployment
from sqlalchemy import Engine

from epub_reader.core.design import available_schemes
from epub_reader.core.localization import LANGUAGES, LanguageManager
from epub_reader.core.logging import configure_logging
from epub_reader.core.paths import RESOURCES, AppPaths
from epub_reader.core.preferences import Preferences
from epub_reader.core.typography import configure_ui_font
from epub_reader.infrastructure.database.engine import create_database
from epub_reader.infrastructure.database.repositories import PreferenceRepository, SqlBookRepository
from epub_reader.platforms import android
from epub_reader.presentation.controllers.library_controller import LibraryController
from epub_reader.presentation.controllers.reader_controller import ReaderController
from epub_reader.presentation.controllers.sync_controller import SyncController
from epub_reader.presentation.models.book_list_model import BookFilterModel, BookListModel
from epub_reader.presentation.native_page import BookPage  # noqa: F401 - registers the QML type
from epub_reader.presentation.surface_preview import SurfacePreview  # noqa: F401
from epub_reader.services.annotation_service import AnnotationService
from epub_reader.services.epub_import_service import EpubImportService
from epub_reader.services.library_service import LibraryService
from epub_reader.services.reading_service import ReadingService

# Our controls supply their own backgrounds/palettes; use a customizable style
# consistently on desktop and Android, before the first QML engine is created.
QQuickStyle.setStyle("Basic")


@dataclass
class Runtime:
    engine: QQmlApplicationEngine
    database: Engine
    library: LibraryController
    reader: ReaderController
    i18n: LanguageManager
    sync: SyncController
    # Keep context objects alive for the full engine lifetime; QML does not own them.
    objects: list[QObject]
    _closed: bool = False

    def shutdown(self) -> None:
        if self._closed:
            return
        self.reader.shutdown()
        self.library.shutdown()
        self.sync.shutdown()
        self.i18n.shutdown()
        self.database.dispose()
        self._closed = True

    def dispose(self) -> None:
        """Destroy QML views before their Python context objects."""
        self.shutdown()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.Type.DeferredDelete)


def create_runtime(
    paths: AppPaths, *, library_only: bool = False, preview_size: tuple[int, int] | None = None
) -> Runtime:
    configure_ui_font()
    QGuiApplication.setWindowIcon(QIcon(str(RESOURCES / "icons/app_icon.png")))
    paths.create()
    database = create_database(paths.database)
    repository = SqlBookRepository(database)
    i18n = LanguageManager(PreferenceRepository(database))
    preferences = Preferences(PreferenceRepository(database))
    books = BookListModel(LibraryService(repository).books())
    filtered = BookFilterModel(books)
    library = LibraryController(books, EpubImportService(repository, paths.books), filtered)
    reader = ReaderController(
        ReadingService(repository), preferences, books, AnnotationService(database)
    )
    sync = SyncController(database, paths, PreferenceRepository(database))
    engine = QQmlApplicationEngine()
    if preview_size:
        engine.setInitialProperties(
            {"width": preview_size[0], "height": preview_size[1], "mobilePreview": True}
        )
    owned_objects = [preferences, books, filtered, library, reader, i18n, sync]
    # Context properties do not transfer ownership. Give the engine ownership so
    # its contexts are destroyed before these objects, including at process exit.
    for owned in owned_objects:
        owned.setParent(engine)
    context = engine.rootContext()
    for name, obj in {
        "preferences": preferences,
        "library": library,
        "bookModel": filtered,
        "reader": reader,
        "i18n": i18n,
        "sync": sync,
    }.items():
        context.setContextProperty(name, obj)
    context.setContextProperty("readerEnabled", not library_only)
    i18n.changed.connect(engine.retranslate)
    i18n.changed.connect(library.messageChanged.emit)
    i18n.changed.connect(reader.errorChanged.emit)
    i18n.changed.connect(sync.changed.emit)

    def refresh_remote(changes: dict[str, object]) -> None:
        identifiers = (
            [book.id for book in repository.list()]
            if changes.get("all")
            else changes.get("books", [])
        )
        if isinstance(identifiers, list):
            for identifier in identifiers:
                if isinstance(identifier, str) and (book := repository.get(identifier)) is not None:
                    books.upsert(book)
            if identifiers:
                library.countChanged.emit()
                reader.annotationsChanged.emit()
        if changes.get("preferences") or changes.get("all"):
            preferences.reload()
            i18n.setLanguage(str(preferences.repository.get("language", i18n.current_language())))

    sync.dataChanged.connect(refresh_remote)
    engine.load(QUrl.fromLocalFile(str(RESOURCES / "qml/Main.qml")))
    if not engine.rootObjects():
        library.shutdown()
        database.dispose()
        raise RuntimeError("Unable to load the application interface. See the QML errors above.")
    QTimer.singleShot(0, library.classifyExisting)
    QTimer.singleShot(0, sync.startSaved)
    if android.IS_ANDROID:
        connect_android(engine, library, preferences)
    return Runtime(
        engine,
        database,
        library,
        reader,
        i18n,
        sync,
        owned_objects,
    )


def connect_android(
    engine: QQmlApplicationEngine, library: LibraryController, preferences: Preferences
) -> None:
    """Color the system bars with the app palette and import EPUBs opened from other apps."""

    def paint() -> None:
        palette: dict[str, str] = preferences.palette  # type: ignore[assignment]
        android.set_system_bars(palette["background"], dark=bool(preferences.dark))

    def open_pending() -> None:
        if uri := android.take_intent_uri():
            library.importFiles([QUrl(uri)])

    def on_state(state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationActive:
            paint()
            open_pending()

    preferences.changed.connect(paint)
    QGuiApplication.instance().applicationStateChanged.connect(on_state)  # type: ignore[union-attr]
    QTimer.singleShot(0, paint)
    # MainActivity drops the document of a VIEW intent into a file; check for it regularly.
    poller = QTimer(engine)
    poller.setInterval(700)
    poller.timeout.connect(open_pending)
    poller.start()


def schedule_captures(runtime: Runtime, directory: Path) -> None:
    """Capture only this application window; never the rest of the user's desktop."""
    logger = logging.getLogger(__name__)

    def capture(label: str) -> None:
        roots = runtime.engine.rootObjects()
        if not roots or not isinstance(roots[0], QQuickWindow):
            logger.warning("No application window is available for capture")
            return
        image = roots[0].grabWindow()
        target = directory / f"window-{label}.png"
        if image.isNull() or not image.save(str(target)):
            logger.warning("Could not capture the application window")
            return
        logger.info("Captured application window: %s", target)

    for delay in (1000, 4000, 10000):
        QTimer.singleShot(delay, lambda label=str(delay): capture(label))


def main() -> int:
    parser = argparse.ArgumentParser(description="Epubify — a quiet place for your books")
    parser.add_argument(
        "--data-dir", type=Path, help="Override platform application data directory"
    )
    parser.add_argument(
        "--smoke-test", action="store_true", help="Load the window and exit after 2s"
    )
    parser.add_argument(
        "--qml-only",
        "--library-only",
        dest="library_only",
        action="store_true",
        help="Limit this run to the library interface",
    )
    parser.add_argument("--open-last", action="store_true", help="Open the most recently read book")
    parser.add_argument(
        "--mobile-preview",
        action="store_true",
        help="Start at 411x914 logical pixels (1080x2400 Android screen at density 420)",
    )
    parser.add_argument(
        "--diagnostics-dir",
        type=Path,
        help="Write reader logs and application-window screenshots to this directory",
    )
    parser.add_argument(
        "--color-scheme",
        choices=[s["id"] for s in available_schemes()],
        help="Select and remember a bundled color scheme",
    )
    parser.add_argument(
        "--language",
        choices=[code for code, _ in LANGUAGES],
        help="Select and remember the application language",
    )
    args = parser.parse_args()
    app = QGuiApplication(sys.argv[:1])
    app.setOrganizationName("Epubify")
    app.setApplicationName("Epubify")
    app.setApplicationDisplayName("Epubify")
    QImageReader.setAllocationLimit(128)
    paths = AppPaths(args.data_dir) if args.data_dir else AppPaths.default()
    paths.create()
    configure_logging(paths.root, args.diagnostics_dir)
    runtime = create_runtime(
        paths,
        library_only=args.library_only,
        preview_size=(411, 914) if args.mobile_preview else None,
    )
    if args.language:
        runtime.i18n.setLanguage(args.language)
    if args.color_scheme:
        runtime.reader.preferences.setColorScheme(args.color_scheme)
    app.aboutToQuit.connect(runtime.shutdown)
    if args.open_last and runtime.library.model.books:
        latest = max(
            runtime.library.model.books,
            key=lambda book: book.last_opened_at or book.imported_at,
        )
        QTimer.singleShot(0, lambda: runtime.reader.openBook(latest.id))
    if args.diagnostics_dir:
        schedule_captures(runtime, args.diagnostics_dir)
    if args.smoke_test:
        QTimer.singleShot(2000, app.quit)
    try:
        return app.exec()
    finally:
        runtime.dispose()

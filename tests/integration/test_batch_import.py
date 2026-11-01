from pathlib import Path

import pytest
from PySide6.QtCore import QMetaObject, QObject, QUrl

from epub_reader.bootstrap import create_runtime
from epub_reader.core.paths import AppPaths
from tests.fixtures.epub_factory import make_epub


@pytest.mark.gui
def test_batch_import_continues_after_errors_deduplicates_and_persists(
    qtbot, tmp_path: Path
) -> None:
    paths = AppPaths(tmp_path / "app")
    first = make_epub(tmp_path / "first.epub", title="The First Book")
    second = make_epub(tmp_path / "second.epub", title="The Second Book")
    broken = tmp_path / "broken.epub"
    broken.write_bytes(b"not an EPUB")
    runtime = create_runtime(paths)
    try:
        history = []
        runtime.library.batchChanged.connect(
            lambda: history.append(runtime.library.importCompleted)
        )
        urls = [QUrl.fromLocalFile(str(p)) for p in (first, broken, first, second)]
        urls.append(QUrl("https://example.org/remote.epub"))
        runtime.library.importFiles(urls)
        assert runtime.library.busy
        assert runtime.library.importTotal == 5
        qtbot.waitUntil(lambda: not runtime.library.busy, timeout=10_000)
        assert runtime.library.count == 2
        assert runtime.library.importCompleted == 5
        assert history == sorted(history)
        results = runtime.library.importResults
        assert [r["status"] for r in results] == ["added", "failed", "existing", "added", "failed"]
        assert results[1]["source"] == "broken.epub"
        assert "not an EPUB" in results[1]["detail"] or "damaged" in results[1]["detail"]
        assert "local EPUB" in results[-1]["detail"]
        assert "Added: 2" in runtime.library.message
        assert "Failed: 2" in runtime.library.message
        assert len(list(paths.books.iterdir())) == 2
    finally:
        runtime.dispose()
    restored = create_runtime(paths)
    try:
        assert restored.library.count == 2
        assert {b.title for b in restored.library.model.books} == {
            "The First Book",
            "The Second Book",
        }
    finally:
        restored.dispose()


@pytest.mark.gui
def test_qml_multiple_file_selection_reaches_the_worker(qtbot, tmp_path: Path) -> None:
    runtime = create_runtime(AppPaths(tmp_path / "app"))
    try:
        first = make_epub(tmp_path / "first.epub", title="First")
        second = make_epub(tmp_path / "second.epub", title="Second")
        root = runtime.engine.rootObjects()[0]
        dialog = root.findChild(QObject, "epubImportDialog")
        assert dialog is not None
        import json

        from PySide6.QtQml import QQmlExpression, qmlContext

        mode = QQmlExpression(qmlContext(dialog), dialog, "fileMode === FileDialog.OpenFiles")
        assert mode.evaluate()[0] is True
        urls = ", ".join(
            f"Qt.resolvedUrl({json.dumps(QUrl.fromLocalFile(str(p)).toString())})"
            for p in (first, second)
        )
        action = QQmlExpression(qmlContext(root), root, f"library.importFiles([{urls}])")
        action.evaluate()
        assert not action.hasError(), action.error().toString()
        qtbot.waitUntil(lambda: not runtime.library.busy, timeout=10_000)
        assert runtime.library.importTotal == 2
        assert runtime.library.count == 2
        button = root.findChild(QObject, "importResultsButton")
        assert button.property("visible")
        assert QMetaObject.invokeMethod(button, "clicked")
        report = root.findChild(QObject, "importReport")
        qtbot.waitUntil(lambda: report.property("visible"))
    finally:
        runtime.dispose()


@pytest.mark.gui
def test_empty_selection_and_second_submission_do_not_replace_running_batch(
    qtbot, tmp_path: Path
) -> None:
    runtime = create_runtime(AppPaths(tmp_path / "app"))
    try:
        runtime.library.importFiles([])
        assert not runtime.library.busy
        assert runtime.library.importTotal == 0
        first = make_epub(tmp_path / "first.epub", title="First")
        second = make_epub(tmp_path / "second.epub", title="Second")
        runtime.library.importFiles([QUrl.fromLocalFile(str(first))])
        runtime.library.importFiles([QUrl.fromLocalFile(str(second))])
        qtbot.waitUntil(lambda: not runtime.library.busy, timeout=10_000)
        assert runtime.library.importTotal == 1
        assert [b.title for b in runtime.library.model.books] == ["First"]
    finally:
        runtime.dispose()


@pytest.mark.gui
def test_shutdown_finishes_current_file_and_stops_pending_imports(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    from threading import Event

    from epub_reader.presentation.controllers.library_controller import ImportJob

    runtime = create_runtime(AppPaths(tmp_path / "app"))
    entered, release = Event(), Event()
    original_import = runtime.library.importer.import_book
    original_cancel = ImportJob.cancel_pending

    def wait_then_import(path: Path):
        entered.set()
        assert release.wait(5)
        return original_import(path)

    def cancel_then_release(job: ImportJob) -> None:
        original_cancel(job)
        release.set()

    monkeypatch.setattr(runtime.library.importer, "import_book", wait_then_import)
    monkeypatch.setattr(ImportJob, "cancel_pending", cancel_then_release)
    try:
        first = make_epub(tmp_path / "first.epub", title="First")
        second = make_epub(tmp_path / "second.epub", title="Second")
        runtime.library.importFiles([QUrl.fromLocalFile(str(p)) for p in (first, second)])
        qtbot.waitUntil(entered.is_set)
        runtime.library.shutdown()
        saved = runtime.library.importer.repository.list()
        assert [book.title for book in saved] == ["First"]
        assert (saved[0].storage_path / saved[0].package_path).is_file()
    finally:
        release.set()
        runtime.dispose()

from pathlib import Path

import pytest
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetricsF, QGuiApplication

from epub_reader.bootstrap import create_runtime
from epub_reader.core.paths import AppPaths
from epub_reader.core.typography import register_fonts
from epub_reader.rendering.engine import NativeBookEngine
from epub_reader.services.epub_import_service import EpubImportService
from tests.fixtures.epub_factory import make_epub


@pytest.mark.gui
def test_bundled_fonts_are_registered_and_used_by_the_window(qtbot, tmp_path: Path) -> None:
    runtime = create_runtime(AppPaths(tmp_path / "app"))
    try:
        families = {
            family
            for font_id in register_fonts()
            for family in QFontDatabase.applicationFontFamilies(font_id)
        }
        assert {"IBM Plex Sans", "Playfair Display", "JetBrains Mono"} <= families
        root = runtime.engine.rootObjects()[0]
        assert root.property("font").family() == "IBM Plex Sans"
        assert QGuiApplication.font().family() == "IBM Plex Sans"
        assert not QGuiApplication.windowIcon().isNull()
        from PySide6.QtCore import QObject
        from PySide6.QtQml import QQmlProperty

        button = root.findChild(QObject, "importEpubButton")
        assert button is not None
        assert QQmlProperty.read(button, "palette.buttonText").name() == "#f5ebe0"
        assert QQmlProperty.read(button, "icon.color").name() == "#f5ebe0"
        mono = QFont("JetBrains Mono")
        mono.setPixelSize(20)
        metrics = QFontMetricsF(mono)
        assert metrics.horizontalAdvance("WWWW") == metrics.horizontalAdvance("iiii")
    finally:
        runtime.dispose()


@pytest.mark.gui
def test_reader_enforces_playfair_and_preserves_semantic_code_fonts(
    qtbot, repository, tmp_path: Path
) -> None:
    chapter = b"""<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Typography</title></head>
<body style="font-family: Arial"><h1 style="font-family: Arial">Reading with character</h1>
<p style="font-family: Arial">Body text with <em>gentle emphasis</em> and
<strong>bold words</strong>.</p>
<p>A fragment of <code>inline_code()</code> in the text.</p>
<pre><code><span style="font-family: Georgia">print('reading')</span></code></pre>
<p style="font-family: monospace">legacy_monospace</p></body></html>"""
    source = make_epub(tmp_path / "type.epub", extra={"EPUB/chapter1.xhtml": chapter})
    book = EpubImportService(repository, tmp_path / "books").import_book(source)
    engine = NativeBookEngine()
    engine.open(book)
    for text in ("Body text", "Reading with character", "gentle emphasis", "bold words"):
        cursor = engine.document.find(text)
        assert QFontInfo(cursor.charFormat().font()).family() == "Playfair Display"
    assert engine.document.find("gentle emphasis").charFormat().fontItalic()
    assert engine.document.find("bold words").charFormat().fontWeight() >= QFont.Weight.Bold
    for text in ("inline_code()", "print('reading')", "legacy_monospace"):
        cursor = engine.document.find(text)
        assert not cursor.isNull()
        assert QFontInfo(cursor.charFormat().font()).family() == "JetBrains Mono"
        assert cursor.charFormat().fontFixedPitch()


@pytest.mark.gui
def test_new_json_scheme_updates_qml_reader_and_saved_preference(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    import json

    from PySide6.QtCore import QObject

    import epub_reader.core.design as design
    from epub_reader.core.paths import RESOURCES

    source = (RESOURCES / "themes/stormcloud.json").read_text()
    themes = tmp_path / "themes"
    themes.mkdir()
    for existing in (RESOURCES / "themes").glob("*.json"):
        (themes / existing.name).write_bytes(existing.read_bytes())
    alternate = json.loads(source)
    alternate["id"], alternate["name"] = "twilight", "Twilight"
    alternate["colors"]["ebony_clay"] = "#17293D"
    alternate["colors"]["brown"] = "#7F4E62"
    (themes / "twilight.json").write_text(json.dumps(alternate))
    monkeypatch.setattr(design, "SCHEMES_DIR", themes)
    design.scheme_for.cache_clear()
    paths = AppPaths(tmp_path / "app")
    runtime = create_runtime(paths)
    try:
        book = runtime.library.importer.import_book(make_epub(tmp_path / "book.epub"))
        runtime.reader.openBook(book.id)
        root = runtime.engine.rootObjects()[0]
        qtbot.waitUntil(lambda: root.findChild(QObject, "colorSchemePicker") is not None)
        qtbot.wait(150)
        runtime.reader.next()
        location = runtime.reader.engine.location
        preferences = runtime.reader.preferences
        assert len(preferences.schemeOptions) == len(list(themes.glob("*.json")))
        picker = root.findChild(QObject, "colorSchemePicker")
        assert picker.property("currentValue") == "parchment"
        assert picker.property("displayText") == "Parchment"
        preferences.setColorScheme("twilight")
        qtbot.waitUntil(lambda: root.property("color").name() == "#17293d")
        assert runtime.reader.engine.location == location
        assert runtime.reader.engine.image.pixelColor(0, 0).name() == "#17293d"
        assert root.findChild(QObject, "colorSchemePicker").property("currentValue") == "twilight"
        assert preferences.palette["action"] == "#7F4E62"
    finally:
        runtime.dispose()
    restored = create_runtime(paths)
    try:
        assert restored.reader.preferences.colorScheme == "twilight"
        restored.reader.openBook(book.id)
        assert restored.reader.engine.location == location
        assert restored.reader.engine.image.pixelColor(0, 0).name() == "#17293d"
    finally:
        restored.dispose()
        design.scheme_for.cache_clear()

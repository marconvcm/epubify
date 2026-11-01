import json
import re
from pathlib import Path
from string import Formatter

import pytest
from PySide6.QtCore import QMetaObject, QObject

from epub_reader.bootstrap import create_runtime
from epub_reader.core.localization import LANGUAGES, tr
from epub_reader.core.paths import RESOURCES, AppPaths


@pytest.mark.gui
@pytest.mark.parametrize(
    "language,expected",
    [
        ("en", "Import EPUBs"),
        ("pt", "Importar EPUBs"),
        ("es", "Importar EPUB"),
        ("fr", "Importer des EPUB"),
        ("de", "EPUBs importieren"),
        ("it", "Importa EPUB"),
        ("zh-CN", "导入 EPUB"),
        ("ja", "EPUB を読み込む"),
    ],
)
def test_language_switch_updates_live_qml_and_is_saved(
    qtbot, tmp_path: Path, language: str, expected: str
) -> None:
    paths = AppPaths(tmp_path / "app")
    runtime = create_runtime(paths)
    try:
        root = runtime.engine.rootObjects()[0]
        button = root.findChild(QObject, "importEpubButton")
        runtime.i18n.setLanguage(language)
        qtbot.waitUntil(lambda: button.property("text") == expected)
        assert set(item["code"] for item in runtime.i18n.languages) == {
            code for code, _ in LANGUAGES
        }
        assert QMetaObject.invokeMethod(root.findChild(QObject, "settingsButton"), "clicked")
        settings = root.findChild(QObject, "librarySettings")
        qtbot.waitUntil(lambda: settings.property("opened"))
        assert settings.findChild(QObject, "languagePicker").property("currentValue") == language
        assert tr("Added: {count}", count=2).endswith("2")
    finally:
        runtime.dispose()
    restored = create_runtime(paths)
    try:
        assert restored.i18n.language == language
        root = restored.engine.rootObjects()[0]
        assert root.findChild(QObject, "importEpubButton").property("text") == expected
    finally:
        restored.dispose()


def test_catalogs_cover_all_qml_strings_and_preserve_placeholders() -> None:
    catalogs = json.loads((RESOURCES / "i18n/catalogs.json").read_text())
    assert set(catalogs) == {code for code, _ in LANGUAGES}
    sources = set()
    for file in (RESOURCES / "qml").rglob("*.qml"):
        sources.update(
            json.loads(literal)
            for literal in re.findall(
                r'qsTranslate\("Epubify",\s*("(?:[^"\\]|\\.)*")', file.read_text()
            )
        )
    formatter = Formatter()
    for code, catalog in catalogs.items():
        assert set(catalog) == set(catalogs["en"])
        assert sources <= set(catalog)
        assert (RESOURCES / "i18n" / f"{code}.qm").is_file()
        for source, translation in catalog.items():
            assert translation
            assert sorted(re.findall(r"%\d+", source)) == sorted(re.findall(r"%\d+", translation))
            assert {field for _, field, _, _ in formatter.parse(source) if field} == {
                field for _, field, _, _ in formatter.parse(translation) if field
            }

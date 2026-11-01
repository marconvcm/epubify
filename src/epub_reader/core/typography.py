"""Application-owned fonts, registered once and used without runtime downloads."""

from functools import cache

from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication

from epub_reader.core.paths import RESOURCES

UI_FAMILY = "IBM Plex Sans"
READING_FAMILY = "Playfair Display"
MONO_FAMILY = "JetBrains Mono"
READING_FALLBACKS = [READING_FAMILY, "Noto Serif", "Georgia", "serif"]
MONO_FALLBACKS = [MONO_FAMILY, "Consolas", "monospace"]
MONO_TAGS = {"code", "pre", "kbd", "samp", "tt"}


@cache
def register_fonts() -> tuple[int, ...]:
    if QGuiApplication.instance() is None:
        raise RuntimeError("Create the Qt application before loading fonts.")
    identifiers = []
    families = set()
    for file in sorted((RESOURCES / "fonts").rglob("*.ttf")):
        identifier = QFontDatabase.addApplicationFont(str(file))
        if identifier < 0:
            raise RuntimeError(f"Unable to load bundled font: {file.name}")
        identifiers.append(identifier)
        families.update(QFontDatabase.applicationFontFamilies(identifier))
    if not {UI_FAMILY, READING_FAMILY, MONO_FAMILY} <= families:
        raise RuntimeError("The application bundle is missing its required fonts.")
    return tuple(identifiers)


def configure_ui_font() -> None:
    register_fonts()
    font = QFont(UI_FAMILY)
    font.setPixelSize(14)
    QGuiApplication.setFont(font)

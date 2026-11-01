"""Native Qt translations and a persisted application-language preference."""

from PySide6.QtCore import Property, QCoreApplication, QLocale, QObject, QTranslator, Signal, Slot

from epub_reader.core.paths import RESOURCES
from epub_reader.infrastructure.database.repositories import PreferenceRepository

LANGUAGES = (
    ("en", "English"),
    ("zh-CN", "简体中文"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("ja", "日本語"),
    ("pt", "Português"),
    ("it", "Italiano"),
)


def tr(source: str, /, **values: object) -> str:
    translated = QCoreApplication.translate("Epubify", source)
    return translated.format(**values) if values else translated


class LanguageManager(QObject):
    changed = Signal()

    def __init__(self, repository: PreferenceRepository) -> None:
        super().__init__()
        self.repository = repository
        code = QLocale.system().name().split("_")[0]
        system_language = "zh-CN" if code == "zh" else code
        saved = str(repository.get("language", system_language))
        self._language = saved if saved in dict(LANGUAGES) else "en"
        self._translator: QTranslator | None = None
        self._install(self._language)

    def current_language(self) -> str:
        return self._language

    @Property(str, notify=changed)
    def language(self) -> str:
        return self._language

    @Property(list, constant=True)
    def languages(self) -> list[dict[str, str]]:
        return [{"code": code, "name": name} for code, name in LANGUAGES]

    def _install(self, code: str) -> None:
        translator = None
        if code != "en":
            translator = QTranslator(self)
            if not translator.load(str(RESOURCES / "i18n" / f"{code}.qm")):
                raise ValueError(f"Translation resources are missing for {code}")
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError("Create the Qt application before loading translations")
        if self._translator is not None:
            app.removeTranslator(self._translator)
            self._translator.deleteLater()
        self._translator = translator
        if translator is not None:
            app.installTranslator(translator)

    @Slot(str)
    def setLanguage(self, code: str) -> None:
        if code not in dict(LANGUAGES):
            raise ValueError("Unsupported application language")
        self.repository.set("language", code)
        if code != self._language:
            self._install(code)
            self._language = code
            self.changed.emit()

    def shutdown(self) -> None:
        app = QCoreApplication.instance()
        if self._translator is not None and app is not None:
            app.removeTranslator(self._translator)
            self._translator = None

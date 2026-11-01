from dataclasses import asdict

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication

from epub_reader.core.design import DEFAULT_SCHEME, available_schemes, palette_for, scheme_for
from epub_reader.core.typography import MONO_FAMILY, READING_FAMILY, UI_FAMILY
from epub_reader.infrastructure.database.repositories import PreferenceRepository
from epub_reader.rendering.surfaces import SURFACE_KEYS, surface_for


class Preferences(QObject):
    _font_size: int
    _dark: bool
    _surface: str
    _scheme_id: str
    _reduced: bool
    changed = Signal()

    def reading_settings(self) -> tuple[int, bool, str, str]:
        return self._font_size, self._dark, self._surface, self._scheme_id

    def reload(self) -> None:
        self._dark = bool(self.repository.get("dark", self._dark))
        self._font_size = max(14, min(32, int(self.repository.get("font_size", self._font_size))))
        self._reduced = bool(self.repository.get("reduced_motion", self._reduced))
        surface = str(self.repository.get("reading_surface", self._surface))
        if surface in SURFACE_KEYS:
            self._surface = surface
        scheme = str(self.repository.get("color_scheme", self._scheme_id))
        if any(option["id"] == scheme for option in self._scheme_options):
            self._scheme_id = scheme
        self.changed.emit()

    def __init__(self, repository: PreferenceRepository) -> None:
        super().__init__()
        self.repository = repository
        self._scheme_options = available_schemes()
        saved_scheme = repository.get("color_scheme", DEFAULT_SCHEME)
        self._scheme_id = (
            str(saved_scheme)
            if any(s["id"] == saved_scheme for s in self._scheme_options)
            else DEFAULT_SCHEME
        )
        self._dark = bool(repository.get("dark", True))
        self._font_size = max(14, min(32, int(repository.get("font_size", 20))))
        self._reduced = bool(repository.get("reduced_motion", False))
        stored_surface = repository.get("reading_surface", "plain")
        self._surface = str(stored_surface) if stored_surface in SURFACE_KEYS else "plain"
        self._system_reduced = False
        # Keep the wrapper for the owner alive as long as its accessibility child.
        self._style_hints = QGuiApplication.styleHints()
        self._accessibility = self._style_hints.accessibility()
        if self._accessibility is not None:
            self._accessibility.motionPreferenceChanged.connect(self._read_motion)
            self._read_motion()

    @Slot()
    def _read_motion(self) -> None:
        self._system_reduced = (
            self._accessibility is not None
            and self._accessibility.motionPreference() == Qt.MotionPreference.ReducedMotion
        )
        self.changed.emit()

    @Property(bool, notify=changed)
    def dark(self) -> bool:
        return self._dark

    @Property(dict, notify=changed)
    def palette(self) -> dict[str, str]:
        return asdict(palette_for(self._dark, self._scheme_id))

    @Property(list, notify=changed)
    def coverColors(self) -> list[str]:
        return list(scheme_for(self._scheme_id).covers)

    @Property(str, notify=changed)
    def coverText(self) -> str:
        return scheme_for(self._scheme_id).cover_text

    @Property(str, notify=changed)
    def coverSecondary(self) -> str:
        return scheme_for(self._scheme_id).cover_secondary

    @Property(str, notify=changed)
    def colorScheme(self) -> str:
        return self._scheme_id

    @Property(list, constant=True)
    def schemeOptions(self) -> list[dict[str, str]]:
        return self._scheme_options

    @Slot(str)
    def setColorScheme(self, identifier: str) -> None:
        scheme_for(identifier)  # Validate before changing or persisting state.
        self.repository.set("color_scheme", identifier)
        if identifier != self._scheme_id:
            self._scheme_id = identifier
            self.changed.emit()

    @Property(dict, constant=True)
    def fontFamilies(self) -> dict[str, str]:
        return {"sans": UI_FAMILY, "serif": READING_FAMILY, "mono": MONO_FAMILY}

    @Property(int, notify=changed)
    def fontSize(self) -> int:
        return self._font_size

    @Property(bool, notify=changed)
    def reducedMotion(self) -> bool:
        return self._reduced or self._system_reduced

    @Property(str, notify=changed)
    def readingSurface(self) -> str:
        return self._surface

    @Property(list, notify=changed)
    def surfaceOptions(self) -> list[dict[str, str]]:
        return [
            {
                "key": key,
                "label": surface_for(key, self._dark, self._scheme_id).label,
                "foreground": surface_for(key, self._dark, self._scheme_id).foreground,
            }
            for key in SURFACE_KEYS
        ]

    @Slot(str)
    def setReadingSurface(self, key: str) -> None:
        if key not in SURFACE_KEYS:
            raise ValueError("Unknown reading surface.")
        if key != self._surface:
            self._surface = key
            self.repository.set("reading_surface", key)
            self.changed.emit()

    @Slot()
    def toggleTheme(self) -> None:
        self._dark = not self._dark
        self.repository.set("dark", self._dark)
        self.changed.emit()

    @Slot(int)
    def setFontSize(self, value: int) -> None:
        self._font_size = max(14, min(32, value))
        self.repository.set("font_size", self._font_size)
        self.changed.emit()

    @Slot()
    def toggleReducedMotion(self) -> None:
        self._reduced = not self._reduced
        self.repository.set("reduced_motion", self._reduced)
        self.changed.emit()

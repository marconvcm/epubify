from PySide6.QtCore import Property, Signal
from PySide6.QtGui import QPainter
from PySide6.QtQml import QmlElement
from PySide6.QtQuick import QQuickItem, QQuickPaintedItem

from epub_reader.core.design import DEFAULT_SCHEME
from epub_reader.rendering.surfaces import paint_surface, surface_for

QML_IMPORT_NAME = "Epubify.Native"
QML_IMPORT_MAJOR_VERSION = 1


@QmlElement
class SurfacePreview(QQuickPaintedItem):
    changed = Signal()

    def __init__(self, parent: QQuickItem | None = None) -> None:
        super().__init__(parent)
        self._surface, self._dark = "plain", True
        self._scheme = DEFAULT_SCHEME

    def get_surface(self) -> str:
        return self._surface

    def set_surface(self, value: str) -> None:
        self._surface = value
        self.changed.emit()
        self.update()

    def get_dark(self) -> bool:
        return self._dark

    def set_dark(self, value: bool) -> None:
        self._dark = value
        self.changed.emit()
        self.update()

    surface = Property(str, get_surface, set_surface, notify=changed)
    dark = Property(bool, get_dark, set_dark, notify=changed)

    def get_scheme(self) -> str:
        return self._scheme

    def set_scheme(self, value: str) -> None:
        self._scheme = value
        self.changed.emit()
        self.update()

    colorScheme = Property(str, get_scheme, set_scheme, notify=changed)

    def paint(self, painter: QPainter) -> None:
        paint_surface(
            painter, self.boundingRect(), surface_for(self._surface, self._dark, self._scheme)
        )

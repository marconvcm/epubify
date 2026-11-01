from PySide6.QtCore import Property, QObject, QPointF, QRectF, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QHoverEvent, QImage, QLinearGradient, QMouseEvent, QPainter
from PySide6.QtQml import QmlElement
from PySide6.QtQuick import QQuickItem, QQuickPaintedItem

from epub_reader.rendering.engine import NativeBookEngine

QML_IMPORT_NAME = "Epubify.Native"
QML_IMPORT_MAJOR_VERSION = 1


@QmlElement
class BookPage(QQuickPaintedItem):
    rendererChanged = Signal()
    linkActivated = Signal(str)
    pageTurnRequested = Signal(int)
    slideProgressChanged = Signal()

    def __init__(self, parent: QQuickItem | None = None) -> None:
        super().__init__(parent)
        self._renderer: NativeBookEngine | None = None
        self._press_position = QPointF()
        self._turn_image = QImage()
        self._slide_progress = 1.0
        self._turn_direction = 1
        self.setAntialiasing(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self._resize = QTimer(self)
        self._resize.setSingleShot(True)
        self._resize.setInterval(60)
        self._resize.timeout.connect(self._layout)
        self.widthChanged.connect(self._resize.start)
        self.heightChanged.connect(self._resize.start)
        self.windowChanged.connect(self._window_changed)

    def get_renderer(self) -> QObject | None:
        return self._renderer

    def set_renderer(self, value: QObject | None) -> None:
        if self._renderer is not None:
            self._renderer.changed.disconnect(self._repaint)
        self._renderer = value if isinstance(value, NativeBookEngine) else None
        if self._renderer is not None:
            self._renderer.changed.connect(self._repaint)
        self._resize.start()
        self.rendererChanged.emit()
        self.update()

    renderer = Property(QObject, get_renderer, set_renderer, notify=rendererChanged)

    def _window_changed(self) -> None:
        window = self.window()
        if window is not None:
            window.screenChanged.connect(self._resize.start)
        self._resize.start()

    @Slot()
    def _layout(self) -> None:
        if self._renderer is None or self.width() < 100 or self.height() < 100:
            return
        window = self.window()
        self.finishTurn()
        dpr = window.effectiveDevicePixelRatio() if window is not None else 1.0
        self._renderer.set_viewport(round(self.width()), round(self.height()), dpr)

    @Slot()
    def _repaint(self) -> None:
        self.update()

    def paint(self, painter: QPainter) -> None:
        # This callback can run on Qt's render thread. It only reads an immutable
        # page image; document layout and resource loading stay on the GUI thread.
        if self._renderer is not None and not self._renderer.image.isNull():
            painter.drawImage(self.boundingRect(), self._renderer.image)
            if not self._turn_image.isNull() and self._slide_progress < 1:
                width, height = self.width(), self.height()
                painter.save()
                painter.setClipRect(self.boundingRect())
                if self._turn_direction > 0:
                    # Higher-numbered pages arrive on top from the right.
                    painter.drawImage(self.boundingRect(), self._turn_image)
                    offset = width * (1 - self._slide_progress)
                    moving = self._renderer.image
                else:
                    # Remove the higher page to the right; the earlier one stays below.
                    offset = width * self._slide_progress
                    moving = self._turn_image
                shadow = QLinearGradient(offset - 14, 0, offset, 0)
                shadow.setColorAt(0, QColor(0, 0, 0, 0))
                shadow.setColorAt(1, QColor(0, 0, 0, 55))
                painter.fillRect(QRectF(offset - 14, 0, 14, height), shadow)
                painter.drawImage(QRectF(offset, 0, width, height), moving)
                painter.restore()

    def get_slide_progress(self) -> float:
        return self._slide_progress

    def set_slide_progress(self, value: float) -> None:
        self._slide_progress = min(1.0, max(0.0, value))
        self.slideProgressChanged.emit()
        self.update()

    slideProgress = Property(
        float, get_slide_progress, set_slide_progress, notify=slideProgressChanged
    )

    @Slot(int)
    def prepareTurn(self, direction: int) -> None:
        self._turn_direction = direction
        # QImage shares immutable pixel data until written; no large bridge transfer.
        self._turn_image = QImage(self._renderer.image) if self._renderer else QImage()
        self.set_slide_progress(0.0)

    @Slot()
    def finishTurn(self) -> None:
        self._turn_image = QImage()
        self.set_slide_progress(1.0)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        delta = event.position() - self._press_position
        if abs(delta.x()) >= 48 and abs(delta.x()) > abs(delta.y()) * 1.5:
            self.pageTurnRequested.emit(1 if delta.x() < 0 else -1)
        elif self._renderer is not None and delta.manhattanLength() < 16:
            href = self._renderer.link_at(event.position().x(), event.position().y())
            if href:
                self.linkActivated.emit(href)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._press_position = event.position()
        event.accept()

    def hoverMoveEvent(self, event: QHoverEvent) -> None:
        href = (
            self._renderer.link_at(event.position().x(), event.position().y())
            if self._renderer
            else ""
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor if href else Qt.CursorShape.ArrowCursor)

    def hoverLeaveEvent(self, event: QHoverEvent) -> None:
        self.unsetCursor()

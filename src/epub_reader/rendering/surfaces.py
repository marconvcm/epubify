"""Deterministic native page materials; no external bitmap assets or downloads."""

from dataclasses import dataclass
from functools import lru_cache
from random import Random

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen

from epub_reader.core.design import DEFAULT_SCHEME, palette_for, scheme_for


@dataclass(frozen=True)
class Surface:
    key: str
    label: str
    background: str
    foreground: str
    accent: str
    pattern: str = "plain"


SURFACE_KEYS = ("plain", "paper", "sepia", "slate", "grid", "dots")


def surface_for(key: str, dark: bool, scheme: str = DEFAULT_SCHEME) -> Surface:
    palette = palette_for(dark, scheme)
    background, text, accent = palette.background, palette.text, palette.accent
    options = {
        "plain": Surface("plain", "Classic", background, text, accent),
        "grid": Surface("grid", "Grid", background, text, accent, "grid"),
        "dots": Surface("dots", "Dots", background, text, accent, "dots"),
    }
    for style in ("paper", "sepia", "slate"):
        options[style] = Surface(
            style, style.title(), **scheme_for(scheme).reading[style], pattern="grain"
        )
    return options.get(key, options["plain"])


@lru_cache(maxsize=16)
def _grain(background: str) -> QImage:
    image = QImage(96, 96, QImage.Format.Format_RGB32)
    base = QColor(background)
    random = Random(1729)
    for y in range(image.height()):
        for x in range(image.width()):
            delta = random.choice((-3, -2, -1, 0, 0, 0, 1, 2, 3))
            image.setPixelColor(
                x,
                y,
                QColor(
                    max(0, min(255, base.red() + delta)),
                    max(0, min(255, base.green() + delta)),
                    max(0, min(255, base.blue() + delta)),
                ),
            )
    return image


def paint_surface(painter: QPainter, rect: QRectF, surface: Surface) -> None:
    painter.save()
    painter.fillRect(rect, QColor(surface.background))
    if surface.pattern == "grain":
        painter.fillRect(rect, QBrush(_grain(surface.background)))
    elif surface.pattern in ("grid", "dots"):
        color = QColor(surface.foreground)
        color.setAlpha(13 if surface.pattern == "grid" else 24)
        painter.setPen(QPen(color, 0.55))
        painter.setBrush(color)
        step = 24
        if surface.pattern == "grid":
            for x in range(0, int(rect.width()) + step, step):
                painter.drawLine(x, 0, x, int(rect.height()))
            for y in range(0, int(rect.height()) + step, step):
                painter.drawLine(0, y, int(rect.width()), y)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            for x in range(12, int(rect.width()), step):
                for y in range(12, int(rect.height()), step):
                    painter.drawEllipse(QRectF(x, y, 1.25, 1.25))
    painter.restore()

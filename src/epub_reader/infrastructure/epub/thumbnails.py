import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImageReader

from epub_reader.domain.models.book import Book

logger = logging.getLogger(__name__)


def thumbnail_path(book: Book) -> Path:
    # Outside extracted files: a publication cannot provide its own cached thumbnail.
    return book.storage_path.parent.parent / "covers" / f"{book.id}.png"


def create_thumbnail(book: Book) -> None:
    """Run in the import worker. Decode a bounded raster, then cache at display size."""
    if book.cover_path is None:
        return
    target = thumbnail_path(book)
    if target.exists():
        return
    reader = QImageReader(str(book.cover_path))
    size = reader.size()
    if (
        not size.isValid()
        or size.width() > 16000
        or size.height() > 16000
        or size.width() * size.height() > 40_000_000
    ):
        logger.info("Skipping an oversized or invalid cover for %s", book.id)
        return
    reader.setAutoTransform(True)
    reader.setScaledSize(size.scaled(QSize(420, 560), Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    # Infer PNG from the suffix: PySide's explicit format argument differs between
    # runtime conversion and its generated stub in some releases.
    temporary = target.with_suffix(".tmp.png")
    if image.save(str(temporary)):
        temporary.replace(target)

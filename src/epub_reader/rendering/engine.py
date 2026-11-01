import bisect
from collections import defaultdict, deque

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, QSizeF, Qt, QUrl, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
)

from epub_reader.core.design import DEFAULT_SCHEME, scheme_for
from epub_reader.core.typography import (
    MONO_FALLBACKS,
    MONO_FAMILY,
    READING_FALLBACKS,
    register_fonts,
)
from epub_reader.domain.models.book import Book
from epub_reader.domain.models.reading_progress import ReadingLocation
from epub_reader.infrastructure.epub.extraction import EpubError
from epub_reader.rendering.document import PublicationDocument, chapter_markup
from epub_reader.rendering.publication import Publication, load_publication, reference
from epub_reader.rendering.surfaces import SURFACE_KEYS, paint_surface, surface_for


class NativeBookEngine(QObject):
    """Owns Qt layout, pagination, stable text offsets and cached native page images."""

    changed = Signal()
    relocated = Signal(str, float)

    def __init__(self) -> None:
        super().__init__()
        register_fonts()
        self.publication: Publication | None = None
        self.document: PublicationDocument | None = None
        self.chapter_index = 0
        self.page = 0
        self.pages = 1
        self.starts = [0]
        self.anchor_offset = 0
        self.width, self.height, self.dpr = 900, 650, 1.0
        self.font_size, self.dark = 20, True
        self.surface = "plain"
        self.color_scheme = DEFAULT_SCHEME
        self.anchors: dict[str, int] = {}
        self.image = QImage()

    @property
    def page_height(self) -> int:
        return max(100, self.height - 64)

    @property
    def text_width(self) -> int:
        margin = 24 if self.width < 600 else 48
        return min(760, max(120, self.width - 2 * margin))

    @property
    def location(self) -> ReadingLocation:
        if self.publication is None:
            raise ValueError("No publication is open.")
        return ReadingLocation(
            self.publication.chapters[self.chapter_index].path, self.anchor_offset
        )

    def open(self, book: Book) -> None:
        self.publication = load_publication(book.storage_path, book.package_path)
        self.chapter_index, self.anchor_offset = 0, 0
        if book.location:
            try:
                location = ReadingLocation.decode(book.location)
                self.chapter_index = next(
                    i for i, c in enumerate(self.publication.chapters) if c.path == location.chapter
                )
                self.anchor_offset = location.offset
            except (ValueError, StopIteration):
                self.chapter_index, self.anchor_offset = 0, 0
        self._layout()

    def close(self) -> None:
        self.document = None
        self.publication = None
        self.image = QImage()
        self.changed.emit()

    def seek(self, location: ReadingLocation) -> None:
        if self.publication is None:
            return
        paths = [chapter.path for chapter in self.publication.chapters]
        if location.chapter not in paths:
            raise EpubError("This link does not point to a reading chapter.")
        self.chapter_index = paths.index(location.chapter)
        self.anchor_offset = location.offset
        self._layout()

    def configure(
        self,
        font_size: int,
        dark: bool,
        surface: str | None = None,
        color_scheme: str | None = None,
    ) -> None:
        surface = self.surface if surface is None else surface
        color_scheme = self.color_scheme if color_scheme is None else color_scheme
        scheme_for(color_scheme)
        if surface not in SURFACE_KEYS:
            raise ValueError("Unknown reading surface.")
        if (self.font_size, self.dark, self.surface, self.color_scheme) != (
            font_size,
            dark,
            surface,
            color_scheme,
        ):
            self.font_size, self.dark, self.surface = font_size, dark, surface
            self.color_scheme = color_scheme
            if self.publication:
                self._layout()

    def set_viewport(self, width: int, height: int, dpr: float = 1.0) -> None:
        width, height = max(220, width), max(180, height)
        dpr = max(1.0, min(4.0, dpr))
        if (width, height, dpr) == (self.width, self.height, self.dpr):
            return
        self.width, self.height, self.dpr = width, height, dpr
        if self.publication:
            self._layout()

    def _layout(self) -> None:
        if self.publication is None:
            return
        chapter = self.publication.chapters[self.chapter_index]
        markup, css, image_targets, navigation = chapter_markup(
            self.publication.root, chapter.path, self.publication
        )
        targets: dict[str, deque[tuple[str, ...]]] = defaultdict(deque)
        for target in image_targets:
            targets[target.source].append(target.names)
        image_anchors: dict[str, int] = {}
        document = PublicationDocument(
            self.publication.root,
            chapter.path,
            QSize(self.text_width, self.page_height - self.font_size * 2),
        )
        font = QFont()
        font.setFamilies(READING_FALLBACKS)
        font.setPixelSize(self.font_size)
        document.setDefaultFont(font)
        document.setDefaultStyleSheet(css)
        document.setPageSize(QSizeF(self.text_width, self.page_height))
        document.setHtml(markup)
        self._apply_typefaces(document)
        # Explicit EPUB image dimensions must fit the native page as well as the
        # decoded bitmap. Leave room for Qt's inline-object baseline/descent.
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.charFormat().isImageFormat():
                    image_format = fragment.charFormat().toImageFormat()
                    if targets[image_format.name()]:
                        for name in targets[image_format.name()].popleft():
                            image_anchors[name] = fragment.position()
                    resource = document.resource(
                        PublicationDocument.ResourceType.ImageResource,
                        document.baseUrl().resolved(QUrl(image_format.name())),
                    )
                    if isinstance(resource, QImage) and not resource.isNull():
                        width = image_format.width() or resource.width()
                        height = image_format.height() or resource.height()
                        factor = min(
                            1,
                            self.text_width / width,
                            (self.page_height - self.font_size * 2) / height,
                        )
                        image_format.setWidth(width * factor)
                        image_format.setHeight(height * factor)
                        image_cursor = QTextCursor(document)
                        image_cursor.setPosition(fragment.position())
                        image_cursor.setPosition(
                            fragment.position() + fragment.length(), QTextCursor.MoveMode.KeepAnchor
                        )
                        image_cursor.setCharFormat(image_format)
                iterator += 1
            block = block.next()
        # Keep structural EPUB CSS while applying the user's typography and palette.
        cursor = QTextCursor(document)
        cursor.select(QTextCursor.SelectionType.Document)
        char_format = QTextCharFormat()
        palette = surface_for(self.surface, self.dark, self.color_scheme)
        char_format.setForeground(QColor(palette.foreground))
        char_format.setBackground(QBrush(Qt.BrushStyle.NoBrush))
        char_format.setFontPointSize(self.font_size * 0.75)
        cursor.mergeCharFormat(char_format)
        block = document.begin()
        while block.isValid():
            block_cursor = QTextCursor(block)
            block_format = block.blockFormat()
            names = list(block.charFormat().anchorNames())
            fragments = block.begin()
            while not fragments.atEnd():
                names.extend(fragments.fragment().charFormat().anchorNames())
                fragments += 1
            nav_style = next((navigation[name] for name in names if name in navigation), None)
            image_only = not block.text().strip("\ufffc \t\n")
            block_format.setLineHeight(
                100 if image_only else 165,
                QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
            )
            if image_only:
                block_format.setTopMargin(0)
                block_format.setBottomMargin(0)
            if nav_style:
                if block.textList() is not None:
                    block.textList().remove(block)
                block_format.setObjectIndex(-1)
                block_format.setIndent(0)
                block_format.setTextIndent(0)
                block_format.setLeftMargin(nav_style.depth * self.font_size * 1.25)
                block_format.setRightMargin(0)
                block_format.setLineHeight(
                    125, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
                )
                block_format.setTopMargin(
                    self.font_size
                    * (0.6 if nav_style.kind != "entry" or nav_style.depth == 0 else 0.1)
                )
                block_format.setBottomMargin(
                    self.font_size * (0.65 if nav_style.kind == "title" else 0.2)
                )
                block_format.setNonBreakableLines(False)
            block_format.setBackground(QBrush(Qt.BrushStyle.NoBrush))
            block_cursor.setBlockFormat(block_format)
            level = block_format.headingLevel()
            if nav_style or level:
                block_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                heading = QTextCharFormat()
                scale = (
                    (1.5 if nav_style.kind == "title" else 1.0)
                    if nav_style
                    else max(1.1, 1.9 - level * 0.15)
                )
                heading.setFontPointSize(self.font_size * 0.75 * scale)
                heading.setFontWeight(
                    QFont.Weight.DemiBold
                    if not nav_style or nav_style.depth == 0 or nav_style.kind != "entry"
                    else QFont.Weight.Normal
                )
                if nav_style:
                    # Qt keeps relative heading adjustments and CSS pixel sizes
                    # alongside point size. Remove those competing properties
                    # on each fragment while preserving links and named anchors.
                    separator_format = block.charFormat()
                    separator_format.clearProperty(QTextFormat.Property.FontSizeAdjustment)
                    separator_format.clearProperty(QTextFormat.Property.FontPixelSize)
                    separator_format.merge(heading)
                    block_cursor.setPosition(block.position())
                    block_cursor.setBlockCharFormat(separator_format)
                    fragments = block.begin()
                    formats: list[tuple[int, int, QTextCharFormat]] = []
                    while not fragments.atEnd():
                        fragment = fragments.fragment()
                        fmt = fragment.charFormat()
                        fmt.clearProperty(QTextFormat.Property.FontSizeAdjustment)
                        fmt.clearProperty(QTextFormat.Property.FontPixelSize)
                        fmt.merge(heading)
                        formats.append((fragment.position(), fragment.length(), fmt))
                        fragments += 1
                    for position, length, fmt in formats:
                        block_cursor.setPosition(position)
                        block_cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
                        block_cursor.setCharFormat(fmt)
                else:
                    block_cursor.mergeCharFormat(heading)
            block = block.next()
        frame_format = document.rootFrame().frameFormat()
        frame_format.setBackground(QBrush(Qt.BrushStyle.NoBrush))
        document.rootFrame().setFrameFormat(frame_format)
        self.anchors = image_anchors
        links: list[tuple[int, int]] = []
        block = document.begin()
        while block.isValid():
            for name in block.charFormat().anchorNames():
                self.anchors.setdefault(name, block.position())
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                for name in fragment.charFormat().anchorNames():
                    self.anchors.setdefault(name, fragment.position())
                if fragment.charFormat().anchorHref():
                    links.append((fragment.position(), fragment.length()))
                iterator += 1
            block = block.next()
        for position, length in links:
            cursor = QTextCursor(document)
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            link_format = QTextCharFormat()
            link_format.setForeground(QColor(palette.accent))
            link_format.setFontUnderline(True)
            cursor.mergeCharFormat(link_format)
        self.document = document
        document.documentLayout().documentSize()  # Materialize layout/resources on the GUI thread.
        self.pages = max(1, document.pageCount())
        self.starts = [
            max(
                0,
                document.documentLayout().hitTest(
                    QPointF(0, page * self.page_height + 1), Qt.HitTestAccuracy.FuzzyHit
                ),
            )
            for page in range(self.pages)
        ]
        self.anchor_offset = min(self.anchor_offset, max(0, document.characterCount() - 1))
        cursor = QTextCursor(document)
        cursor.setPosition(self.anchor_offset)
        block = cursor.block()
        line = block.layout().lineForTextPosition(cursor.positionInBlock())
        y = document.documentLayout().blockBoundingRect(block).top()
        if line.isValid():
            y += line.y()
        self.page = min(self.pages - 1, max(0, int(y // self.page_height)))
        self._render()

    def _apply_typefaces(self, document: PublicationDocument) -> None:
        block = document.begin()
        cursor = QTextCursor(document)
        while block.isValid():
            fragments = block.begin()
            formats: list[tuple[int, int, QTextCharFormat]] = []
            while not fragments.atEnd():
                fragment = fragments.fragment()
                fmt = fragment.charFormat()
                families = fmt.fontFamilies() or []
                mono = fmt.fontFixedPitch() or any(
                    family.casefold()
                    in {MONO_FAMILY.casefold(), "monospace", "courier", "courier new", "consolas"}
                    for family in families
                )
                fmt.setFontFamilies(MONO_FALLBACKS if mono else READING_FALLBACKS)
                fmt.setFontFixedPitch(mono)
                fmt.clearProperty(QTextFormat.Property.FontPixelSize)
                fmt.clearProperty(QTextFormat.Property.FontSizeAdjustment)
                fmt.setFontPointSize(self.font_size * 0.75)
                formats.append((fragment.position(), fragment.length(), fmt))
                fragments += 1
            for position, length, fmt in formats:
                cursor.setPosition(position)
                cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(fmt)
            separator_format = block.charFormat()
            separator_format.setFontFamilies(READING_FALLBACKS)
            separator_format.clearProperty(QTextFormat.Property.FontPixelSize)
            separator_format.clearProperty(QTextFormat.Property.FontSizeAdjustment)
            separator_format.setFontPointSize(self.font_size * 0.75)
            cursor.setPosition(block.position())
            cursor.setBlockCharFormat(separator_format)
            block = block.next()

    def _render(self) -> None:
        if self.document is None or self.publication is None:
            return
        image = QImage(
            round(self.width * self.dpr),
            round(self.height * self.dpr),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.setDevicePixelRatio(self.dpr)
        painter = QPainter(image)
        paint_surface(
            painter,
            QRectF(0, 0, self.width, self.height),
            surface_for(self.surface, self.dark, self.color_scheme),
        )
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setClipRect(
            QRectF((self.width - self.text_width) / 2, 32, self.text_width, self.page_height)
        )
        painter.translate((self.width - self.text_width) / 2, 32 - self.page * self.page_height)
        self.document.drawContents(
            painter, QRectF(0, self.page * self.page_height, self.text_width, self.page_height)
        )
        painter.end()
        self.image = image
        self.changed.emit()
        fraction = (self.chapter_index + self.page / self.pages) / len(self.publication.chapters)
        if self.chapter_index == len(self.publication.chapters) - 1 and self.page == self.pages - 1:
            fraction = 1.0
        self.relocated.emit(self.location.encode(), fraction)

    def next(self) -> None:
        if not self.publication:
            return
        if self.page + 1 < self.pages:
            self.page += 1
            self.anchor_offset = self.starts[self.page]
            self._render()
        elif self.chapter_index + 1 < len(self.publication.chapters):
            self.chapter_index += 1
            self.anchor_offset = 0
            self._layout()

    def previous(self) -> None:
        if not self.publication:
            return
        if self.page > 0:
            self.page -= 1
            self.anchor_offset = self.starts[self.page]
            self._render()
        elif self.chapter_index > 0:
            self.chapter_index -= 1
            self.anchor_offset = 0
            self._layout()
            self.page = self.pages - 1
            self.anchor_offset = self.starts[self.page]
            self._render()

    def navigate(self, href: str) -> None:
        if not self.publication:
            return
        paths = [chapter.path for chapter in self.publication.chapters]
        path, _, fragment = href.partition("#")
        target = href if path in paths else reference(paths[self.chapter_index], href)
        path, _, fragment = target.partition("#")
        if path not in paths:
            raise EpubError("This link does not point to a reading chapter.")
        self.chapter_index, self.anchor_offset = paths.index(path), 0
        self._layout()
        if fragment in self.anchors:
            self.anchor_offset = self.anchors[fragment]
            self.page = max(0, bisect.bisect_right(self.starts, self.anchor_offset) - 1)
            self._render()

    def link_at(self, x: float, y: float) -> str:
        if self.document is None:
            return ""
        return self.document.documentLayout().anchorAt(
            QPointF(x - (self.width - self.text_width) / 2, y - 32 + self.page * self.page_height)
        )

    def page_text(self) -> str:
        if self.document is None:
            return ""
        cursor = QTextCursor(self.document)
        cursor.setPosition(self.starts[self.page])
        end = (
            self.starts[self.page + 1]
            if self.page + 1 < len(self.starts)
            else self.document.characterCount() - 1
        )
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        return cursor.selectedText().replace("\u2029", "\n")

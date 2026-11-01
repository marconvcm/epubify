from typing import Any

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    QUrl,
    Signal,
    Slot,
)

from epub_reader.domain.models.book import Book
from epub_reader.infrastructure.epub.thumbnails import thumbnail_path
from epub_reader.services.library_service import LibraryService

ROOT_INDEX = QModelIndex()


class BookListModel(QAbstractListModel):
    bookChanged = Signal(object)
    ROLES = {
        Qt.ItemDataRole.UserRole + i: name
        for i, name in enumerate(
            (b"bookId", b"bookTitle", b"author", b"coverUrl", b"progressValue", b"favorite"),
            start=1,
        )
    }

    def __init__(self, books: list[Book]) -> None:
        super().__init__()
        self.books = books

    def roleNames(self) -> dict[int, QByteArray]:
        return {int(key): QByteArray(value) for key, value in self.ROLES.items()}

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = ROOT_INDEX) -> int:
        return 0 if parent.isValid() else len(self.books)

    def data(
        self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self.books):
            return None
        book = self.books[index.row()]
        values = {
            b"bookId": book.id,
            b"bookTitle": book.title,
            b"author": book.author,
            b"coverUrl": (
                QUrl.fromLocalFile(str(thumbnail_path(book)))
                if thumbnail_path(book).is_file()
                else QUrl()
            ),
            b"progressValue": book.progress,
            b"favorite": book.favorite,
        }
        return values.get(self.ROLES.get(role, b""))

    def upsert(self, book: Book) -> None:
        for row, existing in enumerate(self.books):
            if existing.id == book.id:
                self.books[row] = book
                self.dataChanged.emit(self.index(row), self.index(row), list(self.ROLES))
                self.bookChanged.emit(book)
                return
        self.beginInsertRows(QModelIndex(), 0, 0)
        self.books.insert(0, book)
        self.endInsertRows()
        self.bookChanged.emit(book)


class BookFilterModel(QSortFilterProxyModel):
    def __init__(self, source: BookListModel) -> None:
        super().__init__()
        self.library = source
        self.query = ""
        self.category = ""
        self.favorites_only = False
        self.setSourceModel(source)

    @Slot(str)
    def search(self, query: str) -> None:
        self.beginFilterChange()
        self.query = query
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(
        self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex
    ) -> bool:
        book = self.library.books[source_row]
        category_match = not self.category or (
            not book.categories
            if self.category == "uncategorized"
            else any(c.id == self.category for c in book.categories)
        )
        return (
            category_match
            and (not self.favorites_only or book.favorite)
            and LibraryService.matches(book, self.query)
        )

    def select_category(self, identifier: str) -> None:
        self.beginFilterChange()
        self.category = identifier
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

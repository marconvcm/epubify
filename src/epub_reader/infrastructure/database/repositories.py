import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from epub_reader.domain.models.book import Book
from epub_reader.domain.models.category import Category
from epub_reader.domain.models.reading_progress import ReadingProgress
from epub_reader.infrastructure.database.models import BookRow, PreferenceRow


def to_book(row: BookRow) -> Book:
    return Book(
        id=row.id,
        title=row.title,
        author=row.author,
        storage_path=Path(row.storage_path),
        package_path=row.package_path,
        imported_at=row.imported_at.replace(tzinfo=UTC),
        cover_path=Path(row.cover_path) if row.cover_path else None,
        last_opened_at=row.last_opened_at.replace(tzinfo=UTC) if row.last_opened_at else None,
        progress=row.progress,
        location=row.location,
        categories=tuple(Category(**category) for category in json.loads(row.categories)),
        classification_version=row.classification_version,
        favorite=row.favorite,
    )


class SqlBookRepository:
    """Short-lived sessions; the engine can be shared with import workers."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list(self) -> list[Book]:
        with Session(self.engine) as session:
            rows = session.scalars(select(BookRow).order_by(BookRow.imported_at.desc(), BookRow.id))
            return [to_book(row) for row in rows]

    def get(self, book_id: str) -> Book | None:
        with Session(self.engine) as session:
            row = session.get(BookRow, book_id)
            return to_book(row) if row else None

    def add(self, book: Book) -> Book:
        with Session(self.engine) as session, session.begin():
            existing = session.get(BookRow, book.id)
            if existing:
                return to_book(existing)
            session.add(
                BookRow(
                    id=book.id,
                    title=book.title,
                    author=book.author,
                    storage_path=str(book.storage_path),
                    package_path=book.package_path,
                    cover_path=str(book.cover_path) if book.cover_path else None,
                    imported_at=book.imported_at,
                    last_opened_at=book.last_opened_at,
                    progress=book.progress,
                    location=book.location,
                    categories=json.dumps([{"id": c.id, "name": c.name} for c in book.categories]),
                    classification_version=book.classification_version,
                    favorite=book.favorite,
                )
            )
        return book

    def delete(self, book_id: str) -> None:
        with Session(self.engine) as session, session.begin():
            row = session.get(BookRow, book_id)
            if row:
                session.delete(row)

    def mark_opened(self, book_id: str) -> Book:
        with Session(self.engine) as session, session.begin():
            row = session.get(BookRow, book_id)
            if row is None:
                raise KeyError(book_id)
            row.last_opened_at = datetime.now(UTC)
            return to_book(row)

    def save_progress(self, book_id: str, progress: ReadingProgress) -> Book:
        with Session(self.engine) as session, session.begin():
            row = session.get(BookRow, book_id)
            if row is None:
                raise KeyError(book_id)
            row.progress, row.location = progress.fraction, progress.location
            return to_book(row)

    def save_categories(self, book_id: str, categories: tuple[Category, ...], version: int) -> Book:
        with Session(self.engine) as session, session.begin():
            row = session.get(BookRow, book_id)
            if row is None:
                raise KeyError(book_id)
            row.categories = json.dumps([{"id": c.id, "name": c.name} for c in categories])
            row.classification_version = version
            return to_book(row)

    def set_favorite(self, book_id: str, favorite: bool) -> Book:
        with Session(self.engine) as session, session.begin():
            row = session.get(BookRow, book_id)
            if row is None:
                raise KeyError(book_id)
            row.favorite = favorite
            return to_book(row)


class PreferenceRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get(self, key: str, default: str | bool | int) -> str | bool | int:
        with Session(self.engine) as session:
            row = session.get(PreferenceRow, key)
            if row is None:
                return default
            try:
                value: object = json.loads(row.value)
            except (ValueError, TypeError):
                return default
            # Do not allow malformed local preferences to change their expected type.
            if type(value) is type(default) and isinstance(value, (str, bool, int)):
                return value
            return default

    def set(self, key: str, value: str | bool | int) -> None:
        with Session(self.engine) as session, session.begin():
            session.merge(PreferenceRow(key=key, value=json.dumps(value)))

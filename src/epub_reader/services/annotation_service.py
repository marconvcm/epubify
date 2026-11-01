import uuid

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from epub_reader.domain.models.reading_progress import ReadingLocation
from epub_reader.infrastructure.database.sync_models import AnnotationRow


class AnnotationService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def notes(self, book_id: str) -> list[dict[str, str]]:
        with Session(self.engine) as session:
            return [
                {"id": row.id, "text": row.text, "location": row.location}
                for row in session.scalars(
                    select(AnnotationRow)
                    .where(AnnotationRow.book_id == book_id, AnnotationRow.deleted.is_(False))
                    .order_by(AnnotationRow.id)
                )
            ]

    def add(self, book_id: str, location: str, text: str) -> None:
        ReadingLocation.decode(location)
        text = text.strip()
        if not text or len(text) > 16000:
            raise ValueError("Write a note of up to 16,000 characters.")
        with Session(self.engine) as session, session.begin():
            session.add(
                AnnotationRow(
                    id=str(uuid.uuid4()),
                    book_id=book_id,
                    location=location,
                    text=text,
                    deleted=False,
                )
            )

    def remove(self, book_id: str, identifier: str) -> None:
        with Session(self.engine) as session, session.begin():
            row = session.get(AnnotationRow, identifier)
            if row is not None and row.book_id == book_id:
                row.deleted = True

    def update(self, book_id: str, identifier: str, text: str) -> None:
        text = text.strip()
        if not text or len(text) > 16000:
            raise ValueError("Write a note of up to 16,000 characters.")
        with Session(self.engine) as session, session.begin():
            row = session.get(AnnotationRow, identifier)
            if row is None or row.book_id != book_id or row.deleted:
                raise ValueError("This note is no longer available.")
            row.text = text

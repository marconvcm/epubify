"""Durable signed registers and atomic projections into the local library."""

import json
import logging
import threading
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from epub_reader.core.design import available_schemes
from epub_reader.infrastructure.database.models import BookRow, PreferenceRow
from epub_reader.infrastructure.database.repositories import SqlBookRepository
from epub_reader.infrastructure.database.sync_models import (
    AnnotationRow,
    SyncBookMapRow,
    SyncHeadRow,
    SyncPeerRow,
    SyncProjectionRow,
    SyncVersionRow,
)
from epub_reader.infrastructure.epub.exchange import content_id, export_publication
from epub_reader.infrastructure.epub.thumbnails import create_thumbnail
from epub_reader.infrastructure.sync.crypto import Identity, verify_record
from epub_reader.infrastructure.sync.records import (
    PREFERENCES,
    Record,
    SyncError,
    canonical,
    digest,
    surviving_heads,
    valid_id,
    winner,
)
from epub_reader.services.epub_import_service import EpubImportService

logger = logging.getLogger(__name__)


class SyncStore:
    def __init__(self, engine: Engine, root: Path, identity: Identity) -> None:
        self.engine, self.root, self.identity = engine, root, identity
        self.books = SqlBookRepository(engine)
        self.importer = EpubImportService(self.books, root / "books")
        self.lock = threading.RLock()

    def _heads(self, session: Session, kind: str, key: str) -> list[Record]:
        row = session.get(SyncHeadRow, (kind, key))
        if row is None:
            return []
        versions = [session.get(SyncVersionRow, identifier) for identifier in json.loads(row.heads)]
        return [
            Record.parse(json.loads(version.record), check_clock=False)
            for version in versions
            if version is not None
        ]

    def _project(self, session: Session, record: Record) -> bool:
        value = record.value
        if record.kind == "preference":
            if record.key == "color_scheme" and value["value"] not in {
                scheme["id"] for scheme in available_schemes()
            }:
                return False
            session.merge(PreferenceRow(key=record.key, value=json.dumps(value["value"])))
        else:
            identifier = record.key if record.kind != "annotation" else value["book"]
            mapping = session.scalar(
                select(SyncBookMapRow).where(SyncBookMapRow.content_id == identifier)
            )
            if mapping is None:
                return False
            book = session.get(BookRow, mapping.book_id)
            if book is None:
                return False
            if record.kind == "book":
                book.favorite = value["favorite"]
            elif record.kind == "progress":
                book.location, book.progress = value["location"], float(value["fraction"])
            elif record.kind == "annotation":
                session.merge(
                    AnnotationRow(
                        id=record.key,
                        book_id=book.id,
                        location=value["location"],
                        text=value["text"],
                        deleted=value["deleted"],
                    )
                )
        session.merge(
            SyncProjectionRow(kind=record.kind, entity_key=record.key, value_hash=digest(value))
        )
        return True

    def _retain(self, session: Session, record: Record, *, remote: bool) -> bool:
        heads = self._heads(session, record.kind, record.key)
        merged = surviving_heads(heads, record)
        if {item.id for item in merged} == {item.id for item in heads}:
            return False
        if len(merged) > 32 or (
            not heads
            and (session.scalar(select(func.count()).select_from(SyncHeadRow)) or 0) >= 10000
        ):
            raise SyncError("Synchronization entity limit reached.")
        if (session.scalar(select(func.count()).select_from(SyncVersionRow)) or 0) >= 100000:
            raise SyncError("Synchronization history reached its storage limit.")
        session.merge(
            SyncVersionRow(
                id=record.id,
                kind=record.kind,
                entity_key=record.key,
                record=canonical(record.wire()).decode(),
            )
        )
        session.merge(
            SyncHeadRow(
                kind=record.kind,
                entity_key=record.key,
                heads=json.dumps([item.id for item in merged]),
            )
        )
        if remote:
            self._project(session, winner(merged))
        else:
            session.merge(
                SyncProjectionRow(
                    kind=record.kind, entity_key=record.key, value_hash=digest(record.value)
                )
            )
        return True

    def _local(
        self, session: Session, kind: str, key: str, value: dict[str, Any], force: bool = False
    ) -> bool:
        projected = session.get(SyncProjectionRow, (kind, key))
        if not force and projected is not None and projected.value_hash == digest(value):
            return False
        vector: dict[str, int] = {}
        for head in self._heads(session, kind, key):
            for device, sequence in head.vector.items():
                vector[device] = max(vector.get(device, 0), sequence)
        vector[self.identity.id] = vector.get(self.identity.id, 0) + 1
        record = self.identity.record(kind, key, value, vector)
        record.validate_value()
        return self._retain(session, record, remote=False)

    def snapshot(self) -> None:
        with self.lock:
            for book in self.books.list():
                if not (book.storage_path / book.package_path).is_file():
                    continue
                with Session(self.engine) as session:
                    mapping = session.get(SyncBookMapRow, book.id)
                    identifier = mapping.content_id if mapping else None
                if identifier is None:
                    identifier = content_id(book.storage_path)
                    with Session(self.engine) as session, session.begin():
                        other = session.scalar(
                            select(SyncBookMapRow).where(SyncBookMapRow.content_id == identifier)
                        )
                        if other is not None and other.book_id != book.id:
                            continue
                        session.merge(SyncBookMapRow(book_id=book.id, content_id=identifier))
                with Session(self.engine) as session, session.begin():
                    self._local(
                        session,
                        "book",
                        identifier,
                        {"title": book.title, "author": book.author, "favorite": book.favorite},
                    )
                    self._local(
                        session,
                        "progress",
                        identifier,
                        {"location": book.location, "fraction": book.progress},
                    )
            with Session(self.engine) as session, session.begin():
                for row in session.scalars(
                    select(PreferenceRow).where(PreferenceRow.key.in_(PREFERENCES))
                ):
                    self._local(session, "preference", row.key, {"value": json.loads(row.value)})
                for note in session.scalars(select(AnnotationRow)):
                    mapping = session.get(SyncBookMapRow, note.book_id)
                    if mapping is not None:
                        self._local(
                            session,
                            "annotation",
                            note.id,
                            {
                                "book": mapping.content_id,
                                "location": note.location,
                                "text": note.text,
                                "deleted": note.deleted,
                            },
                        )

    def records(self) -> list[Record]:
        with self.lock, Session(self.engine) as session:
            records = []
            for row in session.scalars(select(SyncHeadRow)):
                records.extend(self._heads(session, row.kind, row.entity_key))
            return records

    def merge(self, data: dict[str, Any]) -> dict[str, list[str]]:
        record = Record.parse(data)
        verify_record(record)
        with self.lock:
            # Capture local edits before applying an incoming branch.
            self.snapshot()
            return self._merge_verified(record)

    def _merge_verified(self, record: Record) -> dict[str, list[str]]:
        with Session(self.engine) as session, session.begin():
            revoked = session.get(SyncPeerRow, record.author)
            if revoked is not None and not revoked.enabled:
                return {"books": [], "preferences": []}
            changed = self._retain(session, record, remote=True)
            book_ids: list[str] = []
            if changed and record.kind != "preference":
                identifier = record.key if record.kind != "annotation" else record.value["book"]
                mapping = session.scalar(
                    select(SyncBookMapRow).where(SyncBookMapRow.content_id == identifier)
                )
                if mapping:
                    book_ids.append(mapping.book_id)
            return {
                "books": book_ids,
                "preferences": [record.key] if changed and record.kind == "preference" else [],
            }

    def has_book(self, identifier: str) -> bool:
        if not valid_id(identifier):
            return False
        with self.lock, Session(self.engine) as session:
            mapping = session.scalar(
                select(SyncBookMapRow).where(SyncBookMapRow.content_id == identifier)
            )
            book = self.books.get(mapping.book_id) if mapping else None
            return book is not None and (book.storage_path / book.package_path).is_file()

    def missing_books(self) -> set[str]:
        # Metadata may already be acknowledged when a connection drops midway
        # through a transfer. Reconstruct requests from durable state on reconnect.
        return {
            record.key
            for record in self.records()
            if record.kind == "book" and not self.has_book(record.key)
        }

    def export(self, identifier: str) -> tuple[Path, int, str]:
        if not valid_id(identifier):
            raise SyncError("Invalid book identifier.")
        with self.lock, Session(self.engine) as session:
            mapping = session.scalar(
                select(SyncBookMapRow).where(SyncBookMapRow.content_id == identifier)
            )
            book = self.books.get(mapping.book_id) if mapping else None
            if book is None:
                raise SyncError("The requested book is unavailable.")
            if content_id(book.storage_path) != identifier:
                raise SyncError("The stored book has changed since synchronization.")
            path = self.root / "sync/cache" / f"{identifier}.epub"
            size, checksum = export_publication(book.storage_path, path)
            return path, size, checksum

    def install_book(self, identifier: str, archive: Path) -> str:
        with self.lock:
            if self.has_book(identifier):
                with Session(self.engine) as session:
                    mapping = session.scalar(
                        select(SyncBookMapRow).where(SyncBookMapRow.content_id == identifier)
                    )
                    if mapping is None:
                        raise SyncError("Missing book mapping.")
                    return mapping.book_id
            book = self.importer.import_book(archive, expected_content_id=identifier)
            try:
                create_thumbnail(book)
            except (OSError, ValueError, RuntimeError):
                logger.exception("Synced cover thumbnail could not be cached")
            with Session(self.engine) as session, session.begin():
                session.merge(SyncBookMapRow(book_id=book.id, content_id=identifier))
            with Session(self.engine) as session, session.begin():
                for headrow in session.scalars(select(SyncHeadRow)):
                    current = winner(self._heads(session, headrow.kind, headrow.entity_key))
                    if (current.kind in ("book", "progress") and current.key == identifier) or (
                        current.kind == "annotation" and current.value["book"] == identifier
                    ):
                        self._project(session, current)
            return book.id

    def peer(self, identifier: str) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.get(SyncPeerRow, identifier)
            return (
                {
                    "id": row.id,
                    "name": row.name,
                    "certificate": row.certificate,
                    "host": row.host,
                    "port": row.port,
                    "enabled": row.enabled,
                }
                if row
                else None
            )

    def peers(self) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            return [
                {
                    "id": row.id,
                    "name": row.name,
                    "host": row.host,
                    "port": row.port,
                    "enabled": row.enabled,
                }
                for row in session.scalars(select(SyncPeerRow).where(SyncPeerRow.enabled))
            ]

    def trust(self, identifier: str, name: str, certificate: str, host: str, port: int) -> None:
        with Session(self.engine) as session, session.begin():
            session.merge(
                SyncPeerRow(
                    id=identifier,
                    name=name[:100],
                    certificate=certificate,
                    host=host,
                    port=port,
                    enabled=True,
                )
            )

    def endpoint(self, identifier: str, host: str, port: int) -> None:
        with Session(self.engine) as session, session.begin():
            peer = session.get(SyncPeerRow, identifier)
            if peer:
                peer.host, peer.port = host, port

    def revoke(self, identifier: str) -> None:
        with Session(self.engine) as session, session.begin():
            peer = session.get(SyncPeerRow, identifier)
            if peer:
                peer.enabled = False

    def conflicts(self) -> list[dict[str, Any]]:
        with self.lock, Session(self.engine) as session:
            result = []
            for row in session.scalars(select(SyncHeadRow)):
                heads = self._heads(session, row.kind, row.entity_key)
                if len({digest(head.value) for head in heads}) > 1:
                    selected = winner(heads)
                    identifier = selected.value.get("book", selected.key)
                    mapping = session.scalar(
                        select(SyncBookMapRow).where(SyncBookMapRow.content_id == identifier)
                    )
                    book = session.get(BookRow, mapping.book_id) if mapping else None
                    names = {
                        "dark": "Dark appearance",
                        "font_size": "Font size",
                        "language": "Language",
                        "color_scheme": "Color scheme",
                        "reading_surface": "Reading surface",
                        "reduced_motion": "Reduce motion",
                    }
                    context = (
                        names.get(selected.key, selected.kind)
                        if selected.kind == "preference"
                        else book.title
                        if book
                        else selected.value.get("title", "Notes")
                    )
                    choices = []
                    for head in heads:
                        peer = session.get(SyncPeerRow, head.author)
                        if head.kind == "progress":
                            summary = f"{head.value['fraction'] * 100:.0f}%"
                        elif head.kind == "annotation":
                            summary = (
                                "Deleted note"
                                if head.value["deleted"]
                                else head.value["text"][:400]
                            )
                        elif head.kind == "book":
                            summary = head.value["title"] + (
                                " ★" if head.value["favorite"] else " ☆"
                            )
                        else:
                            value = head.value["value"]
                            summary = (
                                ("On" if value else "Off")
                                if isinstance(value, bool)
                                else str(value)
                            )
                        choices.append(
                            {
                                "id": head.id,
                                "value": head.value,
                                "summary": summary,
                                "translate_summary": (
                                    head.kind == "annotation" and head.value["deleted"]
                                )
                                or (
                                    head.kind == "preference"
                                    and isinstance(head.value["value"], bool)
                                ),
                                "device": peer.name if peer else head.author[:12],
                            }
                        )
                    result.append(
                        {
                            "kind": row.kind,
                            "key": row.entity_key,
                            "context": context,
                            "choices": choices,
                        }
                    )
            return result

    def resolve(self, kind: str, key: str, identifier: str) -> None:
        with self.lock, Session(self.engine) as session, session.begin():
            selected = next(
                (head for head in self._heads(session, kind, key) if head.id == identifier), None
            )
            if selected is None:
                raise SyncError("The conflict choice is no longer available.")
            self._local(session, kind, key, selected.value, force=True)
            self._project(session, winner(self._heads(session, kind, key)))

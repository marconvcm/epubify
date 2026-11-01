from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from epub_reader.infrastructure.database.models import Base


class SyncVersionRow(Base):
    __tablename__ = "sync_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    entity_key: Mapped[str] = mapped_column(String(100), index=True)
    record: Mapped[str] = mapped_column(Text)


class SyncHeadRow(Base):
    __tablename__ = "sync_heads"
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    entity_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    heads: Mapped[str] = mapped_column(Text, default="[]")


class SyncProjectionRow(Base):
    __tablename__ = "sync_projections"
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    entity_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_hash: Mapped[str] = mapped_column(String(64))


class SyncBookMapRow(Base):
    __tablename__ = "sync_book_map"
    book_id: Mapped[str] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), primary_key=True
    )
    content_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class SyncPeerRow(Base):
    __tablename__ = "sync_peers"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    certificate: Mapped[str] = mapped_column(Text)
    host: Mapped[str] = mapped_column(String(200), default="")
    port: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AnnotationRow(Base):
    __tablename__ = "annotations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    location: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from epub_reader.domain.models.category import Category


@dataclass(frozen=True, slots=True)
class Book:
    id: str
    title: str
    author: str
    storage_path: Path
    package_path: str
    imported_at: datetime
    cover_path: Path | None = None
    last_opened_at: datetime | None = None
    progress: float = 0.0
    location: str = ""
    categories: tuple[Category, ...] = ()
    classification_version: int = 0
    favorite: bool = False

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QStandardPaths


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @classmethod
    def default(cls) -> "AppPaths":
        return cls(
            Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
        )

    @property
    def books(self) -> Path:
        return self.root / "books"

    @property
    def database(self) -> Path:
        return self.root / "library.sqlite3"

    def create(self) -> None:
        self.books.mkdir(parents=True, exist_ok=True)


RESOURCES = Path(__file__).resolve().parents[1] / "resources"

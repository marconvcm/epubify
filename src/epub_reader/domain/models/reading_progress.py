import json
import math
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class ReadingLocation:
    chapter: str
    offset: int

    def __post_init__(self) -> None:
        if (
            not self.chapter
            or "\\" in self.chapter
            or ":" in self.chapter
            or PurePosixPath(self.chapter).is_absolute()
            or any(part in ("", ".", "..") for part in self.chapter.split("/"))
        ):
            raise ValueError("Invalid chapter location.")
        if type(self.offset) is not int or not 0 <= self.offset <= 50_000_000:
            raise ValueError("Invalid reading offset.")

    def encode(self) -> str:
        return json.dumps({"version": 1, "chapter": self.chapter, "offset": self.offset})

    @classmethod
    def decode(cls, value: str) -> "ReadingLocation":
        try:
            if len(value) > 4096:
                raise ValueError("Location is too long.")
            data = json.loads(value)
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("Unsupported reading location.")
            if not isinstance(data.get("chapter"), str):
                raise ValueError("Invalid chapter location.")
            return cls(data["chapter"], data["offset"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid reading location.") from exc


@dataclass(frozen=True, slots=True)
class ReadingProgress:
    location: str
    fraction: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.fraction) or not 0 <= self.fraction <= 1:
            raise ValueError("Reading progress must be between zero and one.")
        if self.location:
            ReadingLocation.decode(self.location)

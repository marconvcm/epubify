"""Bounded, deterministic multi-value registers for offline replication."""

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from typing import Any

MAX_RECORD_BYTES = 64 * 1024
MAX_VECTOR_DEVICES = 32
KINDS = {"book", "progress", "annotation", "preference"}
PREFERENCES = {"dark", "font_size", "reduced_motion", "reading_surface", "color_scheme", "language"}


class SyncError(ValueError):
    pass


def canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SyncError("Invalid synchronization data.") from exc


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def valid_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def dominates(first: dict[str, int], second: dict[str, int]) -> bool:
    return all(first.get(device, 0) >= sequence for device, sequence in second.items())


@dataclass(frozen=True)
class Record:
    kind: str
    key: str
    value: dict[str, Any]
    vector: dict[str, int]
    author: str
    updated_ms: int
    certificate: str
    signature: str

    def body(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "value": self.value,
            "vector": self.vector,
            "author": self.author,
            "updated_ms": self.updated_ms,
        }

    @property
    def id(self) -> str:
        return digest(self.body())

    def wire(self) -> dict[str, Any]:
        return {**self.body(), "certificate": self.certificate, "signature": self.signature}

    @classmethod
    def parse(cls, data: dict[str, Any], *, check_clock: bool = True) -> "Record":
        if (
            not isinstance(data, dict)
            or len(canonical(data)) > MAX_RECORD_BYTES
            or set(data)
            != {
                "kind",
                "key",
                "value",
                "vector",
                "author",
                "updated_ms",
                "certificate",
                "signature",
            }
        ):
            raise SyncError("Synchronization record exceeds protocol limits.")
        record = cls(**data)
        if (
            not isinstance(record.kind, str)
            or record.kind not in KINDS
            or not valid_id(record.author)
        ):
            raise SyncError("Unknown synchronization record type.")
        if not isinstance(record.key, str) or not 1 <= len(record.key) <= 100:
            raise SyncError("Invalid synchronization key.")
        if not isinstance(record.vector, dict) or not 1 <= len(record.vector) <= MAX_VECTOR_DEVICES:
            raise SyncError("Invalid synchronization version vector.")
        if (
            any(
                not valid_id(device) or type(sequence) is not int or not 1 <= sequence <= 10**12
                for device, sequence in record.vector.items()
            )
            or record.author not in record.vector
        ):
            raise SyncError("Invalid synchronization version vector.")
        if (
            type(record.updated_ms) is not int
            or record.updated_ms < 0
            or (check_clock and record.updated_ms > int(time.time() * 1000) + 300_000)
        ):
            raise SyncError("Device clocks differ too much for synchronization.")
        if (
            not isinstance(record.certificate, str)
            or len(record.certificate) > 8192
            or not isinstance(record.signature, str)
            or len(record.signature) > 512
        ):
            raise SyncError("Invalid device signature.")
        record.validate_value()
        return record

    def validate_value(self) -> None:
        value = self.value
        if not isinstance(value, dict):
            raise SyncError("Invalid synchronization value.")
        if self.kind in {"book", "progress"} and not valid_id(self.key):
            raise SyncError("Invalid book identifier.")
        if self.kind == "book":
            if (
                set(value) != {"title", "author", "favorite"}
                or any(
                    not isinstance(value.get(key), str) or len(value[key]) > 1000
                    for key in ("title", "author")
                )
                or type(value.get("favorite")) is not bool
            ):
                raise SyncError("Invalid book metadata.")
        elif self.kind == "progress":
            location, fraction = value.get("location"), value.get("fraction")
            if (
                set(value) != {"location", "fraction"}
                or not isinstance(location, str)
                or len(location) > 16384
                or not isinstance(fraction, (int, float))
                or isinstance(fraction, bool)
                or not math.isfinite(fraction)
                or not 0 <= fraction <= 1
            ):
                raise SyncError("Invalid reading position.")
            if location:
                from epub_reader.domain.models.reading_progress import ReadingLocation

                ReadingLocation.decode(location)
        elif self.kind == "preference":
            if self.key not in PREFERENCES or set(value) != {"value"}:
                raise SyncError("This preference cannot be synchronized.")
            setting = value["value"]
            if self.key in {"dark", "reduced_motion"} and type(setting) is not bool:
                raise SyncError("Invalid preference value.")
            if self.key == "font_size" and (type(setting) is not int or not 14 <= setting <= 32):
                raise SyncError("Invalid preference value.")
            if self.key == "reading_surface" and setting not in (
                "plain",
                "paper",
                "sepia",
                "slate",
                "grid",
                "dots",
            ):
                raise SyncError("Invalid preference value.")
            if self.key == "language" and setting not in (
                "en",
                "zh-CN",
                "es",
                "fr",
                "de",
                "ja",
                "pt",
                "it",
            ):
                raise SyncError("Invalid preference value.")
            if self.key == "color_scheme" and (
                not isinstance(setting, str)
                or re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", setting) is None
            ):
                raise SyncError("Invalid preference value.")
        elif self.kind == "annotation":
            import uuid

            try:
                if str(uuid.UUID(self.key)) != self.key:
                    raise ValueError
            except (ValueError, AttributeError) as exc:
                raise SyncError("Invalid annotation identifier.") from exc
            if (
                set(value) != {"book", "location", "text", "deleted"}
                or not valid_id(value.get("book"))
                or not isinstance(value.get("text"), str)
                or len(value["text"]) > 16000
                or type(value.get("deleted")) is not bool
                or not isinstance(value.get("location"), str)
            ):
                raise SyncError("Invalid annotation.")
            from epub_reader.domain.models.reading_progress import ReadingLocation

            ReadingLocation.decode(value["location"])


def surviving_heads(existing: list[Record], incoming: Record) -> list[Record]:
    if any(
        record.id == incoming.id
        or (record.vector != incoming.vector and dominates(record.vector, incoming.vector))
        for record in existing
    ):
        return existing
    return sorted(
        [
            record
            for record in existing
            if incoming.vector == record.vector or not dominates(incoming.vector, record.vector)
        ]
        + [incoming],
        key=lambda record: record.id,
    )


def winner(records: list[Record]) -> Record:
    # A concurrent note deletion wins over an edit; every signed branch is retained.
    return max(
        records,
        key=lambda record: (
            record.kind == "annotation" and record.value.get("deleted", False),
            record.updated_ms,
            record.author,
            record.id,
        ),
    )

"""Validated, declarative color schemes shared by QML and the native renderer."""

import json
import re
from dataclasses import dataclass, fields
from functools import cache
from pathlib import Path
from typing import Any

from epub_reader.core.paths import RESOURCES

DEFAULT_SCHEME = "parchment"
SCHEMES_DIR = RESOURCES / "themes"


@dataclass(frozen=True)
class Palette:
    background: str
    surface: str
    elevated: str
    text: str
    secondary: str
    accent: str
    accent_text: str
    border: str
    action: str
    on_action: str
    error_surface: str
    error: str


@dataclass(frozen=True)
class ColorScheme:
    id: str
    name: str
    dark: Palette
    light: Palette
    covers: tuple[str, ...]
    cover_text: str
    cover_secondary: str
    reading: dict[str, dict[str, str]]


def load_scheme(path: Path) -> ColorScheme:
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
        if data["version"] != 1 or not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", data["id"]):
            raise ValueError("Unsupported theme version or identifier")
        if not isinstance(data["name"], str) or not data["name"].strip():
            raise ValueError("A theme name is required")
        colors = data["colors"]
        if not isinstance(colors, dict) or not colors:
            raise ValueError("Named colors are required")
        for value in colors.values():
            if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError("Colors must use #RRGGBB format")

        def resolve(value: str) -> str:
            if value.startswith("{") and value.endswith("}"):
                value = colors[value[1:-1]]
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                raise ValueError(f"Invalid color: {value}")
            return value

        def palette(key: str) -> Palette:
            return Palette(
                **{field.name: resolve(data[key][field.name]) for field in fields(Palette)}
            )

        backgrounds = data["covers"]["backgrounds"]
        if not isinstance(backgrounds, list) or not 1 <= len(backgrounds) <= 12:
            raise ValueError("Supply between 1 and 12 cover colors")
        reading = {
            key: {
                role: resolve(data["reading"][key][role])
                for role in ("background", "foreground", "accent")
            }
            for key in ("paper", "sepia", "slate")
        }
        return ColorScheme(
            id=data["id"],
            name=data["name"],
            dark=palette("dark"),
            light=palette("light"),
            covers=tuple(resolve(value) for value in backgrounds),
            cover_text=resolve(data["covers"]["text"]),
            cover_secondary=resolve(data["covers"]["secondary"]),
            reading=reading,
        )
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise ValueError(f"Invalid color scheme {path.name}: {exc}") from exc


@cache
def scheme_for(identifier: str = DEFAULT_SCHEME) -> ColorScheme:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", identifier):
        raise ValueError("Invalid color scheme identifier")
    scheme = load_scheme(SCHEMES_DIR / f"{identifier}.json")
    if scheme.id != identifier:
        raise ValueError("Color scheme id must match its filename")
    return scheme


def available_schemes() -> list[dict[str, str]]:
    schemes = [scheme_for(path.stem) for path in sorted(SCHEMES_DIR.glob("*.json"))]
    return [{"id": scheme.id, "name": scheme.name} for scheme in schemes]


def palette_for(dark: bool, scheme: str = DEFAULT_SCHEME) -> Palette:
    definition = scheme_for(scheme)
    return definition.dark if dark else definition.light

import hashlib
import json

import pytest

from epub_reader.core.design import available_schemes, palette_for, scheme_for
from epub_reader.core.paths import RESOURCES
from epub_reader.rendering.surfaces import SURFACE_KEYS, surface_for


def contrast(first: str, second: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

    low, high = sorted((luminance(first), luminance(second)))
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("dark", [True, False])
@pytest.mark.parametrize("scheme_id", [scheme["id"] for scheme in available_schemes()])
def test_palette_and_reader_text_keep_readable_contrast(dark: bool, scheme_id: str) -> None:
    palette = palette_for(dark, scheme_id)
    for text in (palette.text, palette.secondary, palette.accent):
        for background in (palette.background, palette.surface, palette.elevated):
            assert contrast(text, background) >= 4.5
    assert contrast(palette.on_action, palette.action) >= 4.5
    assert contrast(palette.error, palette.error_surface) >= 4.5
    scheme = scheme_for(scheme_id)
    for color in scheme.covers:
        assert contrast(scheme.cover_text, color) >= 4.5
        assert contrast(scheme.cover_secondary, color) >= 4.5
    for key in SURFACE_KEYS:
        surface = surface_for(key, dark, scheme_id)
        assert contrast(surface.foreground, surface.background) >= 4.5
        assert contrast(surface.accent, surface.background) >= 4.5


def test_font_assets_match_pinned_sources_and_ship_their_licenses() -> None:
    root = RESOURCES / "fonts"
    manifest = json.loads((root / "manifest.json").read_text())
    fonts = [entry for entry in manifest["files"] if entry["file"].endswith(".ttf")]
    assert len(fonts) == 6
    assert {entry["family"] for entry in fonts} == {
        "IBM Plex Sans",
        "Playfair Display",
        "JetBrains Mono",
    }
    for entry in manifest["files"]:
        path = root / entry["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        assert manifest["revision"] in entry["source"]
        assert "SIL OPEN FONT LICENSE" in (path.parent / "OFL.txt").read_text()


@pytest.mark.parametrize("problem", ["hex", "missing_role", "unknown_token", "version"])
def test_invalid_color_scheme_is_rejected_with_file_context(tmp_path, problem: str) -> None:
    from epub_reader.core.design import load_scheme

    data = json.loads((RESOURCES / "themes/stormcloud.json").read_text())
    if problem == "hex":
        data["colors"]["brown"] = "#XXYYZZ"
    elif problem == "missing_role":
        del data["dark"]["text"]
    elif problem == "unknown_token":
        data["light"]["background"] = "{missing_color}"
    else:
        data["version"] = 999
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="broken.json"):
        load_scheme(path)

from pathlib import Path

import pytest

from epub_reader.bootstrap import create_runtime
from epub_reader.core.paths import AppPaths
from epub_reader.rendering.engine import NativeBookEngine
from epub_reader.rendering.surfaces import SURFACE_KEYS
from epub_reader.services.epub_import_service import EpubImportService


@pytest.mark.gui
@pytest.mark.parametrize("surface", SURFACE_KEYS)
def test_surfaces_preserve_position_and_render_deterministically(
    qtbot, repository, epub: Path, tmp_path: Path, surface: str
) -> None:
    book = EpubImportService(repository, tmp_path / "books").import_book(epub)
    engine = NativeBookEngine()
    engine.open(book)
    engine.next()
    location = engine.location
    engine.configure(20, True, surface)
    assert engine.location == location
    image = engine.image.copy()
    engine.set_viewport(920, 650)
    engine.set_viewport(900, 650)
    assert engine.image == image
    if surface != "plain":
        colors = {
            engine.image.pixelColor(x, y).name() for x in range(0, 60, 3) for y in range(0, 60, 3)
        }
        assert len(colors) > 1  # Actual native texture/grid, away from text.


@pytest.mark.gui
def test_surface_preference_survives_restart_and_keeps_ui_theme_independent(
    qtbot, tmp_path: Path
) -> None:
    paths = AppPaths(tmp_path / "app")
    runtime = create_runtime(paths, library_only=True)
    try:
        runtime.reader.preferences.setReadingSurface("paper")
        assert runtime.reader.preferences.dark
        with pytest.raises(ValueError):
            runtime.reader.preferences.setReadingSurface("unknown")
    finally:
        runtime.dispose()
    restored = create_runtime(paths, library_only=True)
    try:
        assert restored.reader.preferences.readingSurface == "paper"
        assert restored.reader.preferences.dark
    finally:
        restored.dispose()

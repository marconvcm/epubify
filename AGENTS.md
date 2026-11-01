# Repository Guidelines

## Project Structure

- `src/epub_reader/`: application code (`domain/`, `services/`, `infrastructure/`,
  `rendering/`, `presentation/`, `platforms/`, `resources/` with QML, themes, fonts, i18n).
- `tests/`: unit, integration and GUI tests (`pytest`, `pytest-qt`).
- `scripts/`: dev, build and Android helpers (`scripts/android.py`).
- `platforms/android/`: Android runtime pins, p4a recipes, intent filters and Java sources.
- `docs/`: architecture, development, mobile, packaging, sync and theme notes.
- `build/` and `dist/` are generated and git-ignored.

## Commands

```sh
uv sync --locked
uv run epub-reader                 # run the app
uv run epub-reader --mobile-preview
uv run ruff check . && uv run ruff format --check .
uv run mypy
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software uv run pytest
uv run python scripts/android.py apk --arch x86_64 --accept-licenses   # Android debug APK
```

## Style

Python 3.13, four spaces, 100 columns, strict mypy and ruff. Two spaces for JSON/YAML.
Match the surrounding code; avoid unrelated formatting changes.

## Android notes

`pyjnius` does not load in the Qt bootstrap. Android-only behavior lives in
`platforms/android/java/` and exchanges small files with `src/epub_reader/platforms/android.py`.
Read `docs/mobile.md` before changing it.

## Commits and pull requests

Short, imperative commit subjects. Pull requests explain the problem, summarize the
change, link issues and list verification commands with results; disclose checks that
could not run. Never commit credentials, tokens or private documents.

# Development

Use Python 3.13 and uv. `uv sync --locked` installs the application and development
tools. Runtime dependencies include PySide6 6.12.0, SQLAlchemy 2.x, defusedxml,
cryptography, websockets and zeroconf. Networking starts only after opting in.
The full official Qt metapackage supplies initialization/support code and type
stubs as well as the native modules. Its extra browser wheels are unused by the
reader; no browser process starts.

```sh
uv run epub-reader
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python scripts/make_demo.py demo.epub
```

All reading tests can run without a physical display:

```sh
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software uv run pytest
```

Do not set `QSG_RHI_BACKEND=software`; software is a Qt Quick backend rather than
an RHI graphics API. Native desktop startup uses the platform's usual graphics path.

## Diagnostics

```sh
uv run epub-reader --open-last --diagnostics-dir .debug/reader
```

The app captures only its own window after 1, 4 and 10 seconds and writes a log
in the requested directory. `.debug/` is ignored: screenshots can contain private
book content. `--data-dir PATH` isolates a test library; `--smoke-test` exits after
two seconds; `--library-only` limits a diagnostic run to the library UI.

## Tests and conventions

Fixtures generate deterministic, original EPUBs, including EPUB 2/3 contents,
images and linked CSS. Tests cover archives, repositories, migration, preferences,
filtering, native pagination, exact position restoration, high DPI, resource
confinement, nested EPUB 2/3 contents, illustration indexing, image anchors,
deterministic page textures and the actual QML reader. Interaction checks click
disclosure controls, section links, figure links and surface swatches, including
popup dismissal and reading-position preservation. GUI checks use pytest-qt with a real Qt
application. There is no mandated coverage percentage yet.

Use four-space Python indentation, Ruff formatting, descriptive snake_case names
and explicit types at service/rendering boundaries. QML-exposed slots/properties
follow Qt naming conventions. Keep persistence and publication rules outside QML.
Add regression tests for parser, position, layout and persistence changes.

The initial lock was assembled from published PyPI metadata and artifact hashes
because downloads were restricted. `uv lock --check --offline` validates it. Use
`uv lock` when intentionally updating dependencies. The lock tracks the official metapackage and its compatible transitive versions.

Data/logs use QStandardPaths.AppDataLocation. On Linux this is normally
`~/.local/share/Epubify/Epubify`; use `--data-dir` when experimenting. Linux needs
the EGL/OpenGL/XKB/XCB libraries appropriate to its Qt platform plugin; the CI
workflow lists Ubuntu packages. Native platform rendering still needs checking on
each supported OS.

## Organization, translations and sync

Categories use deterministic local title/subject/description rules in
`resources/classification/topics.json`; missing classifications are backfilled
by a worker. Favorites are independent of category/search filters. Editing a
book's progress never overwrites its categories or favorite flag.

Edit `resources/i18n/catalogs.json`, then run
`uv run python scripts/compile_translations.py`. Ship generated TS/QM files for
all eight languages. Tests verify QML string coverage, placeholders, live language
switching and persistence. Book metadata, content and user notes stay verbatim.
IBM Plex Sans uses system font fallback for missing CJK glyphs; Linux CI installs
Noto CJK. Language is selected in Settings or with `--language pt`.

See [sync protocol and tests](synchronization.md) for TLS pairing, signed registers,
conflict resolution, thread ownership and network limits. Test independent GUI
libraries with `epub-reader --data-dir /tmp/epubify-a` and
`epub-reader --data-dir /tmp/epubify-b` in separate terminals, then pair in Settings.
Do not run the same data directory twice. Real network tests skip in restricted
runners; desktop QML and in-memory protocol/TLS tests still run. Android SDK/ADB
helpers and iOS permission overlays are described in [mobile](mobile.md).

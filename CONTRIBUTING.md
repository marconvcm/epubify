# Contributing to Epubify

Thanks for helping! Epubify is a local-first Qt Quick EPUB reader written in
Python 3.13 and Qt 6.12 (PySide6). It runs on Linux, Windows and macOS, and has an
experimental Android build.

## Getting started

```sh
git clone https://github.com/marconvcm/epubify.git
cd epubify
uv sync --locked
uv run epub-reader
```

Create a demo book with `uv run python scripts/make_demo.py demo.epub`. For
phone-sized layouts use `uv run epub-reader --mobile-preview`.

## Checks before opening a pull request

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software uv run pytest
```

CI runs the same checks on Linux, Windows and macOS. Add tests with new behavior
and a regression test for each bug fix. Single test: `uv run pytest tests/unit/test_x.py::test_name`.

## Where things live

See the project map in [README.md](README.md), plus [docs/architecture.md](docs/architecture.md)
and [docs/development.md](docs/development.md). Android specifics (build, Java
bridge, intents, system bars) are in [docs/mobile.md](docs/mobile.md).

## Android contributions

Build with `uv run python scripts/android.py apk --arch x86_64 --accept-licenses`
(use `x86_64` for emulators, `aarch64` for phones). The first build downloads the
SDK/NDK and takes a long time. Please state in your pull request which device or
emulator you tested on; compile-only changes should say so.

Good first areas: the Wi-Fi multicast lock (`platforms/network.py` still uses
`pyjnius`, which does not load in this bootstrap), `content://` edge cases, a
storage-permission-free "open with" test harness, and iOS support.

## Style

- Python: four spaces, 100 columns, `ruff` and strict `mypy`.
- JSON/YAML: two spaces. QML: match the surrounding files.
- Keep modules focused and avoid unrelated formatting changes.
- Commit messages: short, imperative subjects (for example `Add EPUB metadata parser`).

## Pull requests

Explain the problem, summarize the change, link related issues and list the
verification commands you ran with their results. Include screenshots for visible
UI changes and say which checks you could not run.

## Security and privacy

Never commit credentials, tokens or private documents. Report security problems
privately through GitHub's "Report a vulnerability" option instead of a public issue.

## License

By contributing you agree that your work is released under the MIT License.

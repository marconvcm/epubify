# Packaging

Standalone builds are prepared for native Linux, Windows and macOS runners.
No standalone artifact has been generated or verified yet.

```sh
uv sync --locked --group build
uv run python scripts/build.py
uv run python scripts/verify_bundle.py
```

The build calls Nuitka's PySide6 plugin with QML and image plugins, package data,
SVGs, the application PNG icon, JSON themes, all six font binaries and their OFL
license notices. The verifier checks resources and launches the packaged
library. Importing/reading/resuming a book on a clean target machine remains a
separate required release check. The Python wheel is not a standalone application.

The compiler explicitly includes dynamically loaded cryptography, websockets,
zeroconf and ifaddr packages. Keep their native extensions and bundled notices;
verify TLS identities, discovery and transfer in the final bundle, not just the
source environment. See [sync](synchronization.md) and the experimental
[Android/iOS status](mobile.md). Android debug APKs pass structural checks and have
launched in the emulator; complete device acceptance and iOS artifacts remain pending.

Qt's pyside6-deploy wraps Nuitka and can generate deployment specifications; the
explicit build script is used here for reviewable module/resource inclusion.
Confirm that the selected packaging tool includes Qt Quick Controls, Effects, platform/image plugins and their Qt
libraries. There is no browser helper process or browser resource package to ship.

- Linux: match the wheel's glibc/architecture baseline and graphics dependencies.
  AppImage/Flatpak are future distribution options requiring separate validation.
- Windows: build on Windows and ship all DLLs/plugins with the executable. Test a
  machine without Python or Qt before preparing a signed installer.
- macOS: build on supported macOS hardware, inspect architectures, sign nested
  libraries and the outer app, then notarize/staple. Unsigned CI folders are not
  release-ready. Universal wheels do not prove a compiled bundle is universal.

Do not assume cross-compilation from Linux. GitHub Actions uses separate native
runners and currently creates experimental artifacts only after build checks.

Application code is MIT. Qt/PySide6 and their third-party code retain applicable
LGPL/GPL/commercial and other terms. Preserve the exact distribution's notices and
review source availability, replacement/relinking and installation-information
obligations for the intended packaging format. Consult
[Qt licensing](https://www.qt.io/licensing/) and
[third-party licenses](https://doc.qt.io/qt-6/licenses-used-in-qt.html).

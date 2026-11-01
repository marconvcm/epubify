# Third-party notices

Epubify's own Python, QML, SVG, native rendering library and original test EPUBs
are MIT licensed. No third-party book content is distributed.

Bundled typefaces are distributed unmodified under SIL Open Font License 1.1:

- IBM Plex Sans: copyright © 2017 IBM Corp.; Reserved Font Name “Plex”.
- Playfair Display: copyright 2017 The Playfair Display Project Authors; Reserved
  Font Name “Playfair Display”.
- JetBrains Mono: copyright 2020 The JetBrains Mono Project Authors.

Full copyright notices and license terms accompany each family in
`epub_reader/resources/fonts/<family>/OFL.txt`. Keep all three license files with
any redistribution. `fonts/manifest.json` records pinned source URLs and hashes
from [Google Fonts](https://github.com/google/fonts). The application does not
relicense these font binaries as MIT.

Qt/PySide6 is installed as a dependency and is not relicensed by the
application. Preserve applicable LGPL/GPL/commercial and bundled third-party
notices when distributing Qt binaries. Review the exact modules and distribution
method using [Qt licensing](https://www.qt.io/licensing/) and
[Qt third-party licenses](https://doc.qt.io/qt-6/licenses-used-in-qt.html).
See `docs/packaging.md` for release considerations.

SQLAlchemy is MIT licensed; defusedxml is PSF-2.0 licensed. Development/build tools
retain their own licenses. Consult their locked distributions for exact notices.

Local synchronization uses cryptography (Apache-2.0 OR BSD-3-Clause), websockets
(BSD-3-Clause), zeroconf (LGPL-2.1-or-later), ifaddr (MIT), cffi (MIT-0), and
pycparser (BSD-3-Clause). Copies of the installed distributions' license files
are bundled in `resources/licenses/<package>/`; `manifest.json` records versions
and hashes. Preserve these notices and the LGPL obligations for zeroconf in
standalone/mobile distributions. Review native OpenSSL/Rust and mobile recipe
dependencies separately for each final artifact. Android's optional pyjnius
adapter retains pyjnius's MIT license in its target distribution.

The former JavaScript EPUB renderer and its vendored dependencies have been
removed. The reading implementation now uses Qt rich text and application-owned
pagination/rendering code.

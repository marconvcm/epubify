# Native renderer validation

Validated on 2026-10-31 with Python 3.13.18 and PySide6 / Qt 6.12.0.
The reader now uses application-owned Qt rich-text pagination and page images.

## Verified

- **138 pytest cases passed**, with one explicit real-network skip, with the actual QML reader enabled
  under `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software`.
- Tests cover EPUB 2/3 metadata and contents, ZIP/path limits and malformed input,
  SQLite CRUD, preferences, search, background import/thumbnails, native image
  resource confinement, page navigation, anchor navigation, exact text-offset
  restoration after reader/database recreation, font/viewport reflow, high DPI,
  oversized-cover fitting, schema migration, live QML themes, hierarchical outlines,
  figure indexes, isolated/repeated-image anchors, procedural textures, surface
  persistence, and real mouse clicks on the new QML navigation/appearance controls.
- **mypy passed all 59 application source files**; **Ruff check and formatting passed**.
- The reader runs from the official Qt distribution. The full PySide6 metapackage
  is retained because it supplies package initialization, support code and type
  stubs absent from Essentials alone. Its extra browser packages are unused by
  the native reading pipeline; no browser process is started.
- A generated original test EPUB was opened in the actual QML reader, paginated,
  advanced and captured at `docs/design/reader-native-running.png`. The navigation
  fixture also produced actual-window captures in `navigation-paper-running.png`,
  `reading-surfaces-running.png`, `figures-running.png` and `reading-grid-running.png`
  under `docs/design/`; these contain only original generated fixture content.
  `contents-compact-running.png` captures a visible TOC with hierarchical links.
- The user's imported book was read without changing its original files/library:
  the native parser identified **137 spine chapters and 135 contents entries**,
  rendered the cover and advanced to the next part. Private captures are in the
  ignored `.debug/native-user-book/` directory. The cover fits one page. The new
  outline preserves **three hierarchy levels**; the background figure index found
  **120 images**. First, middle and last generated figure links were checked against
  native image offsets using an isolated database and read-only original resources.
- Version-1 database migration preserves books, preferences, progress and the old
  CFI column, and adds versioned native reading locations in schema version 2.
- The dependency lock check passed for **31 packages**, including optional build
  tools. A Python wheel/source distribution is built and resource-checked; this
  is distinct from a standalone desktop executable.

## Branding, schemes and batch import

Parchment is the default scheme, with warm dark and light derivatives of the
supplied five colors. Both Parchment and Stormcloud pass the contrast checks.
All three bundled families registered through QFontDatabase; regular/italic and
font weights resolved using the native renderer. Tests verify IBM Plex Sans in
the QML window, Playfair Display in prose/emphasis, JetBrains Mono in inline/pre
code (including EPUB spans with conflicting CSS), and monospaced glyph widths.
Binary/license hashes match the pinned font manifest. Text/link colors pass the
contrast checks in both interface modes and all reading surfaces.

A second JSON scheme was created in an isolated test directory. Its selector,
QML colors, native page and persisted SQLite preference updated together while
keeping the reading position. Malformed color schemes are rejected with file
context. The current scheme's name is shown immediately on opening appearance.

Batch tests exercise the QML multi-URL boundary, two valid imports mixed with an
invalid archive, duplicate and remote URL, continued processing, monotonic progress,
per-file results, persistence, ignored empty/concurrent submissions, and safe
shutdown that finishes the current file and stops remaining requests. Actual QML
captures: `library-branding-running.png`, `reader-branding-dark.png`,
`reader-branding-light.png`, `reading-surfaces-running.png` and
`batch-import-running.png` under `docs/design/`.
The library footer places its editorial quote at the bottom right over a vertical
fade derived from the active scheme. Captures with original fixture books cover
the initial grid, fully scrolled last row and light mode (`library-footer-*.png`).
Extra bottom scroll space keeps the final cards above the footer.

## Visible contents regression

Before the bundled typography change, the PLC EPUB shown in the user's report
was opened using its original resources and an isolated temporary database. Its visible TOC uses flat `h2`/`h3` links
with different anchor aliases from the canonical index. With a 1440×1000 window
and font size 17, navigation-specific formatting reduced that chapter from 31 to
18 pages. The existing plain text and named-anchor offsets matched before/after;
child left margins measured 21.25 and 42.5 logical pixels. The inspected actual
window capture remains private in `.debug/native-toc/compact-running.png`.
Tests reproduce flat/nested lists, conflicting CSS pixel sizes, alias matching,
links at indented coordinates, unchanged offsets and ordinary prose formatting.

## Organization, languages and secure local sync

Favorites, metadata-based categories, four schemes and eight UI languages have
persistence/live QML tests. Catalogs contain 184 sources per language; user book
text and notes stay verbatim. Notes support add/edit/delete and position navigation.
`sync-running.png` captures the actual Portuguese QML panel with an original EPUB.

Tests use cryptography 50.0.2, websockets 17.4 and zeroconf 0.152.1. Real SSL
MemoryBIO negotiates TLS 1.3; tests check pin mismatch, signatures, tampering,
expired/single-use invitations, content identity, offline conflicts, revocation
and unsnapshotted edits. The authenticated application protocol transfers 11 books
plus progress/notes in memory, including recovery after metadata was acknowledged
before a disconnect. One real TCP/TLS/WebSocket test skips because binding is
denied. Physical network/mDNS tests and independent security review remain pending.

`uv lock --check --offline` passes for 31 packages. New artifact URLs/hashes came
from uv's cached published index; dependency markers match installed metadata.
`uv sync --locked --offline` completed using the populated private cache, rebuilding
and installing the edited application. The console entry point smoke test passed. The wheel includes sync code, QML, catalogs, themes, fonts and notices.
It remains a Python package, not a standalone executable. Android doctor found
Java/SDK/ADB and AVDs but lacks the pinned NDK, target wheels and build prerequisites.
No APK/AAB/iOS artifact was built. See [mobile](mobile.md).

## Remaining limits

QTextDocument supports a subset of HTML/CSS. Complex browser layouts, embedded
EPUB font faces, DRM/fixed layout, media, selection handles, text highlights and page
curl shaders are not implemented. Progress is a chapter/page approximation.
Legacy CFI values are preserved but are not converted to native offsets.

Offscreen rendering and the software scene graph are verified. Physical desktop
GPU behavior, screen-reader interaction, Windows/macOS execution and standalone
bundles still require their target-machine checks. Authored CI/build workflows
have not run remotely. No standalone artifact, signing or notarization is claimed.

The root `.git/` and `.agents/` mounts remain read-only, so Git initialization and
repository-lesson recording were unavailable. Root AGENTS.md was preserved.

# Bundled typefaces

- **IBM Plex Sans** — UI; [license](ibm-plex-sans/OFL.txt).
- **Playfair Display** — book text; [license](playfair-display/OFL.txt).
- **JetBrains Mono** — code/monospace; [license](jetbrains-mono/OFL.txt).

Regular and italic variable fonts are distributed unmodified under SIL OFL 1.1.
`manifest.json` records the original Google Fonts paths, pinned Git revision and
SHA-256 hashes for all six binaries and their license files. Keep those licenses
with the files in source, wheels and standalone packages.

`core/typography.py` loads them through QFontDatabase before QML/document creation.
The application needs no font download or global font installation at runtime.
System fallbacks handle missing glyphs. Imported EPUB font-face declarations are
not implemented by this native foundation.

# Color schemes and typography

All interface, placeholder-cover and reading-surface colors come from
`src/epub_reader/resources/themes/*.json`. Python and QML consume the same parsed
scheme; adding a palette does not require changes to screen components.

## Add another palette

1. Copy `parchment.json` to a new file, for example `mist.json`.
2. Change `id` to `mist` and `name` to `Mist`. The ID must match the filename.
3. Edit `colors`. Values use `#RRGGBB`; roles can reference named colors as
   `"{brown}"` or use a literal hex value. References target `colors` only.
4. Review `dark` and `light` roles, placeholder `covers`, and the paper/sepia/slate
   colors under `reading`. Classic, grid and dots follow the interface palette.
5. Restart the app. Select the scheme from the paper button → **Color scheme**,
   or launch with `uv run epub-reader --color-scheme mist`.

The choice is saved in SQLite. Font size, reading surface and light/dark mode
remain independent preferences. Switching palettes preserves the native reading
location. A removed selected scheme falls back to `parchment` on the next launch.
Schemes are cached per process, so restart after editing a file.

The loader validates the version, identifiers, required roles, hex values and
references, and reports the failing filename. Tests check text/link contrast on
every shipped scheme. Run `uv run pytest tests/unit/test_design.py` after edits.
The application icon is a separate PNG asset; palette changes do not recolor it.

## Current palette

Parchment is the default: parchment `#EDEDE9`, dust grey `#D6CCC2`, linen
`#F5EBE0`, powder petal `#E3D5CA`, and almond silk `#D5BDAF`. The opaque `FF`
alpha suffix from the supplied CSS colors is normalized to six-digit RGB.
Warm charcoal/brown shades provide dark surfaces; pale variants provide light
surfaces. Text, links and controls use contrasting derivatives.

The earlier Stormcloud scheme remains selectable. For an existing library with
a saved scheme, select **Parchment** or run
`uv run epub-reader --color-scheme parchment` to switch and save it.

## Fonts and icon

`core/typography.py` registers the bundled IBM Plex Sans (UI), Playfair Display
(reading) and JetBrains Mono (semantic code and monospace text). Regular and italic
variable-font files are included, together with their original SIL OFL licenses
and a pinned source/hash manifest under `resources/fonts/`.

No system font installation or network request is required. EPUB CSS family names
are overridden with the requested typefaces; emphasis, weight, links and native
text offsets remain intact. Fonts without a bundled glyph use the configured
system fallbacks. Imported EPUB `@font-face` is still unsupported.

The supplied root `app_icon.png` is copied unchanged to
`resources/icons/app_icon.png` and used by Qt and the library UI. OS launcher
registration/signing still belongs to the target platform packaging workflow.

## Desktop color treatments

Four palettes ship: Parchment, Stormcloud, Windows and macOS. The latter two are
color treatments within the existing Epubify interface, not native OS control
skins. Select them in Settings → Color scheme; all have separate light/dark roles.

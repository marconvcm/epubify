"""Check compiled resources and launch the library UI. Reading is a separate smoke gate."""

import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    dist = root / "dist"
    executables = [
        p for p in dist.rglob("*") if p.is_file() and p.name in ("Epubify", "Epubify.exe")
    ]
    if len(executables) != 1:
        raise RuntimeError(f"Expected one Epubify executable; found {executables}")
    executable = executables[0]
    for name in [
        "Main.qml",
        "ReaderScreen.qml",
        "app_icon.png",
        "IBMPlexSans.ttf",
        "PlayfairDisplay.ttf",
        "JetBrainsMono.ttf",
        "manifest.json",
        "parchment.json",
        "stormcloud.json",
        "ImportReport.qml",
        "LibraryFooter.qml",
        "SyncPanel.qml",
        "NotesPanel.qml",
        "catalogs.json",
        "pt.qm",
        "topics.json",
        "windows.json",
        "macos.json",
    ]:
        if not any(dist.rglob(name)):
            raise RuntimeError(f"Bundle is missing {name}")
    for font_name in ("IBMPlexSans.ttf", "PlayfairDisplay.ttf", "JetBrainsMono.ttf"):
        if not all((font.parent / "OFL.txt").is_file() for font in dist.rglob(font_name)):
            raise RuntimeError(f"Bundle is missing the license for {font_name}")
    with tempfile.TemporaryDirectory(prefix="epubify-bundle-") as data:
        subprocess.run(
            [str(executable), "--smoke-test", "--qml-only", "--data-dir", data],
            check=True,
            timeout=30,
        )
    print(
        "Bundle resource check and QML library smoke passed. EPUB rendering still needs validation."
    )


if __name__ == "__main__":
    main()

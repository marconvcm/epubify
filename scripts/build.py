"""Build on the target OS. This prepares a folder bundle, not a signed installer."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=standalone",
        "--enable-plugin=pyside6",
        "--include-qt-plugins=qml,imageformats",
        "--include-module=PySide6.QtQuick",
        "--include-module=PySide6.QtGui",
        "--include-package=cryptography",
        "--include-package=websockets",
        "--include-package=zeroconf",
        "--include-package=ifaddr",
        "--include-package-data=epub_reader",
        "--include-data-dir=src/epub_reader/resources=epub_reader/resources",
        "--include-data-files=LICENSE=LICENSE",
        "--include-data-files=THIRD_PARTY_NOTICES.md=THIRD_PARTY_NOTICES.md",
        "--output-dir=dist",
        "--output-filename=Epubify",
        "--assume-yes-for-downloads",
        "scripts/entrypoint.py",
    ]
    if sys.platform == "darwin":
        command.extend(["--macos-create-app-bundle", "--macos-app-name=Epubify"])
    elif sys.platform == "win32":
        command.append("--windows-console-mode=disable")
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())

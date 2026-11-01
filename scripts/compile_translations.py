"""Compile the editable multilingual catalog into standard Qt .qm resources."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "src/epub_reader/resources/i18n"


def main() -> None:
    catalogs = json.loads((DIRECTORY / "catalogs.json").read_text(encoding="utf-8"))
    compiler = shutil.which("pyside6-lrelease") or str(
        Path(sys.executable).parent
        / ("pyside6-lrelease.exe" if sys.platform == "win32" else "pyside6-lrelease")
    )
    for language, entries in catalogs.items():
        document = ET.Element(
            "TS", {"version": "2.1", "language": language.replace("-", "_"), "sourcelanguage": "en"}
        )
        context = ET.SubElement(document, "context")
        ET.SubElement(context, "name").text = "Epubify"
        for source, translation in sorted(entries.items()):
            message = ET.SubElement(context, "message")
            ET.SubElement(message, "source").text = source
            ET.SubElement(message, "translation").text = translation
        ET.indent(document)
        source_file = DIRECTORY / f"{language}.ts"
        ET.ElementTree(document).write(source_file, encoding="utf-8", xml_declaration=True)
        subprocess.run(
            [compiler, str(source_file), "-qm", str(DIRECTORY / f"{language}.qm")], check=True
        )


if __name__ == "__main__":
    main()

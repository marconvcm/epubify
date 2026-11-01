import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from epub_reader.infrastructure.epub.extraction import (
    EpubError,
    resolve_reference,
    safe_relative_path,
)

CONTAINER = "{urn:oasis:names:tc:opendocument:xmlns:container}"
OPF = "{http://www.idpf.org/2007/opf}"
DC = "{http://purl.org/dc/elements/1.1/}"
ET.register_namespace("", "http://www.w3.org/1999/xhtml")


@dataclass(frozen=True)
class EpubMetadata:
    title: str
    author: str
    package_path: str
    cover: str | None
    subjects: tuple[str, ...] = ()
    description: str = ""


def parse_xml(path: Path) -> ET.Element:
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            raise EpubError("An EPUB document is too large to parse safely.")
        return cast(
            ET.Element,
            SafeET.fromstring(path.read_bytes(), forbid_entities=True, forbid_external=True),
        )
    except (ET.ParseError, DefusedXmlException, OSError) as exc:
        raise EpubError("The EPUB contains missing or malformed XML.") from exc


def parse_metadata(root: Path) -> EpubMetadata:
    if (root / "META-INF/encryption.xml").exists():
        raise EpubError("Encrypted or DRM-protected EPUBs are not supported.")
    container = parse_xml(root / "META-INF/container.xml")
    rootfile = container.find(f"{CONTAINER}rootfiles/{CONTAINER}rootfile")
    if rootfile is None:
        raise EpubError("The EPUB does not declare a package document.")
    package_path = str(safe_relative_path(rootfile.get("full-path", "")))
    package = parse_xml(root / package_path)
    metadata = package.find(f"{OPF}metadata")
    manifest = package.find(f"{OPF}manifest")
    spine = package.find(f"{OPF}spine")
    if metadata is None or manifest is None or spine is None or not list(spine):
        raise EpubError("The EPUB is missing metadata, a manifest, or a reading spine.")
    if any(m.get("property") == "rendition:layout" and m.text == "pre-paginated" for m in metadata):
        raise EpubError("Fixed-layout publications are not supported by this reader yet.")
    items = {item.get("id", ""): item for item in manifest}
    for itemref in spine:
        item = items.get(itemref.get("idref", ""))
        if item is None:
            raise EpubError("The EPUB spine references a missing manifest item.")
        chapter = resolve_reference(package_path, item.get("href", ""))
        if not (root / chapter).is_file():
            raise EpubError("The EPUB is missing a reading chapter.")
        if item.get("media-type") not in ("application/xhtml+xml", "text/html"):
            raise EpubError("Only reflowable HTML reading chapters are supported.")
    cover_id = next((m.get("content") for m in metadata if m.get("name") == "cover"), None)
    cover = None
    for item in manifest:
        if "cover-image" in item.get("properties", "").split() or item.get("id") == cover_id:
            candidate = resolve_reference(package_path, item.get("href", ""))
            if (root / candidate).is_file():
                cover = candidate
                break

    def text(name: str, fallback: str) -> str:
        values = [" ".join("".join(e.itertext()).split()) for e in metadata.findall(f"{DC}{name}")]
        return ", ".join(filter(None, values))[:1000] or fallback

    return EpubMetadata(
        text("title", "Untitled"),
        text("creator", "Unknown author"),
        package_path,
        cover,
        tuple(
            " ".join("".join(e.itertext()).split())[:200] for e in metadata.findall(f"{DC}subject")
        )[:30],
        text("description", ""),
    )


def sanitize_documents(root: Path) -> None:
    """Remove active elements as defense in depth; iframe sandbox and CSP also apply."""
    blocked = {"script", "iframe", "object", "embed", "form", "base", "foreignobject"}
    for path in root.rglob("*"):
        if path.suffix.lower() not in (".xhtml", ".html", ".htm", ".svg") or not path.is_file():
            continue
        document = parse_xml(path)
        for parent in document.iter():
            for child in list(parent):
                local = child.tag.split("}")[-1].lower()
                if local in blocked or (
                    local == "meta" and child.get("http-equiv", "").lower() == "refresh"
                ):
                    parent.remove(child)
            for key, value in list(parent.attrib.items()):
                local = key.split("}")[-1].lower()
                compact = "".join(value.split()).lower()
                if local.startswith("on") or (
                    local in ("href", "src", "action")
                    and compact.startswith(("javascript:", "file:", "vbscript:"))
                ):
                    del parent.attrib[key]
        path.write_bytes(ET.tostring(document, encoding="utf-8", xml_declaration=True))

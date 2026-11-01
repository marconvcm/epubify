import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt, QUrl
from PySide6.QtGui import QImage, QImageReader, QTextDocument

from epub_reader.core.typography import MONO_FAMILY, MONO_TAGS
from epub_reader.infrastructure.epub.extraction import (
    EpubError,
    contained_resource,
    resolve_reference,
)
from epub_reader.infrastructure.epub.parser import parse_xml
from epub_reader.rendering.navigation_layout import NavigationBlock, prepare_navigation
from epub_reader.rendering.publication import Publication, image_anchor, local_name

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageAnchor:
    source: str
    names: tuple[str, ...]


def chapter_markup(
    root: Path, chapter: str, publication: Publication
) -> tuple[str, str, tuple[ImageAnchor, ...], dict[str, NavigationBlock]]:
    document = parse_xml(contained_resource(root, chapter))
    styles = []
    parents = {child: parent for parent in document.iter() for child in parent}
    image_index = 0
    images: list[ImageAnchor] = []
    nodes = list(document.iter())
    code_nodes: set[ET.Element] = set()
    for parent in nodes:
        if local_name(parent) in MONO_TAGS or parents.get(parent) in code_nodes:
            code_nodes.add(parent)
            parent.set("style", parent.get("style", "") + f"; font-family: '{MONO_FAMILY}';")
        if local_name(parent) == "img":
            image_index += 1
            names = [image_anchor(image_index)]
            element = parent
            if element.get("id"):
                names.append(element.attrib["id"])
            # A figure/paragraph beginning with this image has the same target.
            # Qt can otherwise put empty named anchors on the following block.
            while element in parents:
                owner = parents[element]
                if list(owner).index(element) or (owner.text or "").strip():
                    break
                if owner.get("id"):
                    names.append(owner.attrib["id"])
                element = owner
            images.append(ImageAnchor(parent.get("src", ""), tuple(names)))
    image_index = 0
    for parent in nodes:
        identifier = parent.get("id")
        if identifier:
            # QTextDocument supports named anchors consistently, including EPUB 3 ids.
            anchor = ET.Element("a", {"name": identifier})
            if local_name(parent) in {"img", "br", "hr"} and parent in parents:
                owner = parents[parent]
                owner.insert(list(owner).index(parent), anchor)
            else:
                anchor.tail = parent.text
                parent.text = None
                parent.insert(0, anchor)
        if local_name(parent) == "img" and parent in parents:
            image_index += 1
            owner = parents[parent]
            owner.insert(
                list(owner).index(parent), ET.Element("a", {"name": image_anchor(image_index)})
            )
        parent.attrib.pop("bgcolor", None)
        for child in list(parent):
            if child.tag.split("}")[-1] == "link":
                if "stylesheet" in child.get("rel", "").split():
                    try:
                        path = contained_resource(
                            root, resolve_reference(chapter, child.get("href", ""))
                        )
                        if path.stat().st_size <= 1_000_000:
                            styles.append(path.read_text(encoding="utf-8", errors="replace"))
                    except (EpubError, OSError):
                        logger.info("Ignored inaccessible publication stylesheet")
                parent.remove(child)
    navigation = prepare_navigation(document, chapter, publication)
    return (
        ET.tostring(document, encoding="unicode", method="html"),
        "\n".join(styles),
        tuple(images),
        navigation,
    )


class PublicationDocument(QTextDocument):
    """Qt's rich-text document with a confined, offline resource loader."""

    def __init__(self, root: Path, chapter: str, image_size: QSize) -> None:
        super().__init__()
        self.root, self.chapter, self.image_size = root, chapter, image_size
        self.setUndoRedoEnabled(False)
        self.setBaseUrl(QUrl(f"epub://publication/{chapter}"))
        self.setDocumentMargin(0)

    def loadResource(self, resource_type: int, name: QUrl | str) -> Any:
        name = QUrl(name)
        if name.scheme() != "epub" or name.host() != "publication":
            logger.debug("Blocked document resource: %s", name.toString())
            return QByteArray()
        try:
            path = contained_resource(self.root, unquote(name.path().lstrip("/")))
            if resource_type == QTextDocument.ResourceType.StyleSheetResource:
                return path.read_text(encoding="utf-8") if path.stat().st_size <= 1_000_000 else ""
            if resource_type != QTextDocument.ResourceType.ImageResource:
                return QByteArray()
            # Decode from memory, with no file base URL for nested SVG references.
            if path.stat().st_size > 16 * 1024 * 1024:
                return QImage()
            data = path.read_bytes()
            if path.suffix.lower() == ".svg":
                svg = parse_xml(path)
                for element in svg.iter():
                    for key, value in list(element.attrib.items()):
                        if key.split("}")[-1] == "href" and not value.startswith("#"):
                            del element.attrib[key]
                data = ET.tostring(svg, encoding="utf-8")
            buffer = QBuffer()
            buffer.setData(data)
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            reader = QImageReader(buffer)
            size = reader.size()
            if (
                not size.isValid()
                or size.width() * size.height() > 40_000_000
                or max(size.width(), size.height()) > 16000
            ):
                return QImage()
            if size.width() > self.image_size.width() or size.height() > self.image_size.height():
                reader.setScaledSize(
                    size.scaled(self.image_size, Qt.AspectRatioMode.KeepAspectRatio)
                )
            reader.setAutoTransform(True)
            return reader.read()
        except (EpubError, OSError, ValueError):
            logger.info("Could not load confined document resource: %s", name.toString())
            return QByteArray()

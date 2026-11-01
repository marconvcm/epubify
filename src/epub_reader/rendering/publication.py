from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree.ElementTree import Element

from epub_reader.infrastructure.epub.extraction import (
    EpubError,
    contained_resource,
    resolve_reference,
)
from epub_reader.infrastructure.epub.parser import OPF, parse_xml

MAX_ENTRIES = 2000
MAX_DEPTH = 32
EPUB_TYPE = "{http://www.idpf.org/2007/ops}type"


def local_name(element: Element) -> str:
    return element.tag.split("}")[-1].lower()


@dataclass(frozen=True)
class Chapter:
    path: str
    label: str


@dataclass(frozen=True)
class NavigationEntry:
    label: str
    href: str
    depth: int = 0
    parent: int = -1


@dataclass(frozen=True)
class Publication:
    root: Path
    chapters: tuple[Chapter, ...]
    contents: tuple[NavigationEntry, ...]
    figures: tuple[NavigationEntry, ...] = ()


def reference(base: str, href: str) -> str:
    url = urlsplit(href)
    if url.scheme or url.netloc:
        raise EpubError("External publication links are disabled.")
    path = resolve_reference(base, url.path) if url.path else base
    return path + ("#" + unquote(url.fragment) if url.fragment else "")


def _target(base: str, href: str) -> str:
    try:
        return reference(base, href) if href else ""
    except ValueError:
        return ""


def _html_navigation(document: Element, base: str, kinds: set[str]) -> list[NavigationEntry]:
    result: list[NavigationEntry] = []

    def visit(container: Element, parent: int, depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        for li in container:
            if local_name(li) != "li" or len(result) >= MAX_ENTRIES:
                continue
            label = next((e for e in li if local_name(e) in ("a", "span")), None)
            nested_parent = parent
            if label is not None:
                text = " ".join("".join(label.itertext()).split())[:1000]
                href = _target(base, label.get("href", ""))
                if text:
                    nested_parent = len(result)
                    result.append(NavigationEntry(text, href, depth, parent))
            for child in li:
                if local_name(child) in ("ol", "ul"):
                    visit(child, nested_parent, depth + 1)

    for nav in document.iter():
        if local_name(nav) == "nav" and set(nav.get(EPUB_TYPE, "").split()) & kinds:
            for container in nav:
                if local_name(container) in ("ol", "ul"):
                    visit(container, -1, 0)
            if "toc" in kinds:
                break
    return result


def _ncx_navigation(container: Element, base: str) -> list[NavigationEntry]:
    result: list[NavigationEntry] = []

    def visit(element: Element, parent: int, depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        for point in element:
            if local_name(point) not in ("navpoint", "navtarget") or len(result) >= MAX_ENTRIES:
                continue
            label = next((e for e in point if local_name(e) == "navlabel"), None)
            target = next((e for e in point if local_name(e) == "content"), None)
            text = " ".join("".join(label.itertext()).split()) if label is not None else "Chapter"
            index = len(result)
            result.append(
                NavigationEntry(
                    text[:1000],
                    _target(base, target.get("src", "")) if target is not None else "",
                    depth,
                    parent,
                )
            )
            visit(point, index, depth + 1)

    visit(container, -1, 0)
    return result


def load_publication(root: Path, package_path: str) -> Publication:
    package = parse_xml(contained_resource(root, package_path))
    items = {item.get("id", ""): item for item in package.findall(f"{OPF}manifest/{OPF}item")}
    chapters: list[Chapter] = []
    for itemref in package.findall(f"{OPF}spine/{OPF}itemref"):
        if itemref.get("linear") == "no":
            continue
        item = items.get(itemref.get("idref", ""))
        if item is None:
            raise EpubError("The reading spine references a missing chapter.")
        path = resolve_reference(package_path, item.get("href", ""))
        chapters.append(Chapter(path, f"Chapter {len(chapters) + 1}"))
    if not chapters:
        raise EpubError("The publication has no readable chapters.")
    contents: list[NavigationEntry] = []
    figures: list[NavigationEntry] = []
    nav = next(
        (item for item in items.values() if "nav" in item.get("properties", "").split()), None
    )
    if nav is not None:
        path = resolve_reference(package_path, nav.get("href", ""))
        document = parse_xml(contained_resource(root, path))
        contents = _html_navigation(document, path, {"toc"})
        figures = _html_navigation(document, path, {"loi", "lof", "list-of-figures"})
    ncx = next(
        (item for item in items.values() if item.get("media-type") == "application/x-dtbncx+xml"),
        None,
    )
    if ncx is not None and not contents:
        path = resolve_reference(package_path, ncx.get("href", ""))
        document = parse_xml(contained_resource(root, path))
        for element in document:
            if local_name(element) == "navmap":
                contents = _ncx_navigation(element, path)
    if not contents:
        contents = [NavigationEntry(c.label, c.path) for c in chapters]
    return Publication(root, tuple(chapters), tuple(contents), tuple(figures))


def image_anchor(index: int) -> str:
    return f"epubify-image-{index}"


def scan_figures(publication: Publication) -> tuple[NavigationEntry, ...]:
    """Fallback index for books without a declared illustration navigation list."""
    figures: list[NavigationEntry] = []
    for chapter in publication.chapters:
        try:
            document = parse_xml(contained_resource(publication.root, chapter.path))
        except EpubError:
            continue
        parents = {child: parent for parent in document.iter() for child in parent}
        image_index = 0
        cover = Path(chapter.path).stem.casefold() in {"cover", "coverpage", "titlepage"}
        for image in document.iter():
            if local_name(image) != "img":
                continue
            image_index += 1
            if (
                cover
                or not image.get("src")
                or image.get("role") == "presentation"
                or image.get("aria-hidden") == "true"
            ):
                continue
            ancestor = parents.get(image)
            caption = ""
            while ancestor is not None:
                if local_name(ancestor) == "figure":
                    caption = " ".join(
                        " ".join("".join(e.itertext()).split())
                        for e in ancestor.iter()
                        if local_name(e) == "figcaption"
                    )
                    break
                ancestor = parents.get(ancestor)
            label = caption or image.get("alt", "").strip() or image.get("title", "").strip()
            if not label and image.get("alt") == "":
                continue  # Explicitly decorative image, unless it has a caption/title.
            figures.append(
                NavigationEntry(
                    (label or f"Figure {len(figures) + 1}")[:1000],
                    f"{chapter.path}#{image_anchor(image_index)}",
                )
            )
            if len(figures) >= MAX_ENTRIES:
                return tuple(figures)
    return tuple(figures)

"""Compact layout metadata for navigation pages without changing their text offsets."""

from dataclasses import dataclass
from xml.etree.ElementTree import Element

from epub_reader.rendering.publication import EPUB_TYPE, Publication, local_name, reference

BLOCKS = {"p", "li", "div", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6"}
NAVIGATION_TYPES = {"toc", "loi", "lof", "lot", "list-of-figures", "list-of-tables"}


@dataclass(frozen=True)
class NavigationBlock:
    depth: int
    kind: str  # title, entry or group


def _label(element: Element) -> str:
    return " ".join("".join(element.itertext()).split()).casefold()


def prepare_navigation(
    document: Element, chapter: str, publication: Publication
) -> dict[str, NavigationBlock]:
    parents = {child: parent for parent in document.iter() for child in parent}
    roots = {
        e
        for e in document.iter()
        if set(e.get(EPUB_TYPE, "").split()) & NAVIGATION_TYPES
        or e.get("role") in {"doc-toc", "doc-list-of-illustrations", "doc-list-of-tables"}
    }
    if not roots:
        return {}
    entries = (*publication.contents, *publication.figures)
    targets = {e.href: e.depth for e in reversed(entries) if e.href}
    labels = {(e.href.partition("#")[0], e.label.casefold()): e.depth for e in reversed(entries)}
    blocks: dict[Element, NavigationBlock] = {}

    def inside(element: Element) -> bool:
        while element not in roots:
            if element not in parents:
                return False
            element = parents[element]
        return True

    def structural_depth(element: Element) -> int:
        lists = 0
        ancestor = element
        while ancestor not in roots and ancestor in parents:
            ancestor = parents[ancestor]
            lists += local_name(ancestor) in {"ol", "ul"}
        tag = local_name(element)
        return max(0, lists - 1) if lists else max(0, int(tag[1]) - 2) if tag[0] == "h" else 0

    for link in document.iter():
        if local_name(link) != "a" or not link.get("href") or not inside(link):
            continue
        block = parents.get(link)
        while block is not None and local_name(block) not in BLOCKS:
            block = parents.get(block)
        if block is None:
            continue
        try:
            href = reference(chapter, link.attrib["href"])
        except ValueError:
            href = ""
        depth = targets.get(href)
        if depth is None:
            # Publishers often use different id aliases in NCX and the visible TOC.
            depth = labels.get((href.partition("#")[0], _label(link)))
        if depth is None:
            depth = structural_depth(block)
        blocks.setdefault(block, NavigationBlock(min(12, depth), "entry"))

    for element in document.iter():
        tag = local_name(element)
        if element in blocks or not inside(element):
            continue
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and _label(element):
            blocks[element] = NavigationBlock(
                structural_depth(element), "title" if tag == "h1" else "group"
            )
        elif tag == "li" and (element.text or "").strip():
            blocks[element] = NavigationBlock(structural_depth(element), "group")

    result = {}
    for index, (element, style) in enumerate(blocks.items()):
        marker = f"epubify-navigation-{index}"
        anchor = Element("a", {"name": marker})
        anchor.tail, element.text = element.text, None
        element.insert(0, anchor)
        result[marker] = style
    return result

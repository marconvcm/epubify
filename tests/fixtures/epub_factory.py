"""Deterministic, original test publications under the project MIT license."""

import struct
import zlib
from html import escape
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
 <rootfiles>
  <rootfile full-path="EPUB/book.opf" media-type="application/oebps-package+xml"/>
 </rootfiles>
</container>"""


def cover_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\x00" + bytes([52, 67, 63]) * 8) * 8))
        + chunk(b"IEND", b"")
    )


def make_epub(
    path: Path,
    *,
    version: int = 3,
    title: str = "The Quiet Library",
    author: str = "Epubify Contributors",
    extra: dict[str, bytes] | None = None,
    active_content: bool = False,
    subjects: tuple[str, ...] = (),
    description: str = "",
) -> Path:
    navigation = (
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        if version == 3
        else '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
    )
    subject_xml = "".join(f"<dc:subject>{escape(value)}</dc:subject>" for value in subjects)
    opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="{version}.0" unique-identifier="uid">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:identifier id="uid">urn:epubify:fixture</dc:identifier><dc:title>{escape(title)}</dc:title>
  <dc:creator>{escape(author)}</dc:creator><dc:language>en</dc:language>
  {subject_xml}<dc:description>{escape(description)}</dc:description>
  <meta name="cover" content="cover"/><meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>
 </metadata>
 <manifest>{navigation}<item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  <item id="c2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
  <item id="cover" href="cover.png" media-type="image/png" properties="cover-image"/>
  <item id="css" href="style.css" media-type="text/css"/></manifest>
 <spine toc="ncx"><itemref idref="c1"/><itemref idref="c2"/></spine>
</package>'''
    paragraph = (
        "A quiet room leaves space for a new idea. "
        "The reader turns a page, and the story continues. "
    )
    active = (
        "<script>window.__epub_script_executed = true</script>"
        '<img src="cover.png" onerror="alert(1)"/>'
        if active_content
        else ""
    )

    def chapter(number: int) -> bytes:
        paragraphs = "".join(f'<p id="p{i}">{paragraph * 4}</p>' for i in range(30))
        return f"""<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter {number}</title>
<link rel="stylesheet" href="style.css"/></head><body><h1>Chapter {number}</h1>{active}
<img src="cover.png" alt="A green square"/>{paragraphs}
<a href="chapter2.xhtml#p5">Continue to the next chapter</a></body></html>""".encode()

    nav = b"""<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Contents</title></head><body><nav epub:type="toc"><ol>
<li><a href="chapter1.xhtml">A quiet room</a></li>
<li><a href="chapter2.xhtml">The next idea</a></li>
</ol></nav></body></html>"""
    ncx = b"""<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head/>
<docTitle><text>The Quiet Library</text></docTitle><navMap>
<navPoint id="n1" playOrder="1"><navLabel><text>A quiet room</text></navLabel>
<content src="chapter1.xhtml"/></navPoint>
<navPoint id="n2" playOrder="2"><navLabel><text>The next idea</text></navLabel>
<content src="chapter2.xhtml"/></navPoint>
</navMap></ncx>"""
    entries = {
        "mimetype": b"application/epub+zip",
        "META-INF/container.xml": CONTAINER.encode(),
        "EPUB/book.opf": opf.encode(),
        "EPUB/chapter1.xhtml": chapter(1),
        "EPUB/chapter2.xhtml": chapter(2),
        "EPUB/nav.xhtml": nav,
        "EPUB/toc.ncx": ncx,
        "EPUB/cover.png": cover_png(),
        "EPUB/style.css": b"p { margin: 0 0 1em } img { width: 48px }",
    }
    entries.update(extra or {})
    with ZipFile(path, "w") as archive:
        for name, content in entries.items():
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_STORED
            archive.writestr(info, content)
    return path

from pathlib import Path

from tests.fixtures.epub_factory import make_epub


def make_navigation_epub(path: Path, *, version: int = 3, declared_figures: bool = True) -> Path:
    nav = """<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Book navigation</title></head><body>
<nav epub:type="toc"><ol>
<li><a href="chapter1.xhtml#start">A quiet room</a><ol>
 <li><a href="chapter1.xhtml#p1">Quiet spaces</a><ol>
  <li><a href="chapter1.xhtml#p10">Morning light</a></li>
 </ol></li></ol></li>
<li><a href="chapter2.xhtml#start">The next idea</a><ol>
 <li><a href="chapter2.xhtml#p12">Working with images</a></li>
</ol></li></ol></nav>"""
    if declared_figures:
        nav += """<nav epub:type="loi"><ol>
<li><a href="chapter1.xhtml#figure-a">Figure 1 — The reading garden</a></li>
<li><a href="chapter2.xhtml#figure-a">Figure 2 — A place for ideas</a></li>
</ol></nav>"""
    nav += "</body></html>"
    ncx = """<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head/>
<docTitle><text>A quiet room</text></docTitle><navMap>
<navPoint id="a"><navLabel><text>A quiet room</text></navLabel><content src="chapter1.xhtml#start"/>
 <navPoint id="b"><navLabel><text>Quiet spaces</text></navLabel><content src="chapter1.xhtml#p1"/>
  <navPoint id="c"><navLabel><text>Morning light</text></navLabel>
<content src="chapter1.xhtml#p10"/></navPoint>
 </navPoint></navPoint>
<navPoint id="d"><navLabel><text>The next idea</text></navLabel>
<content src="chapter2.xhtml#start"/>
 <navPoint id="e"><navLabel><text>Working with images</text></navLabel>
<content src="chapter2.xhtml#p12"/></navPoint>
</navPoint></navMap></ncx>"""

    def chapter(number: int) -> bytes:
        text = (
            "A quiet room leaves space for a new idea. The light moves across the page, "
            "and there is time to notice the details. "
        )
        content = "".join(f'<p id="p{i}">{text * 4}</p>' for i in range(18))
        return f"""<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>A quiet room</title></head>
<body><h1 id="start">{"A quiet room" if number == 1 else "The next idea"}</h1>
<p><a href="chapter2.xhtml#p12">Go to Working with images</a></p>{content}
<figure id="figure-a"><img id="illustration" src="cover.png" width="180" height="180"/>
<figcaption>Figure {number} — {"The reading garden" if number == 1 else "A place for ideas"}
</figcaption></figure>
<p><img src="cover.png" alt="" width="8" height="8"/></p>
</body></html>""".encode()

    return make_epub(
        path,
        version=version,
        title="The Quiet Library",
        extra={
            "EPUB/nav.xhtml": nav.encode(),
            "EPUB/toc.ncx": ncx.encode(),
            "EPUB/chapter1.xhtml": chapter(1),
            "EPUB/chapter2.xhtml": chapter(2),
        },
    )

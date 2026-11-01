"""Original flat-heading contents like EPUB exports that require native indentation."""

from pathlib import Path

from tests.fixtures.epub_factory import make_epub


def make_contents_epub(path: Path, *, nested: bool = False, semantic: bool = True) -> Path:
    nav = b"""<html xmlns="http://www.w3.org/1999/xhtml"
xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Navigation</title></head><body>
<nav epub:type="toc"><ol><li><a href="chapter1.xhtml">Contents</a></li>
<li><a href="chapter2.xhtml#part">Part One</a></li>
<li><a href="chapter2.xhtml#chapter">Chapter One</a><ol>
<li><a href="chapter2.xhtml#section-nav">Finding a quiet place</a><ol>
<li><a href="chapter2.xhtml#detail-nav">A garden for reading</a></li>
</ol></li></ol></li></ol></nav></body></html>"""
    entries = """<h2><a href="chapter2.xhtml#part">Part One</a></h2>
<h2><a href="chapter2.xhtml#chapter">Chapter One</a></h2>
<h3 id="section-link"><a href="chapter2.xhtml#section">Finding a quiet place</a></h3>
<h3><a href="chapter2.xhtml#detail">A garden for reading</a></h3>"""
    if nested:
        entries = """<ol><li><a href="chapter2.xhtml#part">Part One</a></li>
<li><a href="chapter2.xhtml#chapter">Chapter One</a><ol>
<li id="section-link"><a href="chapter2.xhtml#section">Finding a quiet place</a><ol>
<li><a href="chapter2.xhtml#detail">A garden for reading</a></li>
</ol></li></ol></li></ol>"""
    marker = 'epub:type="toc"' if semantic else ""
    contents = f"""<html xmlns="http://www.w3.org/1999/xhtml"
xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title>
<link href="style.css" rel="stylesheet"/></head><body>
<div {marker}><h1>Table of Contents</h1>{entries}</div></body></html>"""
    prose = b"""<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Reading</title></head>
<body><h1 id="part">Part One</h1><h2 id="chapter">Chapter One</h2>
<h2 id="section"><a id="section-nav"/>Finding a quiet place</h2>
<p>A quiet place makes room for a new idea.</p>
<h3 id="detail"><a id="detail-nav"/>A garden for reading</h3>
<p>The garden changes as the afternoon goes by.</p></body></html>"""
    return make_epub(
        path,
        extra={
            "EPUB/nav.xhtml": nav,
            "EPUB/chapter1.xhtml": contents.encode(),
            "EPUB/chapter2.xhtml": prose,
            "EPUB/style.css": b"h2,h3 { font-size: 30px; margin-top: 45px; margin-bottom: 30px; }",
        },
    )

"""Original EPUB layout and resource isolation in the web reader."""

from pathlib import Path
from urllib.parse import quote
import zipfile

from bs4 import BeautifulSoup
import pytest

from modu.web_epub import EpubBook


PREFIX = "/reader/epub/"
SVG = "http://www.w3.org/2000/svg"


def fixture_epub(path: Path, *, epub3=False):
    navigation = (
        '<item id="toc" href="toc.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        if epub3
        else '<item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="EPUB/content.opf"/></rootfiles></container>',
        )
        archive.writestr(
            "EPUB/content.opf",
            f"""<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">
            <metadata><dc:language>en-GB</dc:language></metadata><manifest>
            <item id="ch1" href="text/01.xhtml" media-type="application/xhtml+xml"/>
            <item id="ch2" href="text/02%20section.xhtml" media-type="application/xhtml+xml"/>
            <item id="note" href="text/note.xhtml" media-type="application/xhtml+xml"/>
            <item id="cover" href="cover.svg" media-type="image/svg+xml"/>
            <item id="art" href="images/图%20one.png" media-type="image/png"/>
            <item id="main" href="styles/main.css" media-type="text/css"/>
            <item id="base" href="styles/base.css" media-type="text/css"/>
            <item id="font" href="fonts/reading.woff2" media-type="font/woff2"/>
            <item id="malicious" href="bad.js" media-type="text/javascript"/>
            {navigation}</manifest><spine toc="toc">
            <itemref idref="ch1"/><itemref idref="note" linear="no"/><itemref idref="ch2"/>
            </spine></package>""",
        )
        archive.writestr(
            "EPUB/toc.ncx",
            """<ncx><navMap>
            <navPoint><navLabel><text>Part 1</text></navLabel><content src="text/01.xhtml#first"/>
              <navPoint><navLabel><text>Part 2</text></navLabel><content src="text/01.xhtml#second"/></navPoint>
            </navPoint>
            <navPoint><navLabel><text>Appendix</text></navLabel><content src="text/02%20section.xhtml"/></navPoint>
            </navMap></ncx>""",
        )
        archive.writestr(
            "EPUB/toc.xhtml",
            """<html><body><nav epub:type="landmarks"><a href="text/01.xhtml">Ignore</a></nav>
            <nav epub:type="toc"><ol><li><a href="text/01.xhtml#second">Second chapter</a></li>
            <li><a href="text/02%20section.xhtml">Appendix</a></li></ol></nav></body></html>""",
        )
        archive.writestr(
            "EPUB/text/01.xhtml",
            f"""<html><head><title>Original title</title>
            <meta http-equiv="refresh" content="0; url=https://example.invalid">
            <base href="https://example.invalid/"><link rel="prefetch" href="../styles/base.css">
            <link rel="stylesheet" href="../styles/main.css">
            <style>.illustration {{ background: url('../images/图 one.png'); }}</style>
            </head><body onload="bad()">
            <h1 id="first">First chapter</h1><p><i>Italic</i>, <ruby>字<rt>zì</rt></ruby></p>
            <table><tr><td>Table cell</td></tr></table>
            <img class="illustration" src="../images/图%20one.png" srcset="https://example.invalid">
            <img src="https://example.invalid"><img src="../unlisted.png">
            <a href="#second">On this page</a>
            <a href="02%20section.xhtml#with%20space" target="_blank" ping="/outside">Next</a>
            <a href="note.xhtml#note">Note</a><a href="javascript:bad()">Bad link</a>
            <a href="%2e%2e/%2e%2e/%2e%2e/outside">Escape</a>
            <a href="../bad.js">Script link</a><script src="../bad.js"></script>
            <iframe src="/outside"></iframe><form action="/outside"><input name="secret"></form>
            <svg xmlns="{SVG}" viewBox="0 0 10 10" onload="bad()">
              <image xlink:href="../images/图%20one.png" width="10" height="10"></image>
              <foreignObject><iframe src="/outside"></iframe></foreignObject>
            </svg><h2 id="second">Second chapter</h2>
            </body></html>""",
        )
        archive.writestr("EPUB/text/02 section.xhtml", '<p id="with space">Appendix text</p>')
        archive.writestr("EPUB/text/note.xhtml", '<p id="note">Book note</p>')
        archive.writestr(
            "EPUB/cover.svg",
            f"""<svg xmlns="{SVG}" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 10 10">
              <image xlink:href="images/图%20one.png" width="10" height="10" onerror="bad()"/>
              <script>bad()</script><foreignObject><p>Unsafe</p></foreignObject>
              <rect width="10" height="10" style="fill:url(#ink)"/>
            </svg>""",
        )
        archive.writestr("EPUB/images/图 one.png", b"PNG fixture")
        archive.writestr(
            "EPUB/styles/main.css",
            """@import "base.css";
            @font-face {font-family: Reading; src: url(../fonts/reading.woff2)}
            p {color: #654321; background: url('../../outside')}
            div { background: url("https://example.invalid/pixel.png"); }""",
        )
        archive.writestr("EPUB/styles/base.css", "table {border-collapse: collapse}")
        archive.writestr("EPUB/fonts/reading.woff2", b"Font fixture")
        archive.writestr("EPUB/bad.js", "bad()")
        archive.writestr("EPUB/unlisted.png", b"Not declared")
    return EpubBook(path)


@pytest.mark.parametrize("epub3", [False, True])
def test_spine_and_original_toc_fragments(tmp_path, epub3):
    book = fixture_epub(tmp_path / "book.epub", epub3=epub3)
    assert book.language == "en-GB"
    assert [chapter.name for chapter in book.chapters] == [
        "EPUB/text/01.xhtml", "EPUB/text/02 section.xhtml",
    ]
    assert [(chapter.label, chapter.fragment) for chapter in book.toc] == (
        [("Second chapter", "second"), ("Appendix", "")]
        if epub3
        else [("Part 1", "first"), ("Part 2", "second"), ("Appendix", "")]
    )
    _, note = book.resource("EPUB/text/note.xhtml", prefix=PREFIX)
    assert b"Book note" in note


def test_local_html_assets_and_active_content_removed(tmp_path):
    book = fixture_epub(tmp_path / "book.epub")
    css = "html {background: #111; color: #eee}"
    media, data = book.resource(book.chapters[0].name, prefix=PREFIX, css=css)
    assert media == "text/html; charset=utf-8"
    soup = BeautifulSoup(data, "html.parser")
    assert soup.i.string == "Italic" and soup.rt.string == "zì" and soup.td.string == "Table cell"
    image_url = PREFIX + quote("EPUB/images/图 one.png")
    assert [tag["src"] for tag in soup.find_all("img", src=True)] == [image_url]
    assert soup.image["xlink:href"] == image_url
    assert soup.link["href"] == PREFIX + "EPUB/styles/main.css"
    assert image_url in soup.style.string
    assert soup.find_all("style")[-1].string == css
    assert [a["href"] for a in soup.find_all("a", href=True)] == [
        "#second", PREFIX + "EPUB/text/02%20section.xhtml#with%20space",
        PREFIX + "EPUB/text/note.xhtml#note",
    ]
    assert soup.find(["base", "meta", "script", "iframe", "form", "foreignobject"]) is None
    assert b"example.invalid" not in data and b"onload" not in data and b"target=" not in data
    for name in ("EPUB/bad.js", "EPUB/unlisted.png", "../cover.svg", "META-INF/container.xml"):
        with pytest.raises(KeyError):
            book.resource(name, prefix=PREFIX)


def test_css_fonts_and_svg_resources(tmp_path):
    book = fixture_epub(tmp_path / "book.epub")
    media, css = book.resource("EPUB/styles/main.css", prefix=PREFIX)
    assert media == "text/css; charset=utf-8"
    assert b'@import "/reader/epub/EPUB/styles/base.css"' in css
    assert b'url("/reader/epub/EPUB/fonts/reading.woff2")' in css
    assert b"#654321" in css and b"example.invalid" not in css and b"outside" not in css
    assert book.resource("EPUB/fonts/reading.woff2", prefix=PREFIX) == ("font/woff2", b"Font fixture")
    assert book.resource("EPUB/images/图 one.png", prefix=PREFIX) == ("image/png", b"PNG fixture")
    media, cover = book.resource("EPUB/cover.svg", prefix=PREFIX)
    assert media == "image/svg+xml"
    assert b'viewBox="0 0 10 10"' in cover and b"url(&quot;#ink&quot;)" in cover
    assert quote("EPUB/images/图 one.png").encode() in cover
    for tag in (b"script", b"foreignObject", b"onerror"):
        assert tag not in cover


def test_rejects_noncanonical_zip_member(tmp_path):
    path = tmp_path / "book.epub"
    fixture_epub(path)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("EPUB/../other.txt", "Unrelated data")
    with pytest.raises(ValueError, match="unsupported archive members"):
        EpubBook(path)

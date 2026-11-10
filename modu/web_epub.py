"""Serve an EPUB's original layout from its bounded, local publication resources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from posixpath import dirname, join, normpath
import re
from urllib.parse import quote, unquote, urlsplit
import zipfile
import zlib

from bs4 import BeautifulSoup, Comment, Doctype, ProcessingInstruction
from defusedxml import ElementTree as SafeET

from .model import clean
from .parsers import decode
from .safety import MAX_ARCHIVE_BYTES, MAX_ARCHIVE_MEMBERS, MAX_MEMBER_BYTES, MAX_SOURCE_BYTES


HTML_TYPES = {"text/html", "application/xhtml+xml"}
DOCUMENT_TYPES = HTML_TYPES | {"image/svg+xml"}
IMAGE_TYPES = {
    "image/svg+xml", "image/jpeg", "image/png", "image/gif", "image/webp", "image/avif", "image/bmp",
}
FONT_TYPES = {
    "font/otf": "font/otf",
    "font/ttf": "font/ttf",
    "font/woff": "font/woff",
    "font/woff2": "font/woff2",
    "application/vnd.ms-opentype": "font/otf",
    "application/font-sfnt": "font/otf",
    "application/x-font-ttf": "font/ttf",
    "application/x-font-otf": "font/otf",
    "application/font-woff": "font/woff",
}
NCX_TYPE = "application/x-dtbncx+xml"
ASSET_TYPES = IMAGE_TYPES | FONT_TYPES.keys() | {"text/css"}
RENDER_TYPES = HTML_TYPES | ASSET_TYPES

HTML_TAGS = frozenset(
    """
    html head body title link style a abbr address article aside b bdi bdo blockquote br caption
    cite code col colgroup dd del details dfn div dl dt em figcaption figure footer h1 h2 h3 h4 h5
    h6 header hgroup hr i img ins kbd li main mark nav ol p pre q rp rt ruby s samp section small
    span strong sub summary sup table tbody td tfoot th thead time tr u ul var wbr math mrow mi mn
    mo mfrac msqrt mroot msub msup msubsup mover munder munderover mtable mtr mtd mtext mspace
    mstyle mfenced mpadded mphantom semantics
    """.split()
)
DROP_TAGS = frozenset(
    """
    script base meta iframe frame frameset object embed applet portal template noscript form
    input select textarea button video audio source track foreignobject annotation-xml
    """.split()
)
SVG_TAGS = frozenset(
    """
    svg a title desc g symbol defs image use path rect circle ellipse line polyline polygon
    text tspan textpath lineargradient radialgradient stop pattern clippath mask marker
    filter feblend fecolormatrix fecomponenttransfer fecomposite feconvolvematrix fediffuselighting
    fedisplacementmap fedistantlight fedropshadow feflood fefunca fefuncb fefuncg fefuncr
    fegaussianblur femerge femergenode femorphology feoffset fepointlight fespecularlighting
    fespotlight fetile feturbulence style
    """.split()
)
HTML_ATTRIBUTES = frozenset(
    """
    id class title lang xml:lang dir hidden role style xmlns xmlns:epub epub:type name alt width
    height align valign colspan rowspan scope headers abbr start reversed value type datetime
    open display mathvariant mathsize mathcolor mathbackground stretchy fence separator lspace
    rspace form linethickness notation encoding
    """.split()
)
SVG_ATTRIBUTES = frozenset(
    """
    xmlns:xlink viewbox preserveaspectratio x y x1 x2 y1 y2 cx cy r rx ry dx dy rotate points d
    pathlength transform gradienttransform patterntransform gradientunits patternunits
    patterncontentunits clippathunits maskunits maskcontentunits markerunits markerwidth
    markerheight orient refx refy spreadmethod offset stop-color stop-opacity fill fill-opacity
    fill-rule stroke stroke-width stroke-opacity stroke-linecap stroke-linejoin stroke-dasharray
    stroke-dashoffset stroke-miterlimit opacity color clip-path clip-rule mask marker-start
    marker-mid marker-end filter filterunits primitiveunits flood-color flood-opacity
    lighting-color display visibility overflow font-size font-family font-weight font-style
    text-anchor dominant-baseline alignment-baseline baseline-shift letter-spacing word-spacing
    textlength lengthadjust startoffset in in2 result stddeviation values mode operator k1 k2 k3
    k4 type radius scale xchannelselector ychannelselector color-interpolation-filters
    """.split()
)
_CONTROLS = re.compile(r"[\x00-\x1f\x7f]")
_LANGUAGE_TAG = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*")
# Preserve strings and comments, and rewrite conventional url() and quoted @import references.
# A path-scoped CSP in the HTTP response covers escaped CSS syntax and other CSS fetch functions.
_CSS_TOKEN = re.compile(
    r"""(?P<comment>/\*[\s\S]*?\*/)|"""
    r"""(?P<import>@import\s+(?P<import_value>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'))|"""
    r"""(?<![-\w])(?P<url>url\(\s*(?P<url_value>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^()"'\s]*)\s*\))|"""
    r"""(?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EpubChapter:
    name: str
    label: str
    fragment: str = ""


def _valid_name(name: str) -> bool:
    return bool(
        name
        and name not in {".", ".."}
        and not name.startswith(("/", "../"))
        and "\\" not in name
        and not _CONTROLS.search(name)
        and name == normpath(name)
    )


def _reference(base: str, raw: str) -> tuple[str, str] | None:
    """Resolve a publication link once, without treating escaped separators as URL syntax."""
    if _CONTROLS.search(raw) or "\\" in raw:
        return None
    try:
        url = urlsplit(raw.strip())
    except ValueError:
        return None
    if url.scheme or url.netloc or url.path.startswith("/"):
        return None
    path, fragment = unquote(url.path), unquote(url.fragment)
    if path.startswith("/") or _CONTROLS.search(path) or _CONTROLS.search(fragment):
        return None
    name = normpath(join(dirname(base), path)) if path else base
    return (name, fragment) if _valid_name(name) else None


def _label(text: str) -> str:
    return " ".join(clean(text).split())[:240]


def _read(archive: zipfile.ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if (
        info.file_size > MAX_MEMBER_BYTES
        or info.flag_bits & 1
        or info.compress_type not in {zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED}
    ):
        raise ValueError("Unsupported EPUB member size or encryption")
    try:
        with archive.open(info) as stream:
            data = stream.read(MAX_MEMBER_BYTES + 1)
    except (zipfile.BadZipFile, zlib.error, RuntimeError) as error:
        raise ValueError("Corrupt EPUB publication resource") from error
    if len(data) > MAX_MEMBER_BYTES:
        raise ValueError("EPUB member exceeds its read limit")
    return data


def _xml(data: bytes, *, forbid_dtd=True):
    try:
        return SafeET.fromstring(data, forbid_dtd=forbid_dtd)
    except SafeET.ParseError as error:
        raise ValueError("Invalid EPUB XML resource") from error


class EpubBook:
    """An EPUB index. Individual XHTML and media resources are loaded on demand."""

    def __init__(self, path: Path):
        self.path = Path(path)
        with self._archive() as archive:
            infos = archive.infolist()
            if (
                len(infos) > MAX_ARCHIVE_MEMBERS
                or sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES
            ):
                raise ValueError("EPUB archive exceeds its resource limits")
            names = {info.filename for info in infos}
            if len(names) != len(infos) or any(
                not _valid_name(info.filename.rstrip("/"))
                or info.file_size > MAX_MEMBER_BYTES
                or info.flag_bits & 1
                for info in infos
            ):
                raise ValueError("EPUB has unsupported archive members")
            container = _xml(_read(archive, "META-INF/container.xml"))
            rootfile = container.find(".//{*}rootfile")
            package_name = rootfile.get("full-path", "") if rootfile is not None else ""
            package_ref = _reference("", package_name)
            if package_ref is None or package_ref[0] not in names:
                raise ValueError("EPUB package document is missing")
            package_name = package_ref[0]
            package = _xml(_read(archive, package_name))
            language = (package.findtext("./{*}metadata/{*}language") or "").strip()[:64]
            self.language = language if _LANGUAGE_TAG.fullmatch(language) else ""
            items = {}
            self._resources = {}
            nav = None
            for item in package.findall("./{*}manifest/{*}item"):
                reference = _reference(package_name, item.get("href", ""))
                media_type = item.get("media-type")
                if reference is None or reference[0] not in names or not media_type:
                    continue
                name = reference[0]
                if name in self._resources and self._resources[name] != media_type:
                    raise ValueError("EPUB member has conflicting media types")
                items[item.get("id")] = name
                self._resources[name] = media_type
                if "nav" in item.get("properties", "").split() and media_type in HTML_TYPES:
                    nav = name

            spine = package.find("./{*}spine")
            if spine is None:
                raise ValueError("EPUB reading order is missing")
            linear, supplemental = [], []
            for entry in spine.findall("./{*}itemref"):
                name = items.get(entry.get("idref"))
                if self._resources.get(name) in DOCUMENT_TYPES:
                    (supplemental if entry.get("linear") == "no" else linear).append(name)
            if not linear and not supplemental:
                raise ValueError("EPUB has no supported reading-order documents")
            toc = self._navigation(archive, nav, items.get(spine.get("toc")))
            labels = {}
            for entry in toc:
                labels.setdefault(entry.name, entry.label)
            self.chapters = tuple(
                EpubChapter(name, labels.get(name) or self._heading(archive, name) or str(number))
                for number, name in enumerate(dict.fromkeys(linear or supplemental), 1)
            )
            self.toc = tuple(toc) or self.chapters

    def _archive(self) -> zipfile.ZipFile:
        if (
            self.path.is_symlink()
            or not self.path.is_file()
            or self.path.stat().st_size > MAX_SOURCE_BYTES
        ):
            raise ValueError("EPUB is missing or exceeds its file size limit")
        try:
            return zipfile.ZipFile(self.path)
        except (zipfile.BadZipFile, zipfile.LargeZipFile) as error:
            raise ValueError("Invalid EPUB archive") from error

    def _navigation(self, archive, nav, ncx):
        links = []
        if nav:
            soup = BeautifulSoup(decode(_read(archive, nav)), "html.parser")
            toc = next(
                (
                    element
                    for element in soup.find_all("nav")
                    if "toc" in element.get("epub:type", "").split()
                    or element.get("role") == "doc-toc"
                ),
                None,
            )
            if toc is not None:
                links.extend(
                    (nav, anchor["href"], anchor.get_text(" ", strip=True))
                    for anchor in toc.find_all("a", href=True)
                )
        if not links and self._resources.get(ncx) == NCX_TYPE:
            try:
                root = _xml(_read(archive, ncx), forbid_dtd=False)
            except ValueError:
                root = None
            if root is not None:
                for point in root.findall("./{*}navMap//{*}navPoint"):
                    label = point.find("./{*}navLabel/{*}text")
                    content = point.find("./{*}content")
                    if label is not None and content is not None:
                        links.append((ncx, content.get("src", ""), "".join(label.itertext())))
        toc, seen = [], set()
        for base, href, title in links:
            ref = _reference(base, href)
            if ref and ref not in seen and self._resources.get(ref[0]) in DOCUMENT_TYPES:
                title = _label(title)
                if title:
                    toc.append(EpubChapter(ref[0], title, ref[1]))
                    seen.add(ref)
        return toc

    def _heading(self, archive, name):
        if self._resources[name] not in HTML_TYPES:
            return ""
        soup = BeautifulSoup(decode(_read(archive, name)), "html.parser")
        tag = soup.find(["h1", "h2", "h3"]) or soup.title
        return _label(tag.get_text(" ", strip=True)) if tag is not None else ""

    def _url(self, base, raw, prefix, allowed, *, local_fragment=False):
        ref = _reference(base, raw)
        if ref is None:
            return None
        name, fragment = ref
        if fragment and raw.strip().startswith("#") and (local_fragment or self._resources.get(name) in allowed):
            return "#" + quote(fragment)
        if self._resources.get(name) not in allowed:
            return None
        return prefix + quote(name, safe="/") + ("#" + quote(fragment) if fragment else "")

    def _css(self, css, name, prefix):
        def replace(match):
            value = match["import_value"] or match["url_value"]
            if value is None:
                return match[0]
            if value[:1] in ('"', "'"):
                value = value[1:-1]
            allowed = {"text/css"} if match["import"] else ASSET_TYPES
            url = self._url(name, value, prefix, allowed, local_fragment=True)
            if match["import"]:
                return '@import "' + (url or "about:blank") + '"'
            return 'url("' + (url or "about:blank") + '")'

        return _CSS_TOKEN.sub(replace, css)

    def _attrs(self, tag, attributes, name, prefix, svg=False):
        allowed = HTML_ATTRIBUTES | SVG_ATTRIBUTES if svg else HTML_ATTRIBUTES
        result = {}
        for key, value in attributes.items():
            short_key = key.rsplit("}", 1)[-1].lower()
            if short_key == "style":
                result[key] = self._css(value, name, prefix)
            elif short_key in {"href", "xlink:href", "src"}:
                if tag == "a" and short_key != "src":
                    target_types = DOCUMENT_TYPES
                elif tag in {"img", "image"}:
                    target_types = IMAGE_TYPES
                elif tag == "link" and short_key == "href":
                    target_types = {"text/css"}
                elif svg and tag in {"use", "textpath", "lineargradient", "radialgradient", "pattern"}:
                    target_types = {"image/svg+xml"}
                else:
                    continue
                target = self._url(name, value, prefix, target_types, local_fragment=svg)
                if target is not None:
                    result[key] = target
            elif short_key in allowed or short_key.startswith("aria-") or (
                tag == "link" and short_key in {"rel", "media", "disabled"}
            ):
                result[key] = self._css(value, name, prefix) if svg and "url(" in value.lower() else value
        return result

    def _html(self, data, name, prefix, css):
        soup = BeautifulSoup(decode(data), "html.parser")
        for item in soup.find_all(string=lambda text: isinstance(text, (Comment, Doctype, ProcessingInstruction))):
            item.extract()
        for tag in soup.find_all(True):
            if not tag.name:
                continue
            svg = tag.name == "svg" or tag.find_parent("svg") is not None
            if tag.name in DROP_TAGS or (
                tag.name == "link" and "stylesheet" not in tag.get("rel", [])
            ):
                tag.decompose()
            elif tag.name not in (SVG_TAGS if svg else HTML_TAGS):
                tag.decompose() if svg else tag.unwrap()
            else:
                tag.attrs = self._attrs(
                    tag.name,
                    {key: " ".join(value) if isinstance(value, list) else value for key, value in tag.attrs.items()},
                    name,
                    prefix,
                    svg,
                )
                if tag.name == "style":
                    tag.string = self._css(tag.get_text(), name, prefix)
        if css:
            style = soup.new_tag("style")
            style.string = css
            (soup.head or soup).append(style)
        return ("<!doctype html>\n" + str(soup)).encode("utf-8")

    def _svg(self, data, name, prefix):
        root = _xml(data, forbid_dtd=False)
        if root.tag != "{http://www.w3.org/2000/svg}svg":
            raise ValueError("Invalid SVG publication resource")
        stack = [root]
        while stack:
            element = stack.pop()
            tag = element.tag.rsplit("}", 1)[-1].lower()
            attrs = self._attrs(tag, element.attrib, name, prefix, svg=True)
            element.attrib.clear()
            element.attrib.update(attrs)
            if tag == "style" and element.text:
                element.text = self._css(element.text, name, prefix)
            for child in list(element):
                if child.tag.startswith("{http://www.w3.org/2000/svg}") and child.tag.rsplit("}", 1)[-1].lower() in SVG_TAGS:
                    stack.append(child)
                else:
                    element.remove(child)
        return SafeET.tostring(root, encoding="utf-8")

    def resource(self, name: str, *, prefix: str, css: str | None = None) -> tuple[str, bytes]:
        """Read a manifest resource. The caller must enforce a scoped response CSP."""
        media_type = self._resources.get(name)
        if media_type not in RENDER_TYPES:
            raise KeyError(name)
        with self._archive() as archive:
            data = _read(archive, name)
        if media_type in HTML_TYPES:
            return "text/html; charset=utf-8", self._html(data, name, prefix, css)
        if media_type == "text/css":
            return "text/css; charset=utf-8", self._css(decode(data), name, prefix).encode("utf-8")
        if media_type == "image/svg+xml":
            return media_type, self._svg(data, name, prefix)
        return FONT_TYPES.get(media_type, media_type), data

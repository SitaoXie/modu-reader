"""Bounded local TXT, Markdown, EPUB and PDF extraction. No URLs are fetched."""

from __future__ import annotations
import json
import re
from pathlib import Path
from posixpath import dirname, join, normpath
from urllib.parse import unquote, urlsplit
import zipfile
from bs4 import BeautifulSoup
from defusedxml import ElementTree as SafeET
from markdown_it import MarkdownIt
from .model import Block, Document, CHAPTER, clean
from .safety import (
    MAX_SOURCE_BYTES,
    MAX_ARCHIVE_BYTES,
    MAX_MEMBER_BYTES,
    MAX_ARCHIVE_MEMBERS,
    MAX_DOCUMENT_CHARS,
    MAX_BLOCKS,
    MAX_CACHE_BYTES,
    MAX_PDF_PAGES,
    read_bounded,
)

SUPPORTED = {".txt", ".epub", ".pdf", ".md", ".markdown"}
CACHE_VERSION = 3


def text_blocks(text: str, kind: str = "body") -> list[Block]:
    result = []
    for raw in clean(text).splitlines():
        line = raw.strip() if kind != "code" else raw.rstrip()
        if not line:
            continue
        style = "heading" if len(line) <= 90 and CHAPTER.match(line) else kind
        # Bound single-paragraph wrapping cost, including files with no newline.
        for start in range(0, len(line), 2048):
            result.append(Block(line[start : start + 2048], style))
    return result


def plain_blocks(text: str, title: str) -> tuple[list[Block], str]:
    """Recognize numbered headings and whitespace-delimited, unnumbered TXT titles."""
    lines = clean(text).splitlines()
    nonempty = [i for i, x in enumerate(lines) if x.strip()]
    author_index = -1
    author = ""
    if len(nonempty) > 2 and lines[nonempty[0]].strip() == title:
        candidate = lines[nonempty[1]].strip()
        if len(candidate) <= 12 and not re.search(r"[，。！？；“”]", candidate):
            author_index = nonempty[1]
            author = re.sub(r"^作者[：:]?\s*", "", candidate)
    result = []
    for index, raw in enumerate(lines):
        text = raw.strip()
        if not text:
            continue
        surrounded = (
            index > 0
            and index + 1 < len(lines)
            and not lines[index - 1].strip()
            and not lines[index + 1].strip()
        )
        short_title = len(text) <= 24 and not re.search(r"[，。！？；：、“”‘’「」…,.!?<>]", text)
        isolated = surrounded or (
            not raw[:1].isspace()
            and len(text) <= 12
            and index > 1
            and index + 1 < len(lines)
            and len(lines[index - 1].strip()) > 24
            and len(lines[index + 1].strip()) > 24
        )
        heading = len(text) <= 90 and bool(CHAPTER.match(text))
        heading = heading or (
            short_title and isolated and not any(x in text for x in ("上一页", "下一页", "目录页"))
        )
        if index == author_index:
            heading = False
        if index == 0 and text == title:
            heading = True
        for start in range(0, len(text), 2048):
            result.append(Block(text[start : start + 2048], "heading" if heading else "body"))
    return result, author


def decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    from charset_normalizer import from_bytes

    best = from_bytes(data).best()
    if best is None:
        raise ValueError("无法识别文字编码；请先将文件另存为 UTF-8。")
    return str(best)


def html_blocks(html: str) -> list[Block]:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "nav", "head"]):
        element.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for img in soup.find_all("img"):
        img.replace_with(f"〔图片：{img.get('alt') or '插图'}〕")
    blocks = []
    tags = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "tr"])
    for tag in tags:
        if tag.find_parent(["pre", "li", "tr"]):
            continue
        kind = "heading" if tag.name.startswith("h") else "code" if tag.name == "pre" else "body"
        text = tag.get_text(" | ", strip=True) if tag.name == "tr" else tag.get_text()
        if tag.name == "li":
            text = "• " + text
        if kind == "heading":
            text = " ".join(text.split())
        blocks.extend(text_blocks(text, kind))
    if not blocks:
        blocks = text_blocks(soup.get_text("\n"))
    return blocks


def member_name(base: str, href: str) -> str:
    decoded = unquote(href)
    target = urlsplit(decoded)
    if target.scheme or target.netloc or "\\" in decoded or "\x00" in decoded:
        raise ValueError("EPUB 包含非本地或无效的资源路径。")
    result = normpath(join(base, target.path))
    if result.startswith(("/", "../")) or result in {"..", "."}:
        raise ValueError("EPUB 资源路径超出书籍范围。")
    return result


def parse_epub(path: Path) -> tuple[str, str, list[Block]]:
    blocks = []
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_MEMBERS or sum(x.file_size for x in infos) > MAX_ARCHIVE_BYTES:
            raise ValueError("EPUB 内容过大，请拆分后导入。")
        names = [x.filename for x in infos]
        if len(names) != len(set(names)):
            raise ValueError("EPUB 包含重复资源名称。")
        for item in infos:
            member_name("", item.filename.rstrip("/"))
            if item.file_size > MAX_MEMBER_BYTES or item.flag_bits & 1:
                raise ValueError("EPUB 含过大或加密的资源。")
        budget = MAX_ARCHIVE_BYTES

        def read(name):
            nonlocal budget
            info = archive.getinfo(name)
            with archive.open(info) as source:
                data = source.read(min(MAX_MEMBER_BYTES, budget) + 1)
            budget -= len(data)
            if len(data) > MAX_MEMBER_BYTES or budget < 0:
                raise ValueError("EPUB 内容超过解析限额。")
            return data

        container = SafeET.fromstring(read("META-INF/container.xml"), forbid_dtd=True)
        root = container.find(".//{*}rootfile")
        if root is None:
            raise ValueError("EPUB 缺少内容索引。")
        opf_name = member_name("", root.attrib["full-path"])
        opf = SafeET.fromstring(read(opf_name), forbid_dtd=True)
        title, author = opf.find(".//{*}title"), opf.find(".//{*}creator")
        items = {x.attrib["id"]: x.attrib for x in opf.findall(".//{*}manifest/{*}item")}
        chars = 0
        for number, ref in enumerate(opf.findall(".//{*}spine/{*}itemref"), 1):
            if ref.get("linear") == "no":
                continue
            name = member_name(dirname(opf_name), items[ref.attrib["idref"]]["href"])
            part = html_blocks(read(name).decode("utf-8-sig"))
            if part and not any(x.kind == "heading" for x in part):
                part.insert(0, Block(f"第 {number} 节", "heading"))
            blocks.extend(part)
            chars += sum(len(b.text) for b in part)
            if len(blocks) > MAX_BLOCKS or chars > MAX_DOCUMENT_CHARS:
                raise ValueError("EPUB 正文超过解析限额。")
        return (
            (title.text or "") if title is not None else "",
            (author.text or "") if author is not None else "",
            blocks,
        )


def parse_pdf(path: Path) -> tuple[list[Block], list[str]]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    blocks, warnings = [], []
    with path.open("rb") as stream:
        reader = PdfReader(stream, strict=True)
        if reader.is_encrypted:
            raise ValueError("PDF 已加密，请先导出可阅读的本地副本。")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError("PDF 页数超过 2000 页，请拆分后导入。")
        toc = {}

        def visit(items, depth=0):
            if depth > 16:
                return
            for item in items[:MAX_PDF_PAGES]:
                if isinstance(item, list):
                    visit(item, depth + 1)
                else:
                    try:
                        page = reader.get_destination_page_number(item)
                        if page is not None:
                            toc.setdefault(page, []).append(clean(str(item.title))[:200])
                    except (ValueError, TypeError, PdfReadError):
                        continue

        visit(reader.outline)
        empty, chars = 0, 0
        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            chars += len(text)
            if chars > MAX_DOCUMENT_CHARS:
                raise ValueError("PDF 文字超过解析限额。")
            if not text.strip():
                empty += 1
                continue
            label = " · ".join(toc.get(index, []))
            blocks.append(Block(f"第 {index + 1} 页" + (f" · {label}" if label else ""), "heading"))
            blocks.extend(text_blocks(text))
            if len(blocks) > MAX_BLOCKS:
                raise ValueError("PDF 段落超过解析限额。")
        if empty:
            warnings.append(f"{empty} 页没有可提取文字；扫描页需要先进行 OCR。")
    warnings.append("PDF 使用文字重排模式；多栏与复杂表格的顺序取决于原文。")
    return blocks, warnings


def parse_file(path: Path, title: str | None = None) -> Document:
    if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("文件不存在或超过 64 MB。")
    ext = path.suffix.lower()
    title, author, warnings = title or path.stem, "", []
    if ext in {".txt", ".md", ".markdown"}:
        content = decode(read_bounded(path, MAX_SOURCE_BYTES))
        if len(content) > MAX_DOCUMENT_CHARS:
            raise ValueError("正文超过 800 万字符，请拆分后导入。")
        if ext == ".txt":
            blocks, author = plain_blocks(content, title)
        else:
            blocks = html_blocks(
                MarkdownIt("commonmark", {"html": False}).enable("table").render(content)
            )
    elif ext == ".epub":
        metadata_title, author, blocks = parse_epub(path)
        title = metadata_title or title
        warnings.append("EPUB 以文字阅读模式呈现；图片显示说明文字。")
    elif ext == ".pdf":
        blocks, warnings = parse_pdf(path)
    else:
        raise ValueError("支持 TXT、EPUB、PDF 和 Markdown 文件。")
    if not blocks:
        raise ValueError("没有可阅读文字。扫描版 PDF 需要先进行 OCR。")
    if len(blocks) > MAX_BLOCKS or sum(len(b.text) for b in blocks) > MAX_DOCUMENT_CHARS:
        raise ValueError("正文超过解析限额。")
    return Document(clean(title)[:300], clean(author)[:200], blocks, warnings)


def document_bytes(doc: Document) -> bytes:
    data = {
        "version": CACHE_VERSION,
        "title": doc.title,
        "author": doc.author,
        "blocks": [[b.text, b.kind] for b in doc.blocks],
        "warnings": doc.warnings,
    }
    encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_CACHE_BYTES:
        raise ValueError("解析结果超过缓存限额。")
    return encoded


def document_from_bytes(encoded: bytes) -> Document:
    data = json.loads(encoded)
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
        raise ValueError("缓存格式需要更新。")
    rows = data.get("blocks")
    if not isinstance(rows, list) or not rows or len(rows) > MAX_BLOCKS:
        raise ValueError("缓存段落无效。")
    blocks, chars = [], 0
    for item in rows:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], str)
            or item[1] not in {"body", "heading", "code"}
        ):
            raise ValueError("缓存内容无效。")
        text = clean(item[0])
        chars += len(text)
        if len(text) > 2048 or chars > MAX_DOCUMENT_CHARS:
            raise ValueError("缓存内容过大。")
        blocks.append(Block(text, item[1]))
    title, author, warnings = data.get("title"), data.get("author"), data.get("warnings", [])
    if (
        not isinstance(title, str)
        or not isinstance(author, str)
        or not isinstance(warnings, list)
        or not all(isinstance(w, str) for w in warnings)
        or len(warnings) > 100
    ):
        raise ValueError("缓存元数据无效。")
    return Document(
        clean(title)[:300], clean(author)[:200], blocks, [clean(w)[:500] for w in warnings]
    )

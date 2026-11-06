"""Lossless source anchors and bounded, lazy paragraph layout."""

from __future__ import annotations
from bisect import bisect_right
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
import re
from threading import Event
import unicodedata
import regex
from rich.cells import cell_len

OPEN = set("（([{《〈「『【〔〖‘“")
CLOSE = set("，。、；：！？）》〉」』】〕〗’”％‰…,.!?;:%)]}")
CHAPTER = re.compile(
    r"^(第[零〇一二三四五六七八九十百千万两\d]+[章回卷部节篇集]|序章|序言|楔子|前言|引言|尾声|后记|终章|附录|Chapter\s+\d+)",
    re.I,
)


def clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    # Terminal escape / control sequences must never enter the renderer.
    return "".join(
        c
        for c in text
        if c in "\n\t"
        or unicodedata.category(c) not in {"Cc", "Cs"}
        and c not in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
    ).replace("\t", "    ")


@dataclass
class Block:
    text: str
    kind: str = "body"
    start: int = 0


@dataclass
class Document:
    title: str
    author: str
    blocks: list[Block]
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self):
        offset = 0
        for b in self.blocks:
            b.start = offset
            offset += len(b.text) + 2
        self.starts = [b.start for b in self.blocks]
        self.text = "\n\n".join(b.text for b in self.blocks)
        self.chapters = [(i, b.text) for i, b in enumerate(self.blocks) if b.kind == "heading"]
        if not self.chapters and self.blocks:
            self.chapters = [(0, "正文")]

    def locate(self, offset: int) -> tuple[int, int]:
        i = max(0, min(len(self.blocks) - 1, bisect_right(self.starts, offset) - 1))
        return i, max(0, min(len(self.blocks[i].text), offset - self.starts[i]))

    def search(self, query: str, limit: int = 200) -> tuple[list[tuple[int, str]], bool]:
        if not query.strip():
            return [], False
        out = []
        for m in re.finditer(re.escape(query), self.text, re.I):
            if len(out) == limit:
                return out, True
            snippet = self.text[max(0, m.start() - 20) : m.end() + 50].replace("\n", " ")
            out.append((m.start(), snippet))
        return out, False


@dataclass(frozen=True)
class Line:
    start: int
    end: int
    text: str


@lru_cache(maxsize=4096)
def char_width(char: str) -> int:
    return cell_len(char)


def wrap(text: str, width: int) -> tuple[Line, ...]:
    """Wrap without losing a codepoint; keep CJK closing/opening punctuation together."""
    width = max(4, width)
    units = [(m.start(), m.end(), m.group()) for m in regex.finditer(r"\X", text)]
    lines = []
    a, n = 0, len(units)
    while a < n:
        b, used = a, 0
        while b < n and used + char_width(units[b][2]) <= width:
            used += char_width(units[b][2])
            b += 1
        b = max(a + 1, b)
        if b < n:
            # Backtrack to a legal boundary. Leave whole pairs / punctuation runs together.
            legal = b
            while legal > a + 1 and (
                units[legal][2][0] in CLOSE or units[legal - 1][2][-1] in OPEN
            ):
                legal -= 1
            b = legal
            # Avoid breaking a normal Latin word, while still supporting long URLs.
            if (
                units[b - 1][2].isascii()
                and units[b - 1][2].isalnum()
                and units[b][2].isascii()
                and units[b][2].isalnum()
            ):
                word = b
                while word > a and units[word - 1][2].isascii() and units[word - 1][2].isalnum():
                    word -= 1
                if word > a and word - a >= (b - a) // 2:
                    b = word
        start, end = units[a][0], units[b - 1][1]
        lines.append(Line(start, end, text[start:end]))
        a = b
    return tuple(lines) or (Line(0, 0, ""),)


class Layout:
    """Only wraps visited paragraphs. LRU bounded independently of book length."""

    def __init__(self, doc: Document, width: int = 80, spacing: int = 1):
        self.doc, self.width, self.spacing = doc, width, spacing
        self.cache: OrderedDict[tuple[int, int], tuple[Line, ...]] = OrderedDict()

    def lines(self, block: int) -> tuple[Line, ...]:
        key = (block, self.width)
        if key not in self.cache:
            self.cache[key] = wrap(self.doc.blocks[block].text, self.width)
            if len(self.cache) > 512:
                self.cache.popitem(last=False)
        self.cache.move_to_end(key)
        return self.cache[key]

    def at(self, anchor: int) -> tuple[int, int]:
        b, offset = self.doc.locate(anchor)
        lines = self.lines(b)
        if offset >= len(self.doc.blocks[b].text) and b + 1 < len(self.doc.blocks):
            return (b, len(lines)) if self.spacing else (b + 1, 0)
        r = max(0, bisect_right([x.start for x in lines], offset) - 1)
        return b, r

    def anchor(self, pos: tuple[int, int]) -> int:
        b, r = pos
        ls = self.lines(b)
        return self.doc.blocks[b].start + (
            ls[r].start if r < len(ls) else len(self.doc.blocks[b].text)
        )

    def step(self, pos: tuple[int, int], delta: int) -> tuple[int, int]:
        b, r = pos
        for _ in range(abs(delta)):
            if delta > 0:
                if r + 1 < len(self.lines(b)) + self.spacing:
                    r += 1
                elif b + 1 < len(self.doc.blocks):
                    b, r = b + 1, 0
                else:
                    break
            else:
                if r > 0:
                    r -= 1
                elif b > 0:
                    b -= 1
                    r = len(self.lines(b)) + self.spacing - 1
                else:
                    break
        return b, r

    def rows(self, pos: tuple[int, int], height: int):
        rows = []
        b, r = pos
        for _ in range(height):
            ls = self.lines(b)
            if r < len(ls):
                line = ls[r]
                block = self.doc.blocks[b]
                rows.append(
                    (block.start + line.start, block.start + line.end, line.text, block.kind)
                )
            else:
                rows.append(
                    (self.doc.blocks[b].start + len(self.doc.blocks[b].text),) * 2 + ("", "gap")
                )
            nxt = self.step((b, r), 1)
            if nxt == (b, r):
                break
            b, r = nxt
        return rows


@dataclass(frozen=True)
class PageIndex:
    """Small row-prefix index, independent of the viewport's bounded wrap cache."""

    starts: tuple[int, ...]
    total_rows: int

    @classmethod
    def build(cls, document: Document, width: int, spacing: int, cancelled: Event):
        starts = []
        total = 0
        for block in document.blocks:
            if cancelled.is_set():
                return None
            starts.append(total)
            total += len(wrap(block.text, width)) + spacing
        if cancelled.is_set():
            return None
        return cls(tuple(starts), max(1, total - spacing))

    def pages(self, position: tuple[int, int], height: int) -> tuple[int, int]:
        height = max(1, height)
        total = (self.total_rows + height - 1) // height
        block, row = position
        current = (self.starts[block] + row) // height + 1
        return min(current, total), total

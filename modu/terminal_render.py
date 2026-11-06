"""Keep painted cell runs anchored when terminal/font width policies differ.

Textual 6.12 concatenates strips on full updates. A preceding Unicode run may
advance a terminal's cursor differently from Rich's width calculation. Merely
making the rail a separate widget does not isolate its background color.

This adapter is local to MODU: no global Textual/Rich monkey patches. Layout,
source anchors and hit testing still belong to Textual. Both full and partial
updates place every styled run explicitly, including padding and scrollbars.
"""

from __future__ import annotations

from functools import lru_cache
import unicodedata

from rich.control import Control
from rich.segment import Segment
from textual._compositor import ChopsUpdate, CompositorUpdate, LayoutUpdate
from textual.strip import Strip


# Some DOM terminals measure repeated CJK punctuation with contextual spacing
# compression, then draw isolated punctuation at full width. A zero-cell WORD
# JOINER makes measurement and drawing agree. It is emitted only to the terminal;
# book text, wrapping, search offsets and saved positions remain untouched.
# Upstream reproducer: https://github.com/xtermjs/xterm.js/issues/6058
PUNCTUATION_GUARD = "\u2060"


@lru_cache(maxsize=1024)
def guarded_text(text: str) -> str:
    return "".join(
        char + PUNCTUATION_GUARD
        if not char.isascii() and unicodedata.category(char).startswith("P")
        else char
        for char in text
    )


def anchored_strip(strip: Strip, x: int, y: int, console) -> str:
    output = []
    for segment in strip:
        if segment.control:
            output.append(segment.text)
            continue
        width = segment.cell_length
        if not segment.text:
            continue
        position = Control.move_to(x, y).segment.text
        output.append(position)
        if width and not segment.text.isascii():
            # Clear the run's allocated cells, so narrower fallback glyphs cannot
            # leave letters or track pixels from an earlier frame in the gap.
            output.append(Strip([Segment(" " * width, segment.style)], width).render(console))
            output.append(position)
        rendered = Segment(guarded_text(segment.text), segment.style)
        output.append(Strip([rendered], width).render(console))
        x += width
    return "".join(output)


class AnchoredUpdate(CompositorUpdate):
    """Serialize the existing compositor's strips at their declared cell coordinates."""

    def __init__(self, update: LayoutUpdate | ChopsUpdate):
        self.update = update

    def render_segments(self, console) -> str:
        update = self.update
        output = []
        if isinstance(update, LayoutUpdate):
            for y, line in enumerate(update.strips, update.region.y):
                x = update.region.x
                for strip in line:
                    output.append(anchored_strip(strip, x, y, console))
                    x += strip.cell_length
        else:
            # Retain Textual's conservative left boundary: repainting the full
            # chop avoids cutting a wide glyph in half at a dirty-span boundary.
            for y, x1, x2 in update.spans:
                for end, (x, strip) in zip(update.chop_ends[y], update.chops[y].items()):
                    if strip is None or x >= x2 or end <= x1:
                        continue
                    if end > x2:
                        strip = strip.crop(0, x2 - x)
                    output.append(anchored_strip(strip, x, y, console))
        return "".join(output)


def anchor_update(renderable):
    if isinstance(renderable, (LayoutUpdate, ChopsUpdate)):
        return AnchoredUpdate(renderable)
    return renderable

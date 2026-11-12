from __future__ import annotations
import time
from collections import deque, OrderedDict
from bisect import bisect_right
import regex
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from rich.cells import cell_len
from textual import events
from textual.binding import Binding
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget
from .model import Document, Layout

from .themes import PALETTES


class Reader(Widget, can_focus=True):
    """Viewport renderer with stable source anchor and in-place disappearing scrollbar."""

    BINDINGS = [
        Binding("space,pagedown,right", "page(1)", "下一页", show=False),
        Binding("backspace,pageup,left", "page(-1)", "上一页", show=False),
        Binding("down,j", "line(1)", "下移", show=False),
        Binding("up,k", "line(-1)", "上移", show=False),
        Binding("home", "edge(False)", "开头", show=False),
        Binding("end", "edge(True)", "结尾", show=False),
    ]

    class PositionChanged(Message):
        pass

    class SelectionFinished(Message):
        def __init__(self, text, entry=None):
            super().__init__()
            self.text, self.entry = text, entry

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.doc: Document | None = None
        self.layout_engine: Layout | None = None
        self.anchor = 0
        self.pos = (0, 0)
        self.rows = []
        self.read_width = 80
        self.paragraph_spacing = 1
        self.chapter_breaks = True
        self.page_index = None
        self.palette = "modu-gold"
        self.highlight = ""
        self.scrollbar_visible = False
        self.last_activity = 0.0
        self.dragging = False
        self.rail = None
        self.page_history = deque(maxlen=512)
        self.page_geometry = None
        self.selection_start = self.selection_end = None
        self.selecting = False
        self.saved_words = {}
        self.word_cache = OrderedDict()

    def on_mount(self):
        self.set_interval(0.1, self.hide_scrollbar)

    @property
    def body_width(self):
        return max(4, min(self.read_width, self.size.width - 8))

    @property
    def body_height(self):
        return max(1, self.size.height - 2)

    @property
    def left_margin(self):
        return max(1, (self.size.width - self.body_width) // 2)

    def load(self, document, anchor=0):
        self.page_history.clear()
        self.doc = document
        self.clear_selection()
        self.word_cache.clear()
        self.layout_engine = Layout(
            document, self.body_width, self.paragraph_spacing, self.chapter_breaks
        )
        self.page_index = None
        self.anchor = max(0, min(anchor, len(document.text)))
        self.reflow()
        self.focus()

    def reflow(self):
        if self.layout_engine is None:
            return
        self.clear_selection()
        geometry = (self.body_width, self.body_height, self.paragraph_spacing, self.chapter_breaks)
        if geometry != self.page_geometry:
            self.page_history.clear()
            self.page_index = None
            self.page_geometry = geometry
        self.layout_engine.width = self.body_width
        self.layout_engine.spacing = self.paragraph_spacing
        self.layout_engine.chapter_breaks = self.chapter_breaks
        self.pos = self.layout_engine.at(self.anchor)
        self.rebuild()

    def on_resize(self, event: events.Resize):
        # Do not convert the anchor back from the new first row: repeated resizes
        # must never accumulate backward drift.
        self.reflow()

    def rebuild(self):
        if self.layout_engine:
            self.rows = self.layout_engine.rows(self.pos, self.body_height)
            if self.rows:
                start, end, text, kind = self.rows[0]
                if start < self.anchor < end:
                    offset = self.anchor - start
                    # Keep the exact source boundary across reflow. Arbitrary
                    # scrollbar targets snap to the beginning of a grapheme.
                    offset = next(
                        m.start() for m in regex.finditer(r"\X", text) if m.end() > offset
                    )
                    self.anchor = start + offset
                    self.rows[0] = (self.anchor, end, text[offset:], kind)
            self.refresh()
            if self.rail:
                self.rail.refresh()
            self.post_message(self.PositionChanged())

    def show_scrollbar(self):
        self.last_activity = time.monotonic()
        if not self.scrollbar_visible:
            self.scrollbar_visible = True
            if self.rail:
                self.rail.refresh()

    def hide_scrollbar(self):
        if (
            self.scrollbar_visible
            and not self.dragging
            and time.monotonic() - self.last_activity >= 2
        ):
            self.scrollbar_visible = False
            if self.rail:
                self.rail.refresh()

    def move(self, delta, *, page=False):
        if not self.layout_engine:
            return
        if not page:
            self.page_history.clear()
        target = self.layout_engine.step(self.pos, delta)
        if self.chapter_breaks and not page:
            # Wheel / line movement must visit a chapter boundary before moving
            # past it, even if the preceding viewport contains only one line.
            chapters = self.layout_engine.chapter_blocks
            chapter = bisect_right(chapters, self.pos[0]) - 1
            if delta > 0 and chapter + 1 < len(chapters):
                target = min(target, (chapters[chapter + 1], 0))
            elif delta < 0:
                if self.pos == (chapters[chapter], 0):
                    chapter = max(0, chapter - 1)
                target = max(target, (chapters[chapter], 0))
        self.set_position(target)

    def set_position(self, position):
        self.clear_selection()
        self.pos = position
        # Avoid a blank-only top row when paging to the last paragraph gap.
        b, r = self.pos
        if b == len(self.doc.blocks) - 1 and r >= len(self.layout_engine.lines(b)):
            self.pos = (b, len(self.layout_engine.lines(b)) - 1)
        self.anchor = self.layout_engine.anchor(self.pos)
        self.show_scrollbar()
        self.rebuild()

    def action_page(self, direction):
        if not self.layout_engine:
            return
        height = self.body_height
        if direction < 0 and self.page_history:
            self.anchor = self.page_history.pop()
            self.reflow()
            self.show_scrollbar()
            return
        if direction < 0 and self.chapter_breaks:
            chapters = self.layout_engine.chapter_blocks
            chapter = bisect_right(chapters, self.pos[0]) - 1
            target = self.layout_engine.step(self.pos, -height)
            if self.pos == (chapters[chapter], 0) and chapter > 0:
                if self.page_index is not None:
                    start = self.page_index.starts[chapters[chapter - 1]]
                    end = self.page_index.starts[chapters[chapter]]
                    target = self.page_index.position_at_row(
                        start + ((end - start - 1) // height) * height
                    )
                else:
                    target = max(target, (chapters[chapter - 1], 0))
            else:
                target = max(target, (chapters[chapter], 0))
            self.set_position(target)
            return
        if direction > 0:
            height = len(self.rows)
            following = self.layout_engine.step(self.pos, height)
            last_visible = self.layout_engine.step(self.pos, height - 1)
            block, row = following
            # No new page if the next row was already displayed or only the
            # trailing paragraph gap remains. Keep the last page in place.
            if following == last_visible or (
                block == len(self.doc.blocks) - 1 and row >= len(self.layout_engine.lines(block))
            ):
                return
            self.page_history.append(self.anchor)
        # Advance by the entire viewport: adjacent pages share no source text.
        # This uses the current post-resize geometry, not a cached page height.
        self.move(direction * height, page=True)

    def action_line(self, direction):
        self.move(direction)

    def action_edge(self, end):
        self.jump(len(self.doc.text) if end else 0)

    def jump(self, anchor):
        if not self.doc:
            return
        self.page_history.clear()
        self.anchor = max(0, min(int(anchor), len(self.doc.text)))
        self.reflow()
        self.show_scrollbar()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown):
        self.move(3)
        event.stop()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp):
        self.move(-3)
        event.stop()

    def on_mouse_move(self, event: events.MouseMove):
        if self.selecting:
            self.selection_end = self.offset_at(event.x, event.y)
            self.refresh()
            event.stop()
        if event.x >= self.size.width - 2:
            self.show_scrollbar()

    def drag_to(self, y):
        if self.doc:
            ratio = max(0, min(1, (y - 1) / max(1, self.size.height - 3)))
            self.jump(round(ratio * len(self.doc.text)))

    def clear_selection(self):
        if self.selecting:
            self.release_mouse()
        self.selecting = False
        self.selection_start = self.selection_end = None

    @property
    def selected_text(self):
        if self.doc and self.selection_start is not None and self.selection_end is not None:
            start, end = sorted((self.selection_start, self.selection_end))
            return self.doc.text[start:end].strip()
        return ""

    def offset_at(self, x, y):
        if not self.rows:
            return self.anchor
        row = max(0, min(len(self.rows) - 1, y - 1))
        start, end, content, _ = self.rows[row]
        cell = max(0, x - self.left_margin)
        column = 0
        for cluster in regex.finditer(r"\X", content):
            size = cell_len(cluster[0])
            if column + size > cell:
                return start + cluster.start()
            column += size
        return end

    def word_spans(self, block_index):
        if block_index in self.word_cache:
            self.word_cache.move_to_end(block_index)
            return self.word_cache[block_index]
        block = self.doc.blocks[block_index]
        spans = [(block.start + m.start(), block.start + m.end(), m[0].replace("’", "'").lower())
                 for m in regex.finditer(r"\p{L}[\p{L}\p{M}]*(?:['’-][\p{L}\p{M}]+)*", block.text)]
        self.word_cache[block_index] = spans
        if len(self.word_cache) > 512:
            self.word_cache.popitem(last=False)
        return spans

    def row_words(self, start, end):
        if not self.doc or not self.saved_words:
            return []
        block, _ = self.doc.locate(start)
        return [(a, b, self.saved_words[key]) for a, b, key in self.word_spans(block)
                if a < end and b > start and key in self.saved_words]

    def on_mouse_down(self, event: events.MouseDown):
        self.focus()
        if event.button != 1 or not self.rows:
            return
        self.selection_start = self.selection_end = self.offset_at(event.x, event.y)
        self.selecting = True
        self.capture_mouse()
        self.refresh()
        event.stop()

    def on_mouse_up(self, event: events.MouseUp):
        if not self.selecting:
            return
        self.selection_end = self.offset_at(event.x, event.y)
        self.selecting = False
        self.release_mouse()
        if self.selected_text:
            self.post_message(self.SelectionFinished(self.selected_text))
        else:
            offset = self.selection_end
            for start, end, entry in self.row_words(offset, offset + 1):
                if start <= offset < end:
                    self.post_message(self.SelectionFinished(entry["word"], entry))
                    break
        self.refresh()
        event.stop()

    def on_mouse_release(self):
        self.selecting = False

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        bg, fg, accent, muted, panel, _ = PALETTES[self.palette]
        base = Style(color=fg, bgcolor=bg)
        segments = []
        row = y - 1
        if 0 <= row < len(self.rows):
            start, end, content, kind = self.rows[row]
            margin = self.left_margin
            style = Style(
                color=accent if kind == "heading" else muted if kind == "code" else fg,
                bgcolor=bg,
                bold=kind == "heading",
            )
            text = Text(content, style=style, no_wrap=True, overflow="crop")
            for a, b, _entry in self.row_words(start, end):
                text.stylize(Style(color=accent, underline=True), max(0, a - start), min(len(content), b - start))
            if self.selection_start is not None and self.selection_end is not None:
                a, b = sorted((self.selection_start, self.selection_end))
                if a < end and b > start:
                    text.stylize(Style(color=bg, bgcolor=accent), max(0, a - start), min(len(content), b - start))
            if self.highlight:
                text.highlight_words(
                    [self.highlight], Style(color=bg, bgcolor=accent), case_sensitive=False
                )
            segments.append(Segment(" " * margin, base))
            segments.extend(
                Segment(seg.text, style + (seg.style or Style()))
                for seg in text.render(self.app.console, end="")
            )
            used = margin + cell_len(content)
            segments.append(Segment(" " * max(0, width - used), base))
        else:
            segments.append(Segment(" " * width, base))
        strip = Strip(segments).crop_extend(0, width, base)
        return strip


class ReaderRail(Widget):
    """A separate fixed-column widget; only ASCII spaces, no ambiguous box glyphs.

    Body text never contributes to its measured width or mouse coordinates.
    Hiding it repaints its cells, without resizing/reflowing the reader.
    """

    def __init__(self, reader: Reader, **kwargs):
        super().__init__(**kwargs)
        self.reader = reader
        reader.rail = self

    def on_resize(self):
        # A second, rail-only chop places the cursor at its absolute column even
        # on terminals whose CJK glyph fallback differs from Unicode cell widths.
        self.call_after_refresh(self.refresh)

    def on_mouse_move(self, event: events.MouseMove):
        self.reader.show_scrollbar()
        if self.reader.dragging:
            self.reader.drag_to(event.y)
        event.stop()

    def on_mouse_down(self, event: events.MouseDown):
        self.reader.focus()
        self.reader.dragging = True
        self.capture_mouse()
        self.reader.drag_to(event.y)
        event.stop()

    def on_mouse_up(self, event: events.MouseUp):
        self.reader.dragging = False
        self.release_mouse()
        self.reader.show_scrollbar()
        event.stop()

    def on_mouse_release(self, event: events.MouseRelease):
        self.reader.dragging = False

    def on_mouse_scroll_down(self, event: events.MouseScrollDown):
        self.reader.move(3)
        event.stop()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp):
        self.reader.move(-3)
        event.stop()

    def render_line(self, y: int) -> Strip:
        reader = self.reader
        bg, fg, accent, muted, panel, _ = PALETTES[reader.palette]
        color = bg
        if reader.scrollbar_visible and reader.doc and 1 <= y < self.size.height - 1:
            track = max(1, self.size.height - 2)
            visible = sum(end - start for start, end, _, _ in reader.rows)
            thumb = max(1, min(track, round(track * visible / max(1, len(reader.doc.text)))))
            top = 1 + round(reader.anchor / max(1, len(reader.doc.text)) * (track - thumb))
            color = accent if top <= y < top + thumb else panel
        # One colored cell plus an outer gutter, always exactly two cells wide.
        return Strip(
            [
                Segment(" ", Style(bgcolor=color)),
                Segment(" " * max(0, self.size.width - 1), Style(bgcolor=bg)),
            ],
            self.size.width,
        )

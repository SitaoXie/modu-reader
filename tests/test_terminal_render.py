"""Decode actual output with independent terminal width policies, including a failing control."""

import pytest
import pyte
from rich.cells import cell_len
from rich.console import Console
from rich.segment import Segment
from rich.style import Style
from textual._compositor import LayoutUpdate, ChopsUpdate
from textual.geometry import Region
from textual.strip import Strip
from modu.terminal_render import anchor_update
from tests.terminal_widths import WidthVariantScreen

BASE = Style(color="#ddd6c8", bgcolor="#121416")
TRACK = Style(bgcolor="#252a2d")
CONSOLE = Console(force_terminal=True, color_system="truecolor")


def strip(text, width):
    return Strip([Segment(text, BASE), Segment(" " * (width - cell_len(text)), BASE)], width)


def update(kind):
    left = strip("目录「夜航」", 16)
    body = strip("“灯亮了，出发吧。”", 34)
    rail = Strip([Segment(" ", TRACK), Segment(" ", BASE)], 2)
    if kind == "full":
        return LayoutUpdate([[left, body, rail]], Region(0, 1, 52, 1))
    return ChopsUpdate([{}, {0: left, 16: body, 50: rail}], [(1, 0, 52)], [[], [16, 50, 52]])


def paint(renderable, model):
    screen = WidthVariantScreen(60, 4, model)
    stream = pyte.Stream(screen)
    stream.feed("\x1b[?7l\x1b[2;1H" + "X" * 52)
    stream.feed(renderable.render_segments(CONSOLE))
    return screen


@pytest.mark.parametrize("model", ["standard", "narrow-punctuation", "wide-ambiguous"])
@pytest.mark.parametrize("kind", ["full", "partial"])
def test_rail_and_padding_use_fixed_cells(kind, model):
    screen = paint(anchor_update(update(kind)), model)
    assert screen.buffer[1][50].data == " " and screen.buffer[1][50].bg == "252a2d"
    assert all(screen.buffer[1][x].bg == "121416" for x in [47, 48, 49, 51])
    assert all(screen.buffer[1][x].data != "X" for x in range(52))


def test_original_full_update_exposes_width_drift():
    # Negative control: this same decoder rejects the previous serialization.
    screen = paint(update("full"), "narrow-punctuation")
    assert screen.buffer[1][50].bg != "252a2d"


def test_narrower_text_does_not_leave_old_cells():
    body = strip("，，，，", 12)
    fixed = anchor_update(LayoutUpdate([[body]], Region(0, 1, 12, 1)))
    screen = paint(fixed, "narrow-punctuation")
    assert all(screen.buffer[1][x].data == " " for x in range(4, 12))


def test_unrelated_renderables_are_unchanged():
    value = object()
    assert anchor_update(value) is value


def test_punctuation_guard_preserves_source_and_cell_width():
    from modu.terminal_render import guarded_text

    source = "中文，标点。‘引号’…… Latin, punctuation. e\u0301"
    guarded = guarded_text(source)
    assert guarded.replace("\u2060", "") == source
    assert cell_len(guarded) == cell_len(source)
    assert "，\u2060" in guarded and "。\u2060" in guarded
    assert "Latin, punctuation." in guarded
    assert "e\u0301" in guarded
    assert guarded_text.cache_info().maxsize == 1024


def test_decoder_keeps_text_after_zero_cell_format_character():
    screen = WidthVariantScreen(20, 2)
    pyte.Stream(screen).feed("前，\u2060后。\u2060end")
    assert screen.display[0].rstrip() == "前，后。end"

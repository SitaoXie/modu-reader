import pytest
from rich.color import Color
from textual.scrollbar import ScrollBarRender

from modu.scrollbars import SolidScrollBarRender
from modu.app import ModuApp
from modu.library import Library
from modu.reader import Reader
from textual.widgets import OptionList


@pytest.mark.parametrize("position", [0, 0.5, 2, 7.75, 19, 30, 100])
def test_solid_thumb_is_contiguous_ascii_cells_with_hit_targets(position):
    back, thumb = Color.parse("#121416"), Color.parse("#d4b477")
    render = SolidScrollBarRender.render_bar(
        size=29,
        virtual_size=40,
        window_size=29,
        position=position,
        back_color=back,
        bar_color=thumb,
    )
    segments = list(render.segments)
    assert len(segments) == 29
    assert all(s.text == " " and not s.style.reverse for s in segments)
    visible = [i for i, s in enumerate(segments) if s.style.bgcolor == thumb]
    assert visible == list(range(visible[0], visible[-1] + 1))
    assert all(segments[i].style.meta["@mouse.down"] == "grab" for i in visible)
    if position >= 11:
        assert visible[-1] == 28


def test_fractional_glyph_negative_control():
    original = ScrollBarRender.render_bar(size=29, virtual_size=36, window_size=29, position=2)
    assert any(not segment.text.isascii() for segment in original.segments)
    fixed = SolidScrollBarRender.render_bar(size=29, virtual_size=36, window_size=29, position=2)
    assert all(segment.text.isascii() for segment in fixed.segments)


@pytest.mark.asyncio
async def test_current_chapter_visible_after_resize_and_sidebar_toggle(tmp_path):
    path = tmp_path / "chapters.md"
    path.write_text(
        "\n\n".join(f"# Chapter {n} 山间灯火\n\nA quiet page." for n in range(1, 41)),
        encoding="utf-8",
    )
    lib = Library(tmp_path / "library")
    identifier, _ = lib.import_file(path)
    app = ModuApp(lib, start_book=identifier)
    async with app.run_test(size=(110, 42)) as pilot:
        await pilot.pause(0.3)
        await pilot.press("end")
        anchor = app.query_one(Reader).anchor
        for width, height in [(110, 28), (70, 22), (65, 24), (84, 36), (110, 42), (110, 28)]:
            await pilot.resize_terminal(width, height)
            await pilot.pause(0.1)
            assert app.query_one(Reader).anchor == anchor
            if width >= 70:
                toc = app.query_one("#toc-list", OptionList)
                assert "> 40" in "\n".join(line.text for line in toc.render_lines(toc.size.region))
        await pilot.press("c", "c")
        await pilot.pause(0.1)
        assert "> 40" in "\n".join(line.text for line in toc.render_lines(toc.size.region))

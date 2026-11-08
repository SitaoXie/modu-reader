"""Solid cell scrollbars without font-dependent fractional block glyphs."""

from rich.segment import Segment, Segments
from rich.style import Style
from textual.scrollbar import ScrollBarRender


class SolidScrollBarRender(ScrollBarRender):
    @classmethod
    def render_bar(
        cls,
        size=25,
        virtual_size=50,
        window_size=20,
        position=0,
        thickness=1,
        vertical=True,
        back_color=None,
        bar_color=None,
    ):
        size = max(0, int(size))
        scrollable = virtual_size > window_size > 0
        thumb = min(size, max(1, round(size * window_size / virtual_size))) if scrollable else 0
        fraction = min(1, max(0, position / (virtual_size - window_size))) if scrollable else 0
        start = round((size - thumb) * fraction)
        segments = []
        for index in range(size):
            on_thumb = scrollable and start <= index < start + thumb
            action = "grab" if on_thumb else "scroll_up" if index < start else "scroll_down"
            segments.append(
                Segment(
                    " " * (thickness if vertical else 1),
                    Style(
                        bgcolor=bar_color if on_thumb else back_color, meta={"@mouse.down": action}
                    ),
                )
            )
        if vertical:
            return Segments(segments, new_lines=True)
        return Segments((segments + [Segment.line()]) * thickness, new_lines=False)

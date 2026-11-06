"""Test-only diagnostic driver. Never installed as a MODU entry point.

Use only original/synthetic test books: the explicit diagnostic file contains
visible text. It is ignored by Git and excluded from release archives.
"""

import argparse
import json
import os
from pathlib import Path
import time
from modu import app as app_module
from modu.app import ModuApp
from modu.library import Library
from modu.reader import Reader


class DiagnosticApp(ModuApp):
    # Textual resolves relative CSS against the subclass module.
    CSS_PATH = Path(app_module.__file__).with_name("app.tcss")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Also run this external driver against stable versions with legacy tracing.
        if hasattr(self, "trace_file"):
            self.trace_file = None

    async def on_mount(self):
        await super().on_mount()
        self.set_interval(0.02, lambda: self.call_after_refresh(self.record))

    def record(self):
        if not self.doc:
            return
        reader = self.query_one(Reader)
        if reader.layout_engine.width != reader.body_width:
            return
        # App.size can update before the widget Resize event is processed.
        # Do not label the previous viewport as a frame of the new terminal size.
        if (
            max(reader.rail.region.right, reader.region.right) != self.size.width
            or reader.rail.region.bottom != self.size.height - 2
        ):
            return
        data = {
            "time": time.time(),
            "book_id": self.book_id,
            "anchor": reader.anchor,
            "position": reader.pos,
            "width": reader.body_width,
            "size": list(reader.size),
            "region": list(reader.region),
            "terminal_size": list(self.size),
            "rail_region": list(reader.rail.region),
            "sidebar_visible": self.query_one("#toc-sidebar").display,
            "chapter_index": self.current_chapter_index,
            "rows": reader.rows,
            "scrollbar": reader.scrollbar_visible,
            "theme": self.theme,
            "reading": self.reading,
            "modal": type(self.screen).__name__,
            "cache_entries": len(reader.layout_engine.cache),
        }
        target = Path(os.environ["MODU_TEST_TRACE"])
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temporary.replace(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("book", nargs="?", type=Path)
    args = parser.parse_args()
    os.environ.pop("NO_COLOR", None)
    os.environ["TEXTUAL_COLOR_SYSTEM"] = "truecolor"
    lib = Library(args.library)
    target = lib.import_file(args.book)[0] if args.book else None
    DiagnosticApp(lib, start_book=target).run()


if __name__ == "__main__":
    main()

"""Native cursor ownership must end when MODU yields or closes the terminal."""

from types import SimpleNamespace

import pyte

from modu.app import ModuApp
from modu.library import Library


def test_cursor_guard_releases_terminal_for_suspend_and_shutdown(tmp_path):
    app = ModuApp(Library(tmp_path / "library"))
    screen = pyte.Screen(20, 4)
    stream = pyte.Stream(screen)
    writes = []

    def write(data):
        writes.append(data)
        stream.feed(data)

    driver = SimpleNamespace(is_headless=False, write=write, flush=lambda: None)
    app._driver = driver
    app._running = True
    app._resume_terminal_cursor_guard(app)
    assert screen.cursor.hidden
    app._pause_terminal_cursor_guard(app)
    stream.feed("\x1b[?25h")  # An external application / shell owns the cursor.
    before = len(writes)
    app._hide_terminal_cursor()
    assert not screen.cursor.hidden and len(writes) == before
    app._resume_terminal_cursor_guard(app)
    assert screen.cursor.hidden
    for state in ("headless", "stopped", "closed"):
        driver.is_headless = state == "headless"
        app._running = state != "stopped"
        app._closed = state == "closed"
        stream.feed("\x1b[?25h")
        before = len(writes)
        app._hide_terminal_cursor()
        assert not screen.cursor.hidden and len(writes) == before
    app._driver = None

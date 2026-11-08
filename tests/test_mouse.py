from types import SimpleNamespace

import pytest
from textual import events

from modu.app import ModuApp
from modu.library import Library
from modu.reader import Reader, ReaderRail


@pytest.mark.parametrize("mouse,pixels", [(True, False), (True, True), (False, False)])
def test_mode_recovery_honors_driver_mouse_settings(tmp_path, mouse, pixels):
    writes = []
    app = ModuApp(Library(tmp_path / "library"))
    app._driver = SimpleNamespace(
        is_headless=False,
        _mouse=mouse,
        _mouse_pixels=pixels,
        write=writes.append,
        flush=lambda: None,
    )
    app._running = True
    app._terminal_guard_active = True
    app._restore_terminal_modes()
    sequence = "".join(writes)
    assert "\x1b[?25l" in sequence and "\x1b[?1004h" not in sequence
    assert ("\x1b[?1003h" in sequence) is mouse
    assert ("\x1b[?1016h" in sequence) is (mouse and pixels)
    assert ("\x1b[?1006h" in sequence) is (mouse and not pixels)
    assert "\x1b[?1000h" not in sequence  # Do not interrupt active drag listeners.
    app._driver = None


@pytest.mark.asyncio
async def test_focus_change_releases_interrupted_rail_drag(tmp_path):
    path = tmp_path / "mouse.md"
    path.write_text("# One\n\n" + "Reading by the window. " * 300, encoding="utf-8")
    lib = Library(tmp_path / "library")
    identifier, _ = lib.import_file(path)
    app = ModuApp(lib, start_book=identifier)
    async with app.run_test(size=(110, 36)) as pilot:
        await pilot.pause(0.3)
        reader = app.query_one(Reader)
        rail = app.query_one(ReaderRail)
        for transition in (events.AppBlur, events.AppFocus):
            reader.dragging = True
            rail.capture_mouse()
            app._mouse_down_widget = rail
            anchor = reader.anchor
            app.post_message(transition())
            await pilot.pause()
            assert app.mouse_captured is None and not reader.dragging
            assert app._mouse_down_widget is None
            assert reader.anchor == anchor
        await pilot.click("#settings")
        await pilot.pause()
        assert not app.unobstructed
        await pilot.press("escape")
        await pilot.click("#reader")
        assert reader.has_focus

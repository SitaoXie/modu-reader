"""Verify the copy promise, including cache rebuilds and narrow import dialogs."""

import pytest
from textual.widgets import Button, Input, Static

from modu.app import ModuApp
from modu.library import Library
from tests.test_cli import run_cli


@pytest.mark.parametrize("change", ["edit", "move", "delete"])
def test_import_is_independent_even_without_cache(tmp_path, change):
    source = tmp_path / "story.txt"
    source.write_text("第一章 窗边\n\nOriginal words. 雨声渐渐停了。", encoding="utf-8")
    original = source.read_bytes()
    library = Library(tmp_path / "library")
    identifier, _ = library.import_file(source)
    expected = library.load(identifier).text
    library.save_position(identifier, 12)
    library.toggle_bookmark(identifier, 12, "Window")
    copy = library.root / "originals" / f"{identifier}.txt"
    assert copy.read_bytes() == original and not copy.samefile(source)
    if change == "edit":
        source.write_text("Replacement text.", encoding="utf-8")
    elif change == "move":
        source.rename(tmp_path / "moved.txt")
    else:
        source.unlink()
    assert library.load(identifier).text == expected
    (library.root / "cache" / f"{identifier}.json.z").unlink()
    reopened = Library(library.root)
    assert reopened.load(identifier).text == expected
    assert copy.read_bytes() == original
    assert reopened.book(identifier)["position"] == 12
    assert reopened.bookmarks(identifier)[0]["position"] == 12


@pytest.mark.parametrize("language", ["zh", "en"])
def test_cli_import_explains_copy_and_actual_directory(tmp_path, language):
    source = tmp_path / "story.txt"
    source.write_text("An original story.", encoding="utf-8")
    result = run_cli(tmp_path, "--lang", language, "--import-only", str(source))
    assert result.returncode == 0, result.stderr
    assert str((tmp_path / "library" / "originals").resolve()) in result.stdout
    assert ("不会自动同步" if language == "zh" else "Changes are not synced") in result.stdout
    listing = run_cli(tmp_path, "--list")
    assert "originals" not in listing.stdout


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize("size", [(42, 24), (70, 30), (110, 36)])
async def test_import_notice_keeps_path_and_controls_accessible(tmp_path, language, size):
    library = Library(tmp_path / "中文 [books]" / ("long-directory-" * 6))
    library.set_setting("language", language)
    app = ModuApp(library, shelf=True)
    async with app.run_test(size=size) as pilot:
        await pilot.press("i")
        await pilot.pause()
        note = app.screen.query_one("#import-copy-note", Static)
        assert ("独立副本" if language == "zh" else "independent library copy") in note.render().plain
        path = app.screen.query_one("#import-copy-path", Static)
        assert str(library.root / "originals") in path.render().plain
        for selector in ("#path", "#import-go", "#cancel"):
            control = app.screen.query_one(selector)
            assert 0 <= control.region.y < control.region.bottom <= size[1]
            assert 0 <= control.region.x < control.region.right <= size[0]
        assert app.focused is app.screen.query_one(Input)
        info = app.screen.query_one("#import-info")
        info.scroll_end(animate=False)
        await pilot.pause()
        assert path.region.bottom <= info.content_region.bottom
        assert app.screen.query_one("#import-go", Button).region.y >= info.region.bottom
        await pilot.press("escape")
        assert app.unobstructed

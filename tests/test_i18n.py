"""Language changes must never change source text, paging, or durable positions."""

import ast
from pathlib import Path
from string import Formatter

import pytest
from rich.text import Text
from textual.widgets import Button, DataTable, Input, Label, OptionList, Static

from modu.app import ModuApp
from modu.i18n import ENGLISH, message, normalize_language
from modu.library import Library
from modu.reader import Reader
from tests.test_cli import run_cli


@pytest.fixture
def book_library(tmp_path):
    book = tmp_path / "River notes.txt"
    book.write_text(
        "Chapter 1 The river\n\n"
        + "\n\n".join(
            f"{i:04d} “灯光，映在水上。” A quiet river; one more page." for i in range(80)
        )
        + "\n\nChapter 2 The bridge\n\nThe lights were still on.",
        encoding="utf-8",
    )
    lib = Library(tmp_path / "library")
    identity, _ = lib.import_file(book)
    return lib, identity


def rendered(widget):
    value = widget.render()
    return value.plain if isinstance(value, Text) else str(value)


def test_catalog_placeholders_and_app_owned_labels():
    def fields(text):
        return {field for _, field, _, _ in Formatter().parse(text) if field}

    for original, translated in ENGLISH.items():
        assert fields(original) == fields(translated), original
    import modu.app

    tree = ast.parse(Path(modu.app.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "tr"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            assert node.args[0].value in ENGLISH, node.args[0].value
    assert normalize_language(["en"]) == "zh"
    assert normalize_language("unknown") == "zh"
    assert "OCR" in message("en", "3 页没有可提取文字；扫描页需要先进行 OCR。")
    assert "扫描" not in message("en", "3 页没有可提取文字；扫描页需要先进行 OCR。")
    assert message("en", "user {filename}.txt") == "user {filename}.txt"


async def test_live_switch_preserves_paging_and_translates_dialogs(book_library):
    lib, identity = book_library
    app = ModuApp(lib, start_book=identity)
    async with app.run_test(size=(110, 36)) as pilot:
        await pilot.pause(0.5)
        reader = app.query_one(Reader)
        await pilot.press("space", "space", "b")
        await pilot.pause(0.1)
        anchor, rows, text = reader.anchor, list(reader.rows), app.doc.text
        history = list(reader.page_history)
        theme = app.theme
        await pilot.press("l")
        await pilot.pause(0.2)
        assert app.language == "en" and lib.setting("language") == "en"
        assert (reader.anchor, reader.rows, app.doc.text) == (anchor, rows, text)
        assert list(reader.page_history) == history and app.theme == theme
        assert app.query_one("#toc-heading", Static).render().plain == "Contents"
        assert "Page " in rendered(app.query_one("#page-progress"))
        assert "chars" in rendered(app.query_one("#progress"))
        assert [c.label.plain for c in app.query_one(DataTable).columns.values()] == [
            "Title",
            "Author",
            "Format",
            "Progress",
        ]
        for key, expected in [
            ("question_mark", "MODU · A quiet place to read"),
            ("i", "Add books to your shelf"),
            ("s", "Reading settings"),
            ("m", "My bookmarks"),
        ]:
            await pilot.press(key)
            await pilot.pause(0.1)
            assert rendered(app.screen.query_one(Label)) == expected
            if key == "s":
                assert any("Ink night" in label for label, _ in app.screen.options)
            await pilot.press("escape")
        await pilot.press("slash")
        await pilot.pause(0.1)
        search = app.screen.query_one(Input)
        await pilot.press("l")  # Typing a search must not switch the interface.
        assert search.value == "l" and app.language == "en"
        search.value = "quiet river"
        await pilot.pause(0.5)
        assert "Results:" in rendered(app.screen.query_one("#search-info"))
        assert app.screen.query_one(OptionList).option_count > 0
        await pilot.press("escape")
        await pilot.press("space")
        await pilot.pause(0.1)
        previous_end = max(end for _, end, _, _ in rows)
        assert reader.rows[0][0] >= previous_end
        assert not any(text[previous_end : reader.rows[0][0]].strip())
        # Select Chinese through settings, then switch back with the mouse button.
        await pilot.press("s")
        await pilot.pause(0.1)
        modal = app.screen
        modal.query_one(OptionList).highlighted = next(
            i for i, (_, value) in enumerate(modal.options) if value == "language:zh"
        )
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert app.language == "zh"
        assert "页" in rendered(app.query_one("#page-progress"))
        await pilot.click("#language")
        await pilot.pause(0.2)
        assert app.language == "en"
        saved = reader.anchor
        await pilot.press("q")
    assert Library(lib.root).book(identity)["position"] == saved
    again = ModuApp(Library(lib.root))
    async with again.run_test(size=(110, 36)) as pilot:
        await pilot.pause(0.5)
        assert again.language == "en" and again.query_one(Reader).anchor == saved
        assert again.doc.text == text
        assert lib.bookmarks(identity)[0]["position"] == anchor


async def test_english_narrow_layout_and_shelf_selection(book_library):
    lib, identity = book_library
    lib.set_setting("language", "en")
    app = ModuApp(lib, start_book=identity)
    async with app.run_test(size=(84, 36)) as pilot:
        await pilot.pause(0.4)
        await pilot.press("space")
        reader = app.query_one(Reader)
        anchor = reader.anchor
        for width, height in [(42, 24), (60, 28), (110, 36), (70, 30), (84, 36)]:
            await pilot.resize_terminal(width, height)
            await pilot.pause(0.25)
            for identity in ("import", "language", "help"):
                button = app.query_one("#" + identity, Button)
                assert button.region.right <= width and button.region.x >= 0
            assert reader.rail.region.right == width
            assert reader.anchor == anchor
            counter = app.query_one("#page-progress")
            assert counter.region.width >= len(rendered(counter))
        await pilot.press("escape")
        await pilot.pause(0.1)
        table = app.query_one(DataTable)
        cursor = table.cursor_row
        await pilot.press("l")
        await pilot.pause(0.1)
        assert table.cursor_row == cursor
        assert [c.label.plain for c in table.columns.values()] == ["书名", "作者", "格式", "进度"]


def test_cli_language_help_errors_and_persistence(tmp_path):
    result = run_cli(tmp_path, "--lang", "en", "--help")
    assert result.returncode == 0 and "Offline terminal ebook reader" in result.stdout
    assert not (tmp_path / "library").exists()  # --help must not create storage.
    book = tmp_path / "example.txt"
    book.write_text("A quiet river, a little time to read.", encoding="utf-8")
    result = run_cli(tmp_path, "--lang", "en", "--import-only", str(book))
    assert result.returncode == 0 and "Imported:" in result.stdout
    assert Library(tmp_path / "library").setting("language") == "en"
    help_result = run_cli(tmp_path, "--help")
    assert "Offline terminal ebook reader" in help_result.stdout
    invalid = tmp_path / "unsupported.bin"
    invalid.write_text("test", encoding="utf-8")
    result = run_cli(tmp_path, "--import-only", str(invalid))
    assert result.returncode == 1 and "Import failed:" in result.stderr
    assert "Choose a local TXT" in result.stderr
    result = run_cli(tmp_path, "--lang", "zh", "--list")
    assert result.returncode == 0
    assert Library(tmp_path / "library").setting("language") == "zh"


async def test_language_switch_remeasures_every_toolbar_button(book_library):
    lib, identity = book_library
    app = ModuApp(lib, start_book=identity)
    async with app.run_test(size=(110, 36)) as pilot:
        await pilot.pause(0.4)
        reader = app.query_one(Reader)
        await pilot.press("space")
        anchor = reader.anchor
        for width in (110, 85, 84, 70, 69, 60, 59, 42, 110):
            await pilot.resize_terminal(width, 36)
            await pilot.pause(0.1)
            for _ in range(2):
                await pilot.press("l")
                await pilot.pause(0.1)
                for button in app.query(Button):
                    if not button.display:
                        continue
                    lines = [
                        line.text.strip()
                        for line in button.render_lines(button.size.region)
                        if line.text.strip()
                    ]
                    assert lines == [button.label.plain], (width, app.language, button.id, lines)
                    assert 0 <= button.region.x < button.region.right <= width
                assert reader.anchor == anchor

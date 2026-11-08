import sqlite3

import pytest
from textual.widgets import Button, DataTable

from modu.app import ConfirmBookModal, ModuApp
from modu.library import Library


def make_book(tmp_path):
    original = tmp_path / "original.md"
    original.write_text("# A quiet room\n\n" + "Read by the window. " * 60, encoding="utf-8")
    lib = Library(tmp_path / "library")
    identifier, _ = lib.import_file(original)
    lib.save_position(identifier, 31)
    lib.toggle_bookmark(identifier, 31, "Window")
    return lib, identifier, original


def test_archive_preserves_content_marks_position_and_restores(tmp_path):
    lib, identifier, _ = make_book(tmp_path)
    before = lib.load(identifier).text
    lib.archive_book(identifier)
    assert lib.books() == [] and lib.books(archived=True)[0]["id"] == identifier
    assert lib.setting("last_book") is None
    lib.save_position(identifier, 36)
    assert lib.setting("last_book") is None
    again = Library(lib.root)
    assert again.load(identifier).text == before
    assert again.bookmarks(identifier)[0]["position"] == 31
    again.archive_book(identifier, False)
    assert again.books()[0]["position"] == 36 and not again.books(archived=True)


def test_existing_library_migration_keeps_reading_state(tmp_path):
    lib, identifier, _ = make_book(tmp_path)
    with lib.connect() as c:
        c.execute("ALTER TABLE books DROP COLUMN archived")
    migrated = Library(lib.root)
    assert migrated.books()[0]["archived"] == 0
    assert migrated.book(identifier)["position"] == 31
    assert migrated.bookmarks(identifier)[0]["position"] == 31
    assert migrated.setting("last_book") == identifier


def test_delete_only_library_copy_and_no_dangling_resume(tmp_path):
    lib, identifier, original = make_book(tmp_path)
    original_bytes = original.read_bytes()
    outside = tmp_path / "keep.txt"
    outside.write_text("Do not delete")
    with lib.connect() as c:
        c.execute("UPDATE books SET source=? WHERE id=?", (str(outside), identifier))
    lib.delete_book(identifier)
    assert lib.book(identifier) is None and not lib.bookmarks(identifier)
    assert not list((lib.root / "originals").iterdir())
    assert not list((lib.root / "cache").iterdir())
    assert original.read_bytes() == original_bytes and outside.read_text() == "Do not delete"
    lib.save_position(identifier, 100)  # A stale autosave must not recreate last_book.
    assert not lib.toggle_bookmark(identifier, 100, "Stale bookmark")
    assert not lib.bookmarks(identifier)
    assert lib.setting("last_book") is None
    lib.delete_book(identifier)  # Idempotent after removal.


def test_delete_failure_rolls_back_database_and_files(tmp_path):
    lib, identifier, _ = make_book(tmp_path)
    files = {p: p.read_bytes() for d in ("originals", "cache") for p in (lib.root / d).iterdir()}
    with lib.connect() as c:
        c.execute(
            "CREATE TRIGGER stop_delete BEFORE DELETE ON books BEGIN SELECT RAISE(ABORT, 'test failure'); END"
        )
    with pytest.raises(sqlite3.DatabaseError):
        lib.delete_book(identifier)
    assert lib.book(identifier)["position"] == 31
    assert lib.bookmarks(identifier)[0]["position"] == 31
    assert all(p.read_bytes() == data for p, data in files.items())
    assert not list(lib.root.glob(".delete-*"))


def test_delete_rejects_path_traversal_and_symbolic_links(tmp_path):
    lib, identifier, _ = make_book(tmp_path)
    with pytest.raises(ValueError):
        lib.delete_book("../outside")
    cache = lib.root / "cache" / f"{identifier}.json.z"
    outside = tmp_path / "outside"
    outside.write_bytes(cache.read_bytes())
    cache.unlink()
    try:
        cache.symlink_to(outside)
    except OSError:
        pytest.skip("This host does not permit test symlinks")
    with pytest.raises(ValueError):
        lib.delete_book(identifier)
    assert outside.exists() and lib.book(identifier)


@pytest.mark.asyncio
@pytest.mark.parametrize("language,columns", [("zh", 42), ("en", 42), ("zh", 110), ("en", 110)])
async def test_shelf_actions_require_confirmation_and_support_restore(tmp_path, language, columns):
    lib, identifier, original = make_book(tmp_path)
    lib.set_setting("language", language)
    app = ModuApp(lib, shelf=True)
    async with app.run_test(size=(columns, 30)) as pilot:
        await pilot.pause()
        for button in app.query("#shelf-actions Button"):
            assert button.region.right <= columns
            lines = [
                line.text.strip()
                for line in button.render_lines(button.size.region)
                if line.text.strip()
            ]
            assert lines == [button.label.plain]
        await pilot.press("a")
        assert isinstance(app.screen, ConfirmBookModal)
        assert app.focused.id == "cancel-book"
        await pilot.press("enter")  # Default is Cancel, not a destructive action.
        assert not lib.book(identifier)["archived"]
        await pilot.press("a")
        await pilot.click("#confirm-book")
        assert lib.book(identifier)["archived"] and not lib.books()
        await pilot.press("v")
        assert app.show_archived and app.query_one(DataTable).row_count == 1
        await pilot.press("a")
        await pilot.click("#confirm-book")
        assert not lib.book(identifier)["archived"]
        await pilot.press("v", "d")
        assert isinstance(app.screen, ConfirmBookModal)
        await pilot.press("escape")
        assert lib.book(identifier)
        await pilot.press("d")
        assert app.screen.query_one("#confirm-book", Button).region.bottom <= 30
        await pilot.click("#confirm-book")
        assert lib.book(identifier) is None and original.exists()
        await pilot.press("q")
    assert lib.setting("last_book") is None

from threading import Event

import pytest
from rich.cells import cell_len
from textual.widgets import OptionList

from modu.app import ModuApp
from modu.library import Library
from modu.model import Block, Document, Layout, PageIndex
from modu.reader import Reader


def chapter_document():
    return Document(
        "Chapter boundaries",
        "",
        [
            Block("Title", "heading"),
            Block("Chapter 1 小窗", "heading"),
            Block("One short line. 短句，完整。"),
            Block("Chapter 2 长章", "heading"),
            Block("The light hasn't faded. “雨停了，”她说。 " * 95),
            Block("The last paragraph. 最后一句。"),
            Block("Chapter 3 " + "长标题，" * 12, "heading"),
            Block("Final line. 终。"),
        ],
    )


@pytest.mark.parametrize("width,height", [(12, 3), (28, 7), (64, 14), (80, 25)])
@pytest.mark.parametrize("spacing", [0, 1])
@pytest.mark.parametrize("enabled", [False, True])
def test_chapter_pages_exact_coverage_and_counts(width, height, spacing, enabled):
    doc = chapter_document()
    layout = Layout(doc, width, spacing, enabled)
    index = PageIndex.build(doc, width, spacing, Event(), enabled)
    pos, covered, page = (0, 0), [], 1
    while True:
        rows = layout.rows(pos, height)
        assert rows and index.pages(pos, height)[0] == page
        if enabled:
            # A heading may wrap, but the start of another chapter cannot appear
            # beneath the current chapter's text.
            headings = {doc.blocks[i].start for i, _ in doc.chapters}
            assert not any(start in headings for start, end, _, _ in rows[1:] if end > start)
        for start, end, text, _ in rows:
            covered.extend(range(start, end))
            assert cell_len(text) <= width
        following = layout.step(pos, len(rows))
        if following == layout.step(pos, len(rows) - 1) or (
            following[0] == len(doc.blocks) - 1 and following[1] >= len(layout.lines(following[0]))
        ):
            break
        pos = following
        page += 1
        assert page < 1000
    expected = [b.start + n for b in doc.blocks for n in range(len(b.text))]
    assert covered == expected  # Ordered comparison catches both overlap and loss.
    assert index.pages(pos, height) == (page, page)
    for h in range(1, 9):
        index.pages(pos, h)
    assert len(index._chapter_page_cache) <= 3


@pytest.mark.asyncio
async def test_chapter_setting_default_toggle_and_resume(tmp_path):
    path = tmp_path / "chapters.md"
    path.write_text("# First\n\nOne.\n\n# Second\n\nTwo.\n\n# Third\n\nThree.")
    library = Library(tmp_path / "library")
    identifier, _ = library.import_file(path)
    app = ModuApp(library, start_book=identifier)
    async with app.run_test(size=(110, 36)) as pilot:
        await pilot.pause(0.3)
        reader = app.query_one(Reader)
        assert reader.chapter_breaks is True
        assert [row[2] for row in reader.rows if row[2]] == ["First", "One."]
        await pilot.press("right")
        assert [row[2] for row in reader.rows if row[2]] == ["Second", "Two."]
        anchor = reader.anchor
        for language in ("zh", "en"):
            app.set_language(language)
            for columns in (42, 59, 70, 84, 110):
                await pilot.resize_terminal(columns, 28)
                await pilot.press("s")
                choices = app.screen.query_one(OptionList)
                label = str(choices.get_option_at_index(0).prompt)
                assert cell_len(label) <= choices.content_size.width
                await pilot.press("escape")
                assert reader.anchor == anchor
        await pilot.press("s", "enter")
        assert reader.chapter_breaks is False
        assert library.setting("chapter_breaks") is False
        assert reader.anchor == anchor
        assert "Third" in [row[2] for row in reader.rows]
        await pilot.press("q")
    resumed = ModuApp(Library(library.root))
    async with resumed.run_test(size=(84, 36)) as pilot:
        await pilot.pause(0.3)
        reader = resumed.query_one(Reader)
        assert reader.chapter_breaks is False and reader.anchor == anchor
        await pilot.press("s", "enter")
        assert reader.chapter_breaks is True
        assert reader.anchor == anchor
        assert "Third" not in [row[2] for row in reader.rows]


@pytest.mark.asyncio
async def test_chapter_wheel_previous_page_and_resize_coverage(tmp_path):
    doc = chapter_document()
    app = ModuApp(Library(tmp_path / "library"))
    async with app.run_test(size=(84, 24)) as pilot:
        reader = app.query_one(Reader)
        # This test needs a visible reader but no asynchronous import worker.
        app.query_one("#shelf").display = False
        app.query_one("#reading").display = True
        await pilot.pause()
        reader.load(doc)
        reader.move(3)
        assert reader.pos == (1, 0)  # Wheel cannot skip a one-line title chapter.
        reader.move(50)
        assert reader.pos == (3, 0)
        reader.page_index = PageIndex.build(doc, reader.body_width, 1, Event(), True)
        reader.action_page(-1)
        assert reader.pos == (1, 0)
        reader.jump(doc.blocks[6].start)
        reader.page_index = PageIndex.build(doc, reader.body_width, 1, Event(), True)
        reader.action_page(-1)
        assert reader.pos[0] >= 3
        assert reader.rows[-1][1] == doc.blocks[5].start + len(doc.blocks[5].text)
        reader.action_page(1)
        assert reader.anchor == doc.blocks[6].start
        reader.jump(0)
        seen, anchors = [], []
        sizes = [(42, 18), (84, 24), (110, 36), (70, 20)]
        for step in range(500):
            anchor = reader.anchor
            await pilot.resize_terminal(*sizes[step % len(sizes)])
            assert reader.anchor == anchor
            anchors.append(anchor)
            seen.extend(n for a, b, _, _ in reader.rows for n in range(a, b))
            reader.action_page(1)
            if reader.anchor == anchor:
                break
        assert seen == [b.start + n for b in doc.blocks for n in range(len(b.text))]
        assert len(anchors) > 4

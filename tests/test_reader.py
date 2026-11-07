import time
import zipfile
import pytest
from rich.cells import cell_len
from modu.model import Document, Block, Layout, wrap, CLOSE, OPEN
from modu.library import Library
from modu.parsers import parse_file
from modu.app import ModuApp
from modu.reader import Reader
from modu.themes import PALETTES, LIGHT_PALETTES

TEXT = "“你好，世界！”她说。窗外落着雨，灯光映在纸上；他翻开《河岸手记》，轻轻读道：「灯光微暖，湖面平静。」"


@pytest.fixture
def library(tmp_path):
    p = tmp_path / "阅读测试.txt"
    p.write_text(
        "第一章 风起\n"
        + (TEXT + "\n") * 50
        + "第二章 山海\n"
        + (TEXT + "\n") * 50
        + "第三章 归途\n"
        + (TEXT + "\n") * 20,
        encoding="utf-8",
    )
    lib = Library(tmp_path / "library")
    id, _ = lib.import_file(p)
    return lib, id


@pytest.mark.parametrize("width", [8, 11, 16, 25, 39, 40, 63, 64, 79, 80, 96])
def test_punctuation_and_exact_coverage(width):
    text = TEXT * 40 + " Latin words e\u0301 English /long/URL1234567890/"
    lines = wrap(text, width)
    assert "".join(line.text for line in lines) == text
    assert all(cell_len(line.text) <= width for line in lines)
    assert all(line.text[0] not in CLOSE for line in lines[1:])
    assert all(line.text[-1] not in OPEN for line in lines[:-1])
    assert all(a.end == b.start for a, b in zip(lines, lines[1:]))


@pytest.mark.parametrize("width,height", [(16, 8), (64, 14), (80, 25), (96, 40)])
def test_continuous_paging_covers_every_source_character(library, width, height):
    lib, id = library
    doc = lib.load(id)
    layout = Layout(doc, width)
    pos = (0, 0)
    covered = set()
    steps = 0
    while True:
        for start, end, _, _ in layout.rows(pos, height):
            covered.update(range(start, end))
        nxt = layout.step(pos, height - 1)
        steps += 1
        if nxt == pos:
            break
        pos = nxt
        assert steps < 10000
    wanted = {b.start + i for b in doc.blocks for i in range(len(b.text))}
    assert wanted <= covered
    assert len(layout.cache) <= 512
    # Reverse traversal also reaches the beginning without discontinuity.
    while pos != (0, 0):
        pos = layout.step(pos, -height + 1)
    assert pos == (0, 0)


def test_import_dedup_encoding_and_durable_state(library, tmp_path):
    lib, id = library
    assert lib.import_file(tmp_path / "阅读测试.txt") == (id, False)
    lib.save_position(id, 234)
    assert lib.toggle_bookmark(id, 234, "测试")
    lib.set_setting("theme", "modu-paper")
    again = Library(lib.root)
    assert again.book(id)["position"] == 234
    assert again.bookmarks(id)[0]["position"] == 234
    assert again.setting("theme") == "modu-paper"
    for encoding in ["utf-8-sig", "utf-16", "gb18030"]:
        p = tmp_path / f"{encoding}.txt"
        p.write_bytes(TEXT.encode(encoding))
        assert parse_file(p).blocks[0].text == TEXT


def test_four_formats(tmp_path):
    md = tmp_path / "测试.md"
    md.write_text(
        "# 标题\n\n这是**粗体**与[链接](https://example.com)。\n\n## 章节\n\n- 条目\n\n```py\nprint(42)\n```",
        encoding="utf-8",
    )
    doc = parse_file(md)
    assert "粗体与链接" in doc.text and len(doc.chapters) == 2
    epub = tmp_path / "测试.epub"
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>',
        )
        z.writestr(
            "OEBPS/content.opf",
            '<package><metadata><title>中文测试</title><creator>墨读</creator></metadata><manifest><item id="c1" href="one.xhtml"/><item id="c2" href="two.xhtml"/></manifest><spine><itemref idref="c2"/><itemref idref="c1"/></spine></package>',
        )
        z.writestr("OEBPS/one.xhtml", "<html><body><h1>第一章</h1><p>这是正文。</p></body></html>")
        z.writestr(
            "OEBPS/two.xhtml", "<html><body><h1>第二章</h1><p>按 spine 顺序。</p></body></html>"
        )
    doc = parse_file(epub)
    assert doc.title == "中文测试" and doc.blocks[0].text == "第二章" and len(doc.chapters) == 2
    from tests.fixtures import make_pdf

    pdf = tmp_path / "测试.pdf"
    make_pdf(pdf)
    doc = parse_file(pdf)
    assert "中文标点，测试。" in doc.text and len(doc.chapters) == 1
    blank = tmp_path / "扫描.pdf"
    make_pdf(blank, blank=True)
    with pytest.raises(ValueError, match="OCR"):
        parse_file(blank)


def test_controls_and_lazy_large_book():
    from modu.model import clean

    assert "\x1b" not in clean("安全\x1b[31m\x00文字")
    doc = Document("长篇", "", [Block(TEXT * 10) for _ in range(10000)])
    start = time.perf_counter()
    layout = Layout(doc, 80)
    rows = layout.rows((0, 0), 40)
    assert len(rows) == 40 and len(layout.cache) < 10
    assert time.perf_counter() - start < 1


@pytest.mark.asyncio
async def test_ui_resize_theme_search_bookmark_resume(library):
    lib, id = library
    app = ModuApp(lib, start_book=id)
    async with app.run_test(size=(110, 36)) as pilot:
        await pilot.pause(0.5)
        reader = app.query_one(Reader)
        await pilot.press("space", "space", "space")
        await pilot.pause(0.1)
        anchor = reader.anchor
        assert anchor > 0
        for width, height in [(65, 24), (140, 45), (42, 18), (100, 30), (80, 24), (110, 36)] * 3:
            await pilot.resize_terminal(width, height)
            await pilot.pause(0.05)
            assert reader.anchor == anchor
            assert reader.rail.region.right == width
            assert reader.region.right == reader.rail.region.x
            assert app.query_one("#toc-sidebar").display == (width >= 70)
            assert (
                app.query_one("#toc-sidebar").region.x == 0
                or not app.query_one("#toc-sidebar").display
            )
            assert reader.rows[0][0] <= anchor <= reader.rows[0][1]
            for row in reader.rows:
                assert cell_len(row[2]) <= reader.body_width
        for _ in PALETTES:
            await pilot.press("t")
            await pilot.pause(0.05)
            assert reader.anchor == anchor
        await pilot.press("s")
        await pilot.pause(0.1)
        await pilot.press(*(["down"] * (len(PALETTES) + 1)), "enter")
        await pilot.pause(0.1)
        assert reader.read_width == 64 and reader.anchor == anchor
        await pilot.press("s")
        await pilot.pause(0.1)
        await pilot.press(*(["down"] * (len(PALETTES) + 5)), "enter")
        await pilot.pause(0.1)
        assert reader.paragraph_spacing == 0 and reader.anchor == anchor
        await pilot.press("b")
        await pilot.pause(0.1)
        assert lib.bookmarks(id)[0]["position"] == anchor
        await pilot.press("m")
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert reader.anchor == anchor
        await pilot.press("slash")
        await pilot.pause(0.1)
        from textual.widgets import Input, OptionList

        app.screen.query_one(Input).value = "湖面平静"
        await pilot.pause(0.4)
        assert app.screen.query_one(OptionList).option_count > 0
        await pilot.press("enter")
        await pilot.pause(0.2)
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert reader.highlight == "湖面平静"
        toc = app.query_one("#toc-list", OptionList)
        toc.focus()
        toc.highlighted = 1
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert reader.anchor == app.doc.blocks[app.doc.chapters[1][0]].start
        assert app.current_chapter_index == 1
        anchor = reader.anchor
        await pilot.press("c")
        await pilot.pause(0.1)
        assert not app.query_one("#toc-sidebar").display and reader.anchor == anchor
        await pilot.press("c")
        await pilot.pause(0.1)
        assert app.query_one("#toc-sidebar").display and reader.anchor == anchor
        reader.show_scrollbar()
        assert reader.scrollbar_visible
        await pilot.pause(2.2)
        assert not reader.scrollbar_visible
        reader.move(7)
        await pilot.pause(0.1)
        final_anchor = reader.anchor
        await pilot.press("q")
    assert lib.book(id)["position"] == final_anchor
    app2 = ModuApp(lib)
    async with app2.run_test(size=(75, 25)) as pilot:
        await pilot.pause(0.5)
        assert app2.query_one(Reader).anchor == final_anchor
        await pilot.press("q")


@pytest.mark.asyncio
async def test_ui_import_from_empty_shelf(tmp_path):
    from textual.widgets import Input
    from modu.app import ImportModal

    p = tmp_path / "含 空格的书.md"
    p.write_text("# 中文书名\n\n正文内容。\n\n## 第二章\n\n接着阅读。", encoding="utf-8")
    lib = Library(tmp_path / "shelf")
    app = ModuApp(lib)
    async with app.run_test(size=(95, 30)) as pilot:
        await pilot.pause(0.2)
        await pilot.press("i")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ImportModal)
        app.screen.query_one(Input).value = str(p)
        await pilot.press("enter")
        await pilot.pause(0.6)
        assert app.reading and app.doc.title == "含 空格的书"
        assert len(lib.books()) == 1
        # All returned cells have explicit background and no residual line breaks.
        from modu.reader import PALETTES

        reader = app.query_one(Reader)
        for name in PALETTES:
            app.apply_theme(name)
            await pilot.pause(0.1)
            for y in range(reader.size.height):
                strip = reader.render_line(y)
                assert strip.cell_length == reader.size.width
                for segment in strip:
                    assert "\n" not in segment.text
                    assert segment.style.bgcolor.triplet.hex == PALETTES[name][0].lower()
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert not app.reading
        await pilot.press("enter")
        await pilot.pause(0.4)
        assert app.reading
        await pilot.press("q")


@pytest.mark.asyncio
async def test_immediate_quit_flushes_latest_position(library):
    lib, id = library
    app = ModuApp(lib, start_book=id)
    async with app.run_test(size=(90, 28)) as pilot:
        await pilot.pause(0.3)
        reader = app.query_one(Reader)
        reader.move(37)
        anchor = reader.anchor
        # No pause / message-loop turn between movement and quit.
        app.action_quit()
    assert lib.book(id)["position"] == anchor > 0


@pytest.mark.asyncio
async def test_adjacent_pages_do_not_repeat_after_resize(library):
    lib, identifier = library
    app = ModuApp(lib, start_book=identifier)
    async with app.run_test(size=(110, 36)) as pilot:
        await pilot.pause(0.3)
        reader = app.query_one(Reader)
        for spacing in (0, 1):
            app.setting_result(f"spacing:{spacing}")
            await pilot.press("home")
            for columns, rows in [(65, 24), (110, 36), (84, 42), (45, 18), (140, 45)]:
                await pilot.resize_terminal(columns, rows)
                await pilot.pause(0.05)
                before = list(reader.rows)
                previous_end = max(end for start, end, text, kind in before if text.strip())
                await pilot.press("space")
                await pilot.pause(0.05)
                following_start = next(
                    start for start, end, text, kind in reader.rows if text.strip()
                )
                assert following_start >= previous_end, "Next page repeated source characters"
                assert not app.doc.text[previous_end:following_start].strip(), (
                    "Next page skipped text"
                )
                await pilot.press("pageup")
                await pilot.pause(0.05)
                assert reader.rows == before, "Previous page did not return to the same boundary"
                await pilot.press("pagedown")
                await pilot.pause(0.05)
        reader.jump(len(app.doc.text) - 1)
        last_page = list(reader.rows)
        last_anchor = reader.anchor
        await pilot.press("space", "right", "pagedown")
        await pilot.pause(0.05)
        assert reader.rows == last_page and reader.anchor == last_anchor
        await pilot.press("q")


def test_palette_contrast_and_light_dark_modes(library):
    def luminance(color):
        channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
        return sum(a * b for a, b in zip(linear, (0.2126, 0.7152, 0.0722)))

    def contrast(a, b):
        low, high = sorted((luminance(a), luminance(b)))
        return (high + 0.05) / (low + 0.05)

    app = ModuApp(library[0])
    assert len(PALETTES) == 8
    for name, (bg, fg, accent, muted, panel, label) in PALETTES.items():
        assert contrast(bg, fg) >= 7, (name, "body")
        assert contrast(bg, accent) >= 4.5, (name, "accent / search highlight")
        assert contrast(bg, muted) >= 4.5, (name, "secondary text")
        assert app.get_theme(name).dark == (name not in LIGHT_PALETTES)
        assert (luminance(bg) > 0.5) == (name in LIGHT_PALETTES)


@pytest.mark.asyncio
async def test_resize_keeps_exact_first_character_and_paragraph_gap(library):
    lib, identifier = library
    app = ModuApp(lib, start_book=identifier)
    async with app.run_test(size=(110, 36)) as pilot:
        await pilot.pause(0.3)
        reader = app.query_one(Reader)
        anchor = app.doc.blocks[2].start + 17
        reader.jump(anchor)
        for columns, rows in [(110, 36), (65, 24), (140, 45), (45, 18), (84, 42)] * 2:
            await pilot.resize_terminal(columns, rows)
            await pilot.pause(0.05)
            first = next(row for row in reader.rows if row[2])
            assert first[0] == anchor, "Resize reintroduced text before the saved character"
            assert first[2] == app.doc.text[first[0] : first[1]]
        # A saved paragraph gap must not become the preceding paragraph's last line.
        gap = app.doc.blocks[2].start + len(app.doc.blocks[2].text)
        reader.jump(gap)
        await pilot.pause(0.05)
        first = next(row for row in reader.rows if row[2])
        assert first[0] == app.doc.blocks[3].start
        await pilot.press("q")


def test_page_index_counts_rows_without_a_trailing_blank_page():
    from threading import Event
    from modu.model import PageIndex

    doc = Document("计页", "", [Block("一二三四"), Block("五六七八九十")])
    index = PageIndex.build(doc, 4, 1, Event())
    # Two rows, one gap, three rows; there is no gap after the final paragraph.
    assert index.total_rows == 6
    assert index.pages((0, 0), 2) == (1, 3)
    assert index.pages((0, 2), 2) == (2, 3)
    assert index.pages((1, 1), 2) == (3, 3)
    assert index.pages((1, 2), 3) == (2, 2)
    compact = PageIndex.build(doc, 4, 0, Event())
    assert compact.total_rows == 5
    cancelled = Event()
    cancelled.set()
    assert PageIndex.build(doc, 4, 1, cancelled) is None


@pytest.mark.asyncio
async def test_live_page_count_resize_and_theme_persistence(library):
    from textual.widgets import Static

    lib, identifier = library
    app = ModuApp(lib, start_book=identifier)
    async with app.run_test(size=(110, 36)) as pilot:
        await pilot.pause(0.4)
        reader = app.query_one(Reader)

        async def ready():
            key = (identifier, reader.body_width, reader.paragraph_spacing, reader.chapter_breaks)
            for _ in range(80):
                if key in app.page_indexes:
                    return app.page_indexes[key]
                await pilot.pause(0.05)
            raise AssertionError("Background page count did not finish")

        index = await ready()
        first, total = index.pages(reader.pos, reader.body_height)
        assert first == 1 and total > 1
        await pilot.press("space")
        await pilot.pause(0.05)
        assert index.pages(reader.pos, reader.body_height) == (2, total)
        assert "2 /" in str(app.query_one("#page-progress", Static).content)
        for columns, rows in [(65, 24), (140, 45), (84, 42), (45, 18)]:
            anchor = reader.anchor
            await pilot.resize_terminal(columns, rows)
            await pilot.pause(0.05)
            resized = await ready()
            current, count = resized.pages(reader.pos, reader.body_height)
            assert reader.anchor == anchor and 1 <= current <= count
            assert f"{current} / {count} 页" in str(app.query_one("#page-progress", Static).content)
            assert len(app.page_indexes) <= 3
        app.apply_theme("modu-pine")
        await pilot.pause(0.05)
        await pilot.press("q")
    again = ModuApp(lib)
    assert again.theme == "modu-pine" and lib.book(identifier)["position"] == anchor

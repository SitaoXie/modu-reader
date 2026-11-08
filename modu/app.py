from __future__ import annotations
import asyncio
from collections import OrderedDict
from pathlib import Path
import shlex
import sqlite3
from threading import Event
from rich.text import Text
from textual import work, on
from textual.app import App
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Button, DataTable, DirectoryTree, Input, Label, OptionList, Static
from textual.widgets.option_list import Option
from .library import Library, SUPPORTED
from .safety import import_paths
from .model import clean, PageIndex
from .terminal_render import anchor_update
from .reader import Reader, ReaderRail
from .scrollbars import SolidScrollBarRender
from .themes import PALETTES, LIGHT_PALETTES
from .i18n import translate, normalize_language, message


class LocalizedModal(ModalScreen):
    def tr(self, text, **values):
        return self.app.tr(text, **values)


class ChapterList(OptionList):
    def on_resize(self):
        # The list's own Resize arrives after the app's Resize, once its new
        # viewport and scroll limits are available.
        self.call_after_refresh(self.app.follow_current_chapter)

    def on_show(self):
        self.call_after_refresh(self.app.follow_current_chapter)


class ChoiceModal(LocalizedModal):
    BINDINGS = [("escape", "dismiss", "关闭")]

    def __init__(self, title, options, subtitle="↑ ↓ 选择 · Enter 确认 · Esc 返回"):
        super().__init__()
        self.heading, self.options, self.subtitle = title, options, subtitle

    def compose(self):
        with Vertical(classes="dialog"):
            yield Label(self.tr(self.heading), classes="dialog-title")
            yield Static(self.tr(self.subtitle), classes="dialog-hint")
            yield OptionList(
                *(Option(Text(label), id=str(i)) for i, (label, _) in enumerate(self.options)),
                id="choices",
            )
            yield Button(self.tr("返回  Esc"), id="close")

    def on_mount(self):
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event):
        self.dismiss(self.options[event.option_index][1])

    @on(Button.Pressed, "#close")
    def close(self):
        self.dismiss(None)


class ConfirmBookModal(LocalizedModal):
    BINDINGS = [("escape", "cancel", "取消")]

    def __init__(self, action, title):
        super().__init__()
        self.book_action, self.book_title = action, title

    def compose(self):
        headings = {"archive": "归档这本书？", "restore": "恢复这本书？", "delete": "删除这本书？"}
        descriptions = {
            "archive": "书籍移入归档，正文、书签和阅读进度保留，可随时恢复。",
            "restore": "书籍移回书架，继续保留书签和阅读进度。",
            "delete": "将删除书库副本、缓存、书签和阅读进度，无法撤销。最初导入的原始文件不会删除。",
        }
        labels = {"archive": "确认归档", "restore": "确认恢复", "delete": "确认删除"}
        with Vertical(classes="dialog", id="confirm-book-dialog"):
            yield Label(self.tr(headings[self.book_action]), classes="dialog-title")
            yield Static(Text(self.book_title, style="bold"), id="confirm-book-title")
            yield Static(self.tr(descriptions[self.book_action]), id="confirm-book-description")
            with Horizontal(classes="dialog-buttons"):
                yield Button(self.tr("取消"), id="cancel-book")
                yield Button(self.tr(labels[self.book_action]), id="confirm-book")

    def on_mount(self):
        self.query_one("#cancel-book", Button).focus()

    def action_cancel(self):
        self.dismiss(False)

    @on(Button.Pressed)
    def choose(self, event):
        event.stop()
        self.dismiss(event.button.id == "confirm-book")


class FileTree(DirectoryTree):
    def filter_paths(self, paths):
        return [
            p
            for p in paths
            if not p.name.startswith(".") and (p.is_dir() or p.suffix.lower() in SUPPORTED)
        ]


class ImportModal(LocalizedModal):
    BINDINGS = [("escape", "dismiss", "取消")]

    def compose(self):
        with Vertical(classes="dialog", id="import-dialog"):
            yield Label(self.tr("把好书放进书架"), classes="dialog-title")
            with VerticalScroll(id="import-info"):
                yield Static(
                    self.tr("TXT · EPUB · PDF · Markdown  /  支持文件或文件夹路径"),
                    classes="dialog-hint",
                )
                yield Static(
                    self.tr("导入会在书库创建独立副本。成功后，修改、移动或删除原文件均不影响阅读；不会自动同步。"),
                    id="import-copy-note",
                )
                yield Static(
                    Text(self.tr("副本保存目录：{path}", path=str(self.app.library.root / "originals"))),
                    id="import-copy-path",
                )
            yield Input(placeholder=self.tr("粘贴路径，或从下方选择文件"), id="path")
            yield FileTree(str(Path.home()), id="file-tree")
            with Horizontal(classes="dialog-buttons"):
                yield Button(self.tr("导入"), variant="primary", id="import-go")
                yield Button(self.tr("取消"), id="cancel")

    def on_mount(self):
        self.query_one(Input).focus()

    @on(DirectoryTree.FileSelected)
    def picked(self, event):
        self.query_one(Input).value = str(event.path)

    @on(Input.Submitted)
    @on(Button.Pressed, "#import-go")
    def submit(self):
        raw = self.query_one(Input).value.strip()
        # Accept Finder drag-and-drop's shell-escaped path as well as plain text.
        if not Path(raw).expanduser().exists():
            try:
                parts = shlex.split(raw)
                if len(parts) == 1:
                    raw = parts[0]
            except ValueError:
                pass
        if raw:
            self.dismiss(raw)

    @on(Button.Pressed, "#cancel")
    def cancel(self):
        self.dismiss(None)


class SearchModal(LocalizedModal):
    BINDINGS = [("escape", "dismiss", "关闭")]

    def __init__(self, doc):
        super().__init__()
        self.doc = doc
        self.results = []
        self.generation = 0
        self.timer = None

    def compose(self):
        with Vertical(classes="dialog"):
            yield Label(self.tr("在本书中搜索"), classes="dialog-title")
            yield Input(placeholder=self.tr("输入文字，Enter 搜索 · ↓ 选择结果"), id="search-query")
            yield Static(
                self.tr("全文搜索 · 中文短语与标点均可检索"),
                id="search-info",
                classes="dialog-hint",
            )
            yield OptionList(id="search-results")
            yield Button(self.tr("返回  Esc"), id="close")

    def on_mount(self):
        self.query_one(Input).focus()

    @on(Input.Changed)
    def changed(self, event):
        self.generation += 1
        if self.timer:
            self.timer.stop()
        self.timer = self.set_timer(0.25, self.search)

    @on(Input.Submitted)
    def submitted(self):
        self.search()
        self.query_one(OptionList).focus()

    def on_key(self, event):
        if event.key == "down" and isinstance(self.focused, Input):
            self.query_one(OptionList).focus()
            event.stop()

    @work(exclusive=True)
    async def search(self):
        query = self.query_one(Input).value.strip()
        generation = self.generation
        results, more = await asyncio.to_thread(self.doc.search, query)
        if generation != self.generation or not self.is_mounted:
            return
        self.results = results
        choices = self.query_one(OptionList)
        choices.clear_options()
        choices.add_options(
            [Option(Text(f"{i + 1:02d}  {snippet}")) for i, (_, snippet) in enumerate(results)]
        )
        if results:
            choices.highlighted = 0
        self.query_one("#search-info", Static).update(
            self.tr("{p0}{p1} 个结果", p0=len(results), p1="+" if more else "")
            + (self.tr(" · 显示前 200 个，请细化关键词") if more else self.tr(" · Enter 跳转"))
            if query
            else self.tr("全文搜索 · 中文短语与标点均可检索")
        )

    def on_option_list_option_selected(self, event):
        if event.option_index < len(self.results):
            self.dismiss((self.results[event.option_index][0], self.query_one(Input).value.strip()))

    @on(Button.Pressed, "#close")
    def close(self):
        self.dismiss(None)


class HelpModal(LocalizedModal):
    BINDINGS = [("escape,question_mark", "dismiss", "返回")]

    def compose(self):
        with Vertical(classes="dialog", id="help-dialog"):
            yield Label(self.tr("墨读 MODU · 让阅读安静下来"), classes="dialog-title")
            yield Static(
                self.tr(
                    "翻页   Space / → / PgDn       上一页   ← / PgUp / Backspace\n逐行   ↑ ↓ / j k             首尾     Home / End\n滚动   鼠标滚轮               进度     拖动右侧滚动条\n\n侧栏   c       全文搜索 /       书签     b 添加/取消 · m 查看\n章节   n 下一章 · p 上一章      书架     Esc\n主题   t       阅读设置 s       导入     i\n语言   l       退出 q / Ctrl+q              帮助 ?\n\n阅读位置自动保存；重启自动回到上次阅读。\n滚动条静止 2 秒后隐藏，鼠标靠近右缘再次显示。\n字号由终端控制；请使用终端的字体缩放快捷键。\nPDF 为文字重排，扫描 PDF 需先 OCR；EPUB 不支持 DRM。"
                ),
                id="help-text",
            )
            yield Button(self.tr("继续阅读  Esc"), id="close")

    @on(Button.Pressed)
    def close(self):
        self.dismiss(None)


class ModuApp(App):
    TITLE = "墨读 MODU"
    SUB_TITLE = "离线阅读 · 字里行间"
    CSS_PATH = "app.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("q", "leave", "退出"),
        Binding("ctrl+q", "quit", "退出", priority=True),
        Binding("escape", "shelf", "书架"),
        Binding("i", "import", "导入"),
        Binding("c", "toc", "目录"),
        Binding("slash", "search", "搜索"),
        Binding("b", "bookmark", "书签"),
        Binding("m", "bookmarks", "书签列表"),
        Binding("t", "theme_cycle", "主题"),
        Binding("s", "settings", "设置"),
        Binding("l", "language", "Language / 语言"),
        Binding("n", "chapter(1)", "下一章"),
        Binding("p", "chapter(-1)", "上一章"),
        Binding("a", "archive_book", "归档/恢复"),
        Binding("d", "delete_book", "删除书籍"),
        Binding("v", "archive_view", "归档书架"),
        Binding("question_mark", "help", "帮助"),
    ]

    def __init__(self, library: Library, start_book=None, shelf=False):
        super().__init__()
        self.library = library
        self.language = normalize_language(library.setting("language", "zh"))
        self.title = "墨读 MODU" if self.language == "zh" else "MODU"
        self.sub_title = self.tr("离线阅读 · 字里行间")
        self.start_book, self.start_shelf = start_book, shelf
        self.book_id = None
        self.doc = None
        self.pending_save = False
        self.saved_anchor = 0
        self.loading_book = False
        self.importing = False
        self.sidebar_open = self.library.setting("sidebar_open", True)
        self.current_chapter_index = -1
        self.show_archived = False
        self.page_indexes = OrderedDict()
        self.page_index_key = None
        self.page_index_cancel = Event()
        self.page_index_failed = None
        self._terminal_guard_active = False
        for name, (bg, fg, accent, muted, panel, label) in PALETTES.items():
            self.register_theme(
                Theme(
                    name=name,
                    primary=accent,
                    secondary=muted,
                    accent=accent,
                    foreground=fg,
                    background=bg,
                    surface=panel,
                    panel=panel,
                    success=accent,
                    warning=accent,
                    error="#C57264",
                    dark=name not in LIGHT_PALETTES,
                    variables={
                        "block-cursor-text-style": "none",
                        "footer-key-foreground": accent,
                        "input-selection-background": panel,
                        "border": panel,
                    },
                )
            )
        theme = self.library.setting("theme", "modu-gold")
        self.theme = theme if isinstance(theme, str) and theme in PALETTES else "modu-gold"

    def tr(self, text, **values):
        return translate(self.language, text, **values)

    def chapter_label(self, index):
        block, label = self.doc.chapters[index]
        if len(self.doc.chapters) == 1 and self.doc.blocks[block].kind != "heading":
            return self.tr("正文")
        return label

    def action_language(self):
        if self.unobstructed:
            self.set_language("en" if self.language == "zh" else "zh")

    def set_language(self, language):
        self.language = normalize_language(language)
        self.library.set_setting("language", self.language)
        self.title = "墨读 MODU" if self.language == "zh" else "MODU"
        self.sub_title = self.tr("离线阅读 · 字里行间")
        labels = {
            "brand": "墨读 [bold]MODU[/]",
            "tagline": "字里行间，自有天地",
            "import": "导入 i",
            "theme-cycle": "主题 t",
            "help": "帮助 ?",
            "language": "EN l",
            "shelf-title": "[bold]我的书架[/]",
            "empty": "按 i 导入本地书籍，或在终端输入 modu 文件路径\n支持 TXT、EPUB、PDF、Markdown · 所有内容只保存在本机",
            "shelf-hint": "↑ ↓ 选择  ·  Enter 打开  ·  i 导入  ·  q 退出",
            "shelf-button": "‹ 书架",
            "toc": "目录 c",
            "search": "搜索 /",
            "bookmarks": "书签 m",
            "settings": "设置 s",
            "toc-heading": "章节目录",
            "toc-hint": "Enter 跳转 · c 收起",
        }
        for identity, text in labels.items():
            widget = self.query_one("#" + identity)
            if isinstance(widget, Button):
                widget.label = self.tr(text)
                # Textual Button.label repaints but does not request layout.
                # English labels may be wider than the existing Chinese button.
                widget.refresh(layout=True)
            else:
                widget.update(self.tr(text))
        table = self.query_one(DataTable)
        cursor = table.cursor_row
        table.clear(columns=True)
        table.add_columns(*(self.tr(text) for text in ("书名", "作者", "格式", "进度")))
        self.refresh_shelf()
        if table.row_count:
            table.move_cursor(row=min(cursor, table.row_count - 1))
        if self.doc:
            toc = self.query_one("#toc-list", OptionList)
            for index in range(len(self.doc.chapters)):
                toc.replace_option_prompt_at_index(
                    index, Text(f"  {index + 1:02d}  {self.chapter_label(index)}")
                )
            self.current_chapter_index = -1
            self.update_status()
        self.notice(self.tr("界面语言已切换为中文"))

    def _display(self, screen, renderable):
        # Keep this serialization hook covered by actual PTY regression tests.
        if renderable is not None:
            self._hide_terminal_cursor(flush=False)
        super()._display(screen, anchor_update(renderable))

    def _terminal_guard_ready(self):
        return (
            self._terminal_guard_active
            and self._running
            and not self._closed
            and not self.is_headless
            and self._driver is not None
        )

    def _hide_terminal_cursor(self, *, flush=True):
        # Textual draws Input carets itself; the native cursor stays hidden.
        if self._terminal_guard_ready():
            self._driver.write("\x1b[?25l")
            if flush:
                self._driver.flush()

    def _restore_terminal_modes(self):
        if not self._terminal_guard_ready():
            return
        # A host may reset mouse AND focus reporting when switching panes, so
        # FocusIn alone cannot recover it. Reassert modes without repainting.
        # Do not re-enable 1004 here: xterm replies with FocusIn/Out on every
        # enable, which would form a feedback loop and interrupt held drags.
        sequence = "\x1b[?25l"
        if self._driver._mouse:
            # Reassert ANY directly: toggling through VT200 would temporarily
            # remove drag listeners. Keep a negotiated pixel encoding intact.
            encoding = 1016 if getattr(self._driver, "_mouse_pixels", False) else 1006
            sequence += f"\x1b[?1003h\x1b[?{encoding}h"
        self._driver.write(sequence)
        self._driver.flush()

    def _release_interrupted_mouse(self):
        # Focus may leave before MouseUp reaches the app. Do not let an old
        # capture route all subsequent clicks to the reading rail.
        captured = self.mouse_captured
        self.capture_mouse(None)
        self._mouse_down_widget = None
        if isinstance(captured, ReaderRail):
            captured.reader.dragging = False

    def on_app_focus(self):
        self._release_interrupted_mouse()
        self._restore_terminal_modes()

    def on_app_blur(self):
        self._release_interrupted_mouse()
        self._hide_terminal_cursor()

    def _pause_terminal_guard(self, _app):
        self._terminal_guard_active = False
        self._release_interrupted_mouse()

    def _resume_terminal_guard(self, _app):
        self._terminal_guard_active = True
        self._restore_terminal_modes()

    def compose(self):
        with Horizontal(id="brandbar"):
            yield Static(self.tr("墨读 [bold]MODU[/]"), id="brand")
            yield Static(self.tr("字里行间，自有天地"), id="tagline")
            yield Button(self.tr("导入 i"), id="import")
            yield Button(self.tr("主题 t"), id="theme-cycle")
            yield Button(self.tr("EN l"), id="language")
            yield Button(self.tr("帮助 ?"), id="help")
        with Vertical(id="shelf"):
            yield Static(self.tr("[bold]我的书架[/]"), id="shelf-title")
            yield Static(self.tr("一本书，一段属于自己的时间。"), id="shelf-caption")
            with Horizontal(id="shelf-actions"):
                yield Button(self.tr("归档 a"), id="archive-book")
                yield Button(self.tr("删除 d"), id="delete-book")
                yield Button(self.tr("已归档 v"), id="archive-view")
            yield DataTable(id="books", cursor_type="row", zebra_stripes=True)
            yield Static(
                self.tr(
                    "按 i 导入本地书籍，或在终端输入 modu 文件路径\n支持 TXT、EPUB、PDF、Markdown · 所有内容只保存在本机"
                ),
                id="empty",
            )
            yield Static(self.tr("↑ ↓ 选择  ·  Enter 打开  ·  i 导入  ·  q 退出"), id="shelf-hint")
        with Vertical(id="reading"):
            with Horizontal(id="bookbar"):
                yield Button(self.tr("‹ 书架"), id="shelf-button")
                yield Static("", id="book-title")
                yield Button(self.tr("目录 c"), id="toc")
                yield Button(self.tr("搜索 /"), id="search")
                yield Button(self.tr("书签 m"), id="bookmarks")
                yield Button(self.tr("设置 s"), id="settings")
            yield Static("", id="chapter")
            with Horizontal(id="reading-body"):
                reader = Reader(id="reader")
                with Vertical(id="toc-sidebar"):
                    yield Static(self.tr("章节目录"), id="toc-heading")
                    yield Static("", id="chapter-progress")
                    yield ChapterList(id="toc-list")
                    yield Static(self.tr("Enter 跳转 · c 收起"), id="toc-hint")
                yield reader
                yield ReaderRail(reader, id="reader-rail")
            with Horizontal(id="statusbar"):
                yield Static("", id="progress")
                yield Static("", id="page-progress")
                yield Static("", id="read-hint")
        yield Static("", id="notice")

    async def on_mount(self):
        self._terminal_guard_active = True
        self.app_suspend_signal.subscribe(self, self._pause_terminal_guard, immediate=True)
        self.app_resume_signal.subscribe(self, self._resume_terminal_guard, immediate=True)
        # Control sequences only, no repaint; also covers missing focus events.
        self.set_interval(0.5, self._restore_terminal_modes)
        self.query_one("#reading").display = False
        self.query_one("#notice").display = False
        self.query_one("#toc-list", OptionList).vertical_scrollbar.renderer = SolidScrollBarRender
        self.query_one(DataTable).add_columns(
            self.tr("书名"), self.tr("作者"), self.tr("格式"), self.tr("进度")
        )
        reader = self.query_one(Reader)
        reader.palette = self.theme
        reader.read_width = self.library.setting("read_width", 80)
        reader.paragraph_spacing = self.library.setting("spacing", 1)
        reader.chapter_breaks = self.library.setting("chapter_breaks", True)
        self.refresh_shelf()
        self.sync_sidebar()
        self.set_interval(0.5, self.flush_position)
        target = self.start_book or (
            None if self.start_shelf else self.library.setting("last_book")
        )
        book = self.library.book(target) if target else None
        if book and (self.start_book or not book["archived"]):
            self.open_book(target)
        else:
            self.query_one(DataTable).focus()

    @property
    def reading(self):
        return self.book_id is not None and self.query_one("#reading").display

    @property
    def unobstructed(self):
        return not isinstance(self.screen, ModalScreen)

    def refresh_shelf(self):
        table = self.query_one(DataTable)
        cursor = table.cursor_row
        table.clear()
        for book in self.library.books(archived=self.show_archived):
            progress = book["position"] / max(1, book["chars"])
            table.add_row(
                Text(book["title"]),
                Text(book["author"] or "—"),
                book["format"],
                f"{progress:.0%}" if book["opened"] else self.tr("未读"),
                key=book["id"],
            )
        self.query_one("#empty").display = table.row_count == 0
        self.query_one("#empty", Static).update(
            self.tr("还没有归档的书籍。")
            if self.show_archived
            else self.tr(
                "按 i 导入本地书籍，或在终端输入 modu 文件路径\n支持 TXT、EPUB、PDF、Markdown · 所有内容只保存在本机"
            )
        )
        table.display = table.row_count > 0
        if table.row_count:
            table.move_cursor(row=min(cursor, table.row_count - 1))
        self.query_one("#shelf-title", Static).update(
            self.tr("[bold]已归档[/]" if self.show_archived else "[bold]我的书架[/]")
        )
        for identity, label in {
            "archive-book": "恢复 a" if self.show_archived else "归档 a",
            "delete-book": "删除 d",
            "archive-view": "书架 v" if self.show_archived else "已归档 v",
        }.items():
            button = self.query_one("#" + identity, Button)
            button.label = self.tr(label)
            button.refresh(layout=True)
            if identity != "archive-view":
                button.disabled = not table.row_count
        self.query_one("#shelf-caption", Static).update(
            self.tr("{p0} 本藏书  ·  一本书，一段属于自己的时间。", p0=table.row_count)
        )

    def action_archive_view(self):
        if self.unobstructed and not self.reading and not self.loading_book:
            self.show_archived = not self.show_archived
            self.refresh_shelf()
            self.query_one(DataTable).focus()

    def action_archive_book(self):
        self.confirm_book_action("restore" if self.show_archived else "archive")

    def action_delete_book(self):
        self.confirm_book_action("delete")

    def confirm_book_action(self, action):
        if not self.unobstructed or self.reading or self.loading_book or self.importing:
            return
        table = self.query_one(DataTable)
        if not table.row_count:
            return
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        book = self.library.book(key)
        if book:
            self.push_screen(
                ConfirmBookModal(action, book["title"]),
                lambda confirmed: self.finish_book_action(key, action, confirmed),
            )

    def finish_book_action(self, book_id, action, confirmed):
        if not confirmed:
            self.query_one(DataTable).focus()
            return
        try:
            self.flush_position(force=True)
            if action == "delete":
                self.library.delete_book(book_id)
            else:
                self.library.archive_book(book_id, action == "archive")
            if self.book_id == book_id:
                self.page_index_cancel.set()
                self.page_index_key = self.page_index_failed = None
                self.book_id = self.doc = None
                self.pending_save = False
                reader = self.query_one(Reader)
                reader.doc = reader.layout_engine = reader.page_index = None
                reader.rows = []
                reader.page_history.clear()
                self.query_one("#toc-list", OptionList).clear_options()
            self.page_indexes = OrderedDict(
                (key, value) for key, value in self.page_indexes.items() if key[0] != book_id
            )
            self.refresh_shelf()
            self.notice(
                self.tr(
                    {
                        "archive": "已归档，可在已归档书架恢复。",
                        "restore": "已恢复到书架。",
                        "delete": "已删除书库副本和阅读记录。",
                    }[action]
                )
            )
        except (OSError, ValueError, sqlite3.Error) as error:
            self.notice(self.tr("操作失败：{p0}", p0=message(self.language, clean(str(error)))), 6)
        self.query_one(DataTable).focus()

    @on(DataTable.RowSelected)
    def selected(self, event):
        self.open_book(event.row_key.value)

    @work(exclusive=True, group="open")
    async def open_book(self, book_id):
        self.flush_position(force=True)
        self.loading_book = True
        self.notice(self.tr("正在打开书籍…"))
        try:
            doc = await asyncio.to_thread(self.library.load, book_id)
            book = self.library.book(book_id)
            self.doc, self.book_id = doc, book_id
            self.query_one("#shelf").display = False
            self.query_one("#reading").display = True
            self.query_one("#book-title", Static).update(Text(doc.title, style="bold"))
            reader = self.query_one(Reader)
            toc = self.query_one("#toc-list", OptionList)
            toc.clear_options()
            toc.add_options(
                [
                    Option(Text(f"  {i + 1:02d}  {self.chapter_label(i)}"))
                    for i, (_, label) in enumerate(doc.chapters)
                ]
            )
            self.current_chapter_index = -1
            self.sync_sidebar()
            reader.highlight = ""
            reader.load(doc, book["position"])
            self.call_after_refresh(reader.reflow)
            self.notice(
                " · ".join(message(self.language, warning) for warning in doc.warnings)
                if doc.warnings
                else self.tr("已回到上次阅读位置")
                if book["position"]
                else self.tr("开始阅读"),
                duration=5 if doc.warnings else 2,
            )
        except Exception as error:
            self.notice(
                self.tr("打开失败：{p0}", p0=message(self.language, str(error))), duration=7
            )
        finally:
            self.loading_book = False

    @on(Reader.PositionChanged)
    def position_changed(self):
        self.pending_save = True
        self.saved_anchor = self.query_one(Reader).anchor
        self.update_status()

    def update_status(self):
        if not self.doc:
            return
        reader = self.query_one(Reader)
        progress = reader.anchor / max(1, len(self.doc.text))
        chapters = [i for i, _ in self.doc.chapters]
        from bisect import bisect_right

        chapter = max(0, bisect_right(chapters, reader.pos[0]) - 1)
        title = self.chapter_label(chapter)
        start = self.doc.blocks[self.doc.chapters[chapter][0]].start
        end = (
            self.doc.blocks[self.doc.chapters[chapter + 1][0]].start
            if chapter + 1 < len(chapters)
            else len(self.doc.text)
        )
        chapter_progress = max(0, min(1, (reader.anchor - start) / max(1, end - start)))
        self.query_one("#chapter-progress", Static).update(
            self.tr(
                "当前 {p0}/{p1}  ·  本章 {p2:.0%}",
                p0=chapter + 1,
                p1=len(chapters),
                p2=chapter_progress,
            )
        )
        if chapter != self.current_chapter_index:
            toc = self.query_one("#toc-list", OptionList)
            previous = self.current_chapter_index
            if previous >= 0:
                toc.replace_option_prompt_at_index(
                    previous, Text(f"  {previous + 1:02d}  {self.chapter_label(previous)}")
                )
            toc.replace_option_prompt_at_index(
                chapter, Text(f"> {chapter + 1:02d}  {title}", style="bold")
            )
            self.current_chapter_index = chapter
            toc.highlighted = chapter
            self.call_after_refresh(toc.scroll_to_highlight)
        self.query_one("#chapter", Static).update(
            Text(f"{chapter + 1:02d} / {len(chapters):02d}    {title}")
        )
        self.query_one("#progress", Static).update(
            (
                f"{progress:5.1%}  ·  {len(self.doc.text) / 10000:.1f} 万字"
                if self.language == "zh"
                else f"{progress:5.1%} · {len(self.doc.text) / 1000:.1f}k chars"
            )
        )
        self.query_one("#read-hint", Static).update(
            self.tr("← → 翻页  ·  b 书签  ·  ? 帮助  ·  q 退出")
        )
        self.update_page_count()

    def update_page_count(self):
        if not self.doc or not self.reading:
            return
        reader = self.query_one(Reader)
        key = (self.book_id, reader.body_width, reader.paragraph_spacing, reader.chapter_breaks)
        label = self.query_one("#page-progress", Static)
        if key in self.page_indexes:
            self.page_indexes.move_to_end(key)
            reader.page_index = self.page_indexes[key]
            current, total = self.page_indexes[key].pages(reader.pos, reader.body_height)
            label.update(self.tr("{p0} / {p1} 页", p0=current, p1=total))
        elif self.page_index_failed == key:
            label.update(self.tr("页数暂不可用"))
        else:
            label.update(self.tr("页数计算中…"))
            if key != self.page_index_key:
                self.page_index_cancel.set()
                self.page_index_cancel = Event()
                self.page_index_key = key
                self.build_page_index(self.doc, key, self.page_index_cancel)

    @work(exclusive=True, group="page-index")
    async def build_page_index(self, document, key, cancelled):
        try:
            # Debounce interactive resizing; counting never occupies the UI loop
            # or evicts paragraphs from the reader's wrap cache.
            await asyncio.sleep(0.15)
            result = await asyncio.to_thread(
                PageIndex.build, document, key[1], key[2], cancelled, key[3]
            )
            if result is not None and not cancelled.is_set():
                self.page_indexes[key] = result
                while len(self.page_indexes) > 3:
                    self.page_indexes.popitem(last=False)
                self.update_page_count()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        except Exception:
            self.page_index_failed = key
            self.update_page_count()

    def flush_position(self, force=False):
        if self.book_id and (self.pending_save or force):
            try:
                self.saved_anchor = self.query_one(Reader).anchor
            except NoMatches:
                pass  # During teardown only the last captured source anchor remains.
            self.library.save_position(self.book_id, self.saved_anchor)
            self.pending_save = False

    def notice(self, message, duration=3):
        notice = self.query_one("#notice", Static)
        notice.update(Text(message))
        notice.display = True
        timer = getattr(self, "notice_timer", None)
        if timer:
            timer.stop()
        self.notice_timer = self.set_timer(duration, lambda: setattr(notice, "display", False))

    def action_shelf(self):
        if not self.unobstructed:
            return
        self.flush_position(force=True)
        self.query_one("#reading").display = False
        self.query_one("#shelf").display = True
        self.refresh_shelf()
        self.query_one(DataTable).focus()

    def action_leave(self):
        if self.unobstructed:
            self.action_quit()

    def action_quit(self):
        self.page_index_cancel.set()
        self.flush_position(force=True)
        self.exit()

    def on_unmount(self):
        self._terminal_guard_active = False
        self.page_index_cancel.set()
        self.flush_position(force=True)

    def action_import(self):
        if self.unobstructed and not self.importing:
            self.push_screen(ImportModal(), self.import_path)

    @work(group="import", exclusive=True)
    async def import_path(self, raw):
        if not raw:
            return
        self.importing = True
        try:
            path = Path(raw).expanduser()
            files = await asyncio.to_thread(import_paths, path)
            if not files:
                self.notice(self.tr("文件夹中没有支持的书籍。"), 5)
                return
            imported, duplicates, errors = 0, 0, []
            last_id = None
            for i, file in enumerate(files):
                self.notice(
                    self.tr("正在导入 {p0}/{p1}：{p2}", p0=i + 1, p1=len(files), p2=file.name), 60
                )
                try:
                    last_id, new = await asyncio.to_thread(self.library.import_file, file)
                    imported += int(new)
                    duplicates += int(not new)
                except Exception as e:
                    errors.append(f"{file.name}: {message(self.language, str(e))}")
            self.refresh_shelf()
            if len(files) == 1 and last_id:
                self.open_book(last_id)
            else:
                self.notice(
                    self.tr("已导入 {p0} 本 · 已有 {p1} 本", p0=imported, p1=duplicates)
                    + (self.tr(" · 失败 {p0} 本", p0=len(errors)) if errors else ""),
                    6,
                )
            if errors:
                self.push_screen(
                    ChoiceModal(
                        self.tr("部分文件未能导入"),
                        [(x, None) for x in errors],
                        self.tr("已成功导入的书籍保留在书架中"),
                    )
                )
        except (OSError, ValueError) as error:
            self.notice(self.tr("导入失败：{p0}", p0=message(self.language, clean(str(error)))), 6)
        finally:
            self.importing = False

    def sync_sidebar(self, width=None):
        sidebar = self.query_one("#toc-sidebar")
        sidebar.display = self.sidebar_open and (self.size.width if width is None else width) >= 70

    def follow_current_chapter(self):
        if self.reading and self.current_chapter_index >= 0:
            toc = self.query_one("#toc-list", OptionList)
            toc.highlighted = self.current_chapter_index
            toc.scroll_to_highlight()

    def action_toc(self):
        if self.reading and self.unobstructed:
            if self.size.width < 70:
                options = [
                    (f"{i + 1:02d}  {self.chapter_label(i)}", self.doc.blocks[b].start)
                    for i, (b, label) in enumerate(self.doc.chapters)
                ]
                self.push_screen(ChoiceModal(self.tr("章节目录"), options), self.jump_result)
                return
            self.sidebar_open = not self.sidebar_open
            self.library.set_setting("sidebar_open", self.sidebar_open)
            self.sync_sidebar()
            self.query_one(Reader).focus()

    @on(OptionList.OptionSelected, "#toc-list")
    def sidebar_selected(self, event):
        self.jump_result(self.doc.blocks[self.doc.chapters[event.option_index][0]].start)

    def jump_result(self, anchor):
        if anchor is not None:
            reader = self.query_one(Reader)
            reader.highlight = ""
            reader.jump(anchor)
            reader.focus()
            self.flush_position(force=True)

    def action_search(self):
        if self.reading and self.unobstructed:
            self.push_screen(SearchModal(self.doc), self.search_result)

    def search_result(self, result):
        if result:
            offset, query = result
            self.query_one(Reader).highlight = query
            self.query_one(Reader).jump(offset)
            self.query_one(Reader).focus()

    def action_bookmark(self):
        if self.reading and self.unobstructed:
            reader = self.query_one(Reader)
            label = self.doc.text[reader.anchor : reader.anchor + 65].replace("\n", " ")
            added = self.library.toggle_bookmark(self.book_id, reader.anchor, label)
            self.notice(self.tr("已添加书签  ·  m 查看") if added else self.tr("已取消书签"))

    def action_bookmarks(self):
        if self.reading and self.unobstructed:
            marks = self.library.bookmarks(self.book_id)
            if not marks:
                self.notice(self.tr("还没有书签  ·  按 b 添加当前位置"))
                return
            self.push_screen(
                ChoiceModal(
                    self.tr("我的书签"),
                    [
                        (
                            f"{m['position'] / max(1, len(self.doc.text)):.1%}  {m['label']}",
                            m["position"],
                        )
                        for m in marks
                    ],
                    self.tr("Enter 跳转 · 在原位置再次按 b 取消书签"),
                ),
                self.jump_result,
            )

    def action_chapter(self, direction):
        if self.reading and self.unobstructed:
            offsets = [self.doc.blocks[i].start for i, _ in self.doc.chapters]
            anchor = self.query_one(Reader).anchor
            target = (
                next((x for x in offsets if x > anchor), offsets[-1])
                if direction > 0
                else next((x for x in reversed(offsets) if x < anchor), 0)
            )
            self.jump_result(target)

    def apply_theme(self, name):
        self.theme = name
        self.library.set_setting("theme", name)
        self.query_one(Reader).palette = name
        self.query_one(Reader).refresh()
        self.query_one(ReaderRail).refresh()

    def action_theme_cycle(self):
        if self.unobstructed:
            names = list(PALETTES)
            self.apply_theme(names[(names.index(self.theme) + 1) % len(names)])
            self.notice(self.tr(PALETTES[self.theme][-1]))

    def action_settings(self):
        if not self.unobstructed:
            return
        enabled = self.query_one(Reader).chapter_breaks
        options = [
            (
                self.tr("章节另起一页  ·  开启" if enabled else "章节另起一页  ·  关闭"),
                "chapters:toggle",
            )
        ]
        options.extend(
            (self.tr("主题  ·  ") + self.tr(p[-1]), name) for name, p in PALETTES.items()
        )
        options.extend(
            [
                (
                    self.tr("正文宽度  ·  {cells} 列（约 {han} 个汉字）", cells=w, han=w // 2),
                    f"width:{w}",
                )
                for w in (64, 80, 96)
            ]
        )
        options.extend(
            [
                (self.tr("段间留白  ·  舒展"), "spacing:1"),
                (self.tr("段间留白  ·  紧凑"), "spacing:0"),
            ]
        )
        options.extend([("语言 · 中文", "language:zh"), ("Language · English", "language:en")])
        self.push_screen(
            ChoiceModal(
                self.tr("阅读设置"),
                options,
                self.tr("设置即时保存 · 字号请使用终端的字体缩放快捷键"),
            ),
            self.setting_result,
        )

    def setting_result(self, result):
        if not result:
            return
        reader = self.query_one(Reader)
        if result.startswith("language:"):
            self.set_language(result.split(":")[1])
        elif result == "chapters:toggle":
            reader.chapter_breaks = not reader.chapter_breaks
            self.library.set_setting("chapter_breaks", reader.chapter_breaks)
            reader.reflow()
        elif result.startswith("width:"):
            reader.read_width = int(result.split(":")[1])
            self.library.set_setting("read_width", reader.read_width)
            reader.reflow()
        elif result.startswith("spacing:"):
            reader.paragraph_spacing = int(result.split(":")[1])
            self.library.set_setting("spacing", reader.paragraph_spacing)
            reader.reflow()
        else:
            self.apply_theme(result)

    def action_help(self):
        if self.unobstructed:
            self.push_screen(HelpModal())

    @on(Button.Pressed)
    async def button_action(self, event):
        if isinstance(self.screen, ModalScreen):
            return
        action = {
            "shelf-button": "shelf",
            "theme-cycle": "theme_cycle",
            "archive-book": "archive_book",
            "delete-book": "delete_book",
            "archive-view": "archive_view",
        }.get(event.button.id, event.button.id)
        if action:
            await self.run_action(action)
            if self.reading and self.unobstructed:
                self.query_one(Reader).focus()

    def on_resize(self, event):
        # App.size can still describe the previous screen while Resize is
        # dispatched; use the incoming terminal dimensions at breakpoints.
        self.set_class(event.size.width < 85, "compact")
        self.set_class(event.size.width < 60, "narrow")
        if self.is_mounted:
            self.sync_sidebar(event.size.width)

"""UI translations. Book text and cached source offsets never depend on language."""

from __future__ import annotations

import re
import json
import sqlite3

LANGUAGES = ("zh", "en")

# Chinese source strings are message IDs; templates format only named values.
ENGLISH = {
    "↑ ↓ 选择 · Enter 确认 · Esc 返回": "↑ ↓ Select · Enter Confirm · Esc Back",
    "返回  Esc": "Back  Esc",
    "把好书放进书架": "Add books to your shelf",
    "TXT · EPUB · PDF · Markdown  /  支持文件或文件夹路径": "TXT · EPUB · PDF · Markdown / File or folder paths",
    "粘贴路径，或从下方选择文件": "Paste a path, or choose a file below",
    "导入": "Import",
    "取消": "Cancel",
    "在本书中搜索": "Search this book",
    "输入文字，Enter 搜索 · ↓ 选择结果": "Type text · Enter Search · ↓ Select a result",
    "全文搜索 · 中文短语与标点均可检索": "Full-text search · Phrases and punctuation supported",
    "{p0}{p1} 个结果": "Results: {p0}{p1}",
    " · 显示前 200 个，请细化关键词": " · First 200 shown; refine your search",
    " · Enter 跳转": " · Enter Jump",
    "墨读 MODU · 让阅读安静下来": "MODU · A quiet place to read",
    "继续阅读  Esc": "Keep reading  Esc",
    "墨读 [bold]MODU[/]": "[bold]MODU[/]",
    "字里行间，自有天地": "A little room to read",
    "导入 i": "Import i",
    "主题 t": "Theme t",
    "帮助 ?": "Help ?",
    "[bold]我的书架[/]": "[bold]My bookshelf[/]",
    "一本书，一段属于自己的时间。": "A book. A little time of your own.",
    "按 i 导入本地书籍，或在终端输入 modu 文件路径\n支持 TXT、EPUB、PDF、Markdown · 所有内容只保存在本机": "Press i to import a local book, or run modu FILE\nTXT · EPUB · PDF · Markdown · Everything stays on your device",
    "↑ ↓ 选择  ·  Enter 打开  ·  i 导入  ·  q 退出": "↑ ↓ Select · Enter Open · i Import · l Language · q Quit",
    "‹ 书架": "‹ Shelf",
    "目录 c": "TOC c",
    "搜索 /": "Search /",
    "书签 m": "Marks m",
    "设置 s": "Settings s",
    "章节目录": "Contents",
    "Enter 跳转 · c 收起": "Enter Jump · c Hide",
    "书名": "Title",
    "作者": "Author",
    "格式": "Format",
    "进度": "Progress",
    "未读": "Unread",
    "{p0} 本藏书  ·  一本书，一段属于自己的时间。": "Books: {p0} · A little time of your own.",
    "正在打开书籍…": "Opening book…",
    "已回到上次阅读位置": "Resumed where you left off",
    "开始阅读": "Enjoy your book",
    "打开失败：{p0}": "Could not open book: {p0}",
    "当前 {p0}/{p1}  ·  本章 {p2:.0%}": "Ch. {p0}/{p1} · {p2:.0%}",
    "← → 翻页  ·  b 书签  ·  ? 帮助  ·  q 退出": "← → Page · b Mark · ? Help · q Quit",
    "{p0} / {p1} 页": "Page {p0} / {p1}",
    "页数暂不可用": "Pages unavailable",
    "页数计算中…": "Counting pages…",
    "文件夹中没有支持的书籍。": "No supported books found in this folder.",
    "正在导入 {p0}/{p1}：{p2}": "Importing {p0}/{p1}: {p2}",
    "已导入 {p0} 本 · 已有 {p1} 本": "Imported: {p0} · Already on shelf: {p1}",
    " · 失败 {p0} 本": " · Failed: {p0}",
    "部分文件未能导入": "Some files could not be imported",
    "已成功导入的书籍保留在书架中": "Successfully imported books remain on your shelf",
    "导入失败：{p0}": "Import failed: {p0}",
    "已添加书签  ·  m 查看": "Bookmark added · m View",
    "已取消书签": "Bookmark removed",
    "还没有书签  ·  按 b 添加当前位置": "No bookmarks yet · Press b to mark this position",
    "我的书签": "My bookmarks",
    "Enter 跳转 · 在原位置再次按 b 取消书签": "Enter Jump · Press b at the same position to remove",
    "主题  ·  ": "Theme · ",
    "段间留白  ·  舒展": "Paragraph spacing · Relaxed",
    "段间留白  ·  紧凑": "Paragraph spacing · Compact",
    "阅读设置": "Reading settings",
    "设置即时保存 · 字号请使用终端的字体缩放快捷键": "Saved immediately · Use your terminal shortcuts to change font size",
    "黑金 · 墨夜": "Ink night · Black & gold",
    "浅色 · 纸笺": "Paper · Light",
    "深色 · 远山": "Distant hills · Slate",
    "暖纸 · 旧书": "Old book · Sepia",
    "浅绿 · 竹影": "Bamboo · Light green",
    "雾灰 · 晨雾": "Morning mist · Light gray",
    "深灰 · 石墨": "Graphite · Dark gray",
    "暗绿 · 松夜": "Pine night · Dark green",
    "界面语言已切换为中文": "Interface language set to English",
    "正文": "Text",
    "语言 / Language": "Language / 语言",
    "正文宽度  ·  {cells} 列（约 {han} 个汉字）": "Text width · {cells} columns (~{han} CJK characters)",
    "离线阅读 · 字里行间": "Offline reading · A little room to read",
    "EN l": "中文 l",
    "墨读 MODU · 中文离线终端阅读器": "MODU · Offline terminal ebook reader",
    "导入并打开 TXT / EPUB / PDF / Markdown（支持文件夹）": "Import and open TXT / EPUB / PDF / Markdown (folders supported)",
    "独立书库目录，亦可设置 MODU_HOME": "Separate library directory; also settable with MODU_HOME",
    "打开书架，不自动续读": "Open the bookshelf without resuming",
    "导入后退出，不打开界面": "Import and exit without opening the interface",
    "列出书架并退出": "List books and exit",
    "界面语言，选择后自动保存": "Interface language; saved for this library",
    "已导入": "Imported",
    "已在书架": "Already on shelf",
    "请在交互式终端运行 modu；批量导入可使用 --import-only。\n": "Run modu in an interactive terminal; use --import-only for batch imports.\n",
    "保存阅读位置失败：": "Could not save reading position: ",
    "翻页   Space / → / PgDn       上一页   ← / PgUp / Backspace\n逐行   ↑ ↓ / j k             首尾     Home / End\n滚动   鼠标滚轮               进度     拖动右侧滚动条\n\n侧栏   c       全文搜索 /       书签     b 添加/取消 · m 查看\n章节   n 下一章 · p 上一章      书架     Esc\n主题   t       阅读设置 s       导入     i\n语言   l       退出 q / Ctrl+q              帮助 ?\n\n阅读位置自动保存；重启自动回到上次阅读。\n滚动条静止 2 秒后隐藏，鼠标靠近右缘再次显示。\n字号由终端控制；请使用终端的字体缩放快捷键。\nPDF 为文字重排，扫描 PDF 需先 OCR；EPUB 不支持 DRM。": "Next page   Space / → / PgDn   Back   ← / PgUp / Backspace\nLine        ↑ ↓ / j k         Start / End   Home / End\nScroll      Mouse wheel       Progress      Drag right scrollbar\n\nContents    c       Search /      Bookmarks   b Add/remove · m List\nChapter     n Next · p Previous   Bookshelf   Esc\nTheme       t       Settings s    Import      i\nLanguage    l       Quit q / Ctrl+q           Help ?\n\nYour position is saved automatically and restored on restart.\nThe scrollbar hides after 2 seconds; move near the right edge to show it.\nUse your terminal's font zoom shortcuts to change text size.\nPDF text is reflowed; scanned PDFs need OCR. DRM EPUBs are unsupported.",
    "书籍标识无效。": "Invalid book identifier.",
    "文件内容超过允许的大小。": "File content exceeds the size limit.",
    "缓存大小异常或已损坏。": "The cache is too large or corrupted.",
    "缓存含多余数据。": "The cache contains unexpected trailing data.",
    "文件夹中的书籍超过 1000 本，请分批导入。": "This folder contains more than 1,000 books; import in smaller batches.",
    "书籍解析超时，已停止解析进程。": "Book parsing timed out; the parser was stopped.",
    "无法解析书籍，或解析过程超过资源限制。": "Could not parse this book, or the parser exceeded its resource limit.",
    "书籍无法解析。": "Could not parse this book.",
    "书库子目录不能是符号链接。": "Library subdirectories cannot be symbolic links.",
    "书库索引不能是符号链接。": "The library index cannot be a symbolic link.",
    "请选择本地 TXT、EPUB、PDF 或 Markdown 文件。": "Choose a local TXT, EPUB, PDF, or Markdown file.",
    "单个文件不能超过 64 MB。": "A file cannot exceed 64 MB.",
    "缓存不能是符号链接。": "The cache cannot be a symbolic link.",
    "书籍不在书架中。": "This book is not on your shelf.",
    "书籍格式无效。": "Invalid book format.",
    "本地原书副本不存在或路径无效，请重新导入。": "The local book copy is missing or its path is invalid; import it again.",
    "无法识别文字编码；请先将文件另存为 UTF-8。": "Unknown text encoding; save the file as UTF-8 first.",
    "EPUB 包含非本地或无效的资源路径。": "The EPUB contains a non-local or invalid resource path.",
    "EPUB 资源路径超出书籍范围。": "An EPUB resource path points outside the book.",
    "EPUB 内容过大，请拆分后导入。": "This EPUB is too large; split it before importing.",
    "EPUB 包含重复资源名称。": "The EPUB contains duplicate resource names.",
    "EPUB 含过大或加密的资源。": "The EPUB contains oversized or encrypted resources.",
    "EPUB 内容超过解析限额。": "EPUB content exceeds the parsing limit.",
    "EPUB 缺少内容索引。": "The EPUB has no content index.",
    "EPUB 正文超过解析限额。": "EPUB text exceeds the parsing limit.",
    "PDF 已加密，请先导出可阅读的本地副本。": "This PDF is encrypted; export a readable local copy first.",
    "PDF 页数超过 2000 页，请拆分后导入。": "This PDF exceeds 2,000 pages; split it before importing.",
    "PDF 文字超过解析限额。": "PDF text exceeds the parsing limit.",
    "PDF 段落超过解析限额。": "PDF paragraphs exceed the parsing limit.",
    "PDF 使用文字重排模式；多栏与复杂表格的顺序取决于原文。": "PDF text is reflowed; column and table order depends on the original file.",
    "文件不存在或超过 64 MB。": "The file does not exist or exceeds 64 MB.",
    "正文超过 800 万字符，请拆分后导入。": "The book exceeds 8 million characters; split it before importing.",
    "EPUB 以文字阅读模式呈现；图片显示说明文字。": "EPUBs use text reading mode; images appear as captions.",
    "支持 TXT、EPUB、PDF 和 Markdown 文件。": "Supported formats: TXT, EPUB, PDF, and Markdown.",
    "没有可阅读文字。扫描版 PDF 需要先进行 OCR。": "No readable text found. Scanned PDFs need OCR first.",
    "正文超过解析限额。": "Book text exceeds the parsing limit.",
    "解析结果超过缓存限额。": "Parsed content exceeds the cache limit.",
    "缓存格式需要更新。": "The cache format needs updating.",
    "缓存段落无效。": "Invalid cached paragraphs.",
    "缓存内容无效。": "Invalid cached content.",
    "缓存内容过大。": "The cache is too large.",
    "缓存元数据无效。": "Invalid cache metadata.",
}


def normalize_language(value):
    return value if isinstance(value, str) and value in LANGUAGES else "zh"


def translate(language, text, **values):
    template = ENGLISH.get(text, text) if language == "en" else text
    return template.format(**values) if values else template


def message(language, text):
    """Translate known parser errors/warnings; leave user filenames and text alone."""
    if language == "en":
        match = re.fullmatch(r"(\d+) 页没有可提取文字；扫描页需要先进行 OCR。", text)
        if match:
            return f"Pages without extractable text: {match[1]}; scanned pages need OCR."
    return translate(language, text)


def saved_language(root):
    """Read CLI/help language without creating a library or importing the UI."""
    index = root / "library.sqlite3"
    if not index.is_file() or index.is_symlink():
        return "zh"
    try:
        connection = sqlite3.connect(index.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2)
        try:
            row = connection.execute("SELECT value FROM settings WHERE key='language'").fetchone()
            return normalize_language(json.loads(row[0])) if row else "zh"
        finally:
            connection.close()
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return "zh"

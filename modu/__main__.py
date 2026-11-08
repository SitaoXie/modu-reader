from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys
from . import __version__
from .model import clean
from .safety import import_paths
from .i18n import translate, normalize_language, message, saved_language


def main():
    # Discover the help language before argparse handles --help. This probe never
    # creates a library, and never mistakes --lang after -- for an option.
    probe = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    probe.add_argument("--lang", choices=("zh", "en"))
    probe.add_argument("--library", type=Path)
    early, _ = probe.parse_known_args()
    from .library import Library, DEFAULT_HOME

    root = early.library or Path(os.environ.get("MODU_HOME", DEFAULT_HOME))
    language = normalize_language(early.lang or saved_language(root))

    def tr(text):
        return translate(language, text)

    parser = argparse.ArgumentParser(
        prog="modu", description=tr("墨读 MODU · 中英文离线终端阅读器"), allow_abbrev=False
    )
    parser.add_argument(
        "files", nargs="*", help=tr("导入并打开 TXT / EPUB / PDF / Markdown（支持文件夹）")
    )
    parser.add_argument("--library", type=Path, help=tr("独立书库目录，亦可设置 MODU_HOME"))
    parser.add_argument("--shelf", action="store_true", help=tr("打开书架，不自动续读"))
    parser.add_argument("--import-only", action="store_true", help=tr("导入后退出，不打开界面"))
    parser.add_argument("--list", action="store_true", help=tr("列出书架并退出"))
    parser.add_argument("--version", action="version", version=f"MODU {__version__}")
    parser.add_argument("--lang", choices=("zh", "en"), help=tr("界面语言，选择后自动保存"))
    args = parser.parse_args()
    os.environ.setdefault("COLORTERM", "truecolor")
    os.environ.setdefault("TEXTUAL_COLOR_SYSTEM", "truecolor")
    os.environ.setdefault("TEXTUAL_SMOOTH_SCROLL", "0")
    try:
        library = Library(args.library or Path(os.environ.get("MODU_HOME", DEFAULT_HOME)))
    except (OSError, ValueError) as error:
        parser.exit(2, message(language, clean(str(error))) + "\n")
    language = normalize_language(args.lang or library.setting("language", "zh"))
    if args.lang:
        library.set_setting("language", language)
    target, failures = None, []
    if args.files:
        print(tr("导入会在书库创建独立副本。成功后，修改、移动或删除原文件均不影响阅读；不会自动同步。"))
        print(translate(language, "副本保存目录：{path}", path=clean(str(library.root / "originals"))))
    for raw in args.files:
        path = Path(raw).expanduser()
        try:
            files = import_paths(path)
        except (OSError, ValueError) as error:
            failures.append(message(language, clean(str(error))))
            continue
        if not files:
            failures.append(tr("文件夹中没有支持的书籍。"))
        for file in files:
            try:
                target, new = library.import_file(file)
                print(
                    f"{tr('已导入') if new else tr('已在书架')}: {clean(library.book(target)['title'])}"
                )
            except Exception as error:
                failures.append(clean(f"{file.name}: {message(language, str(error))}"))
    for error in failures:
        print(translate(language, "导入失败：{p0}", p0=error), file=sys.stderr)
    if args.list:
        for book in library.books():
            print(
                f"{clean(book['title'])}\t{clean(book['format'])}\t{book['position'] / max(1, book['chars']):.1%}"
            )
        return
    if args.import_only:
        if failures:
            raise SystemExit(1)
        return
    if not sys.stdout.isatty():
        parser.exit(2, tr("请在交互式终端运行 modu；批量导入可使用 --import-only。\n"))
    from .app import ModuApp

    app = ModuApp(library, start_book=target, shelf=args.shelf)
    try:
        app.run()
    finally:
        # Textual handles Ctrl-C / termination; normal exit always flushes.
        if app.book_id:
            try:
                app.flush_position(force=True)
            except Exception as error:
                print(
                    tr("保存阅读位置失败：") + message(language, clean(str(error)))[:500],
                    file=sys.stderr,
                )


if __name__ == "__main__":
    main()

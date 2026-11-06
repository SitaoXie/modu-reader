"""Independent real-PTY language/paging acceptance using an original project story.

Requires pexpect and pyte on POSIX. No Textual internals or diagnostic subclass.
All temporary data and failure frames stay in the explicit --work directory.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import zlib

import pexpect
import pyte


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--command", help="Installed modu launcher to test instead of python -m modu"
    )
    parser.add_argument(
        "--book", type=Path, help="Local book to verify (use a new isolated work directory)"
    )
    parser.add_argument("--columns", type=int, default=84, help="Starting terminal width")
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    library = work / "library"
    if library.exists():
        parser.error("Use a new --work directory so previous reading state cannot affect results")
    command = [args.command] if args.command else [args.python, "-m", "modu"]
    book = (
        args.book.resolve()
        if args.book
        else Path(__file__).resolve().parents[1] / "examples" / "first-pages.txt"
    )
    env = os.environ.copy()
    env.update(TERM="xterm-256color", COLORTERM="truecolor", PYTHONUTF8="1")
    env.pop("NO_COLOR", None)
    env.pop("MODU_TEST_TRACE", None)
    subprocess.run(
        command + ["--library", str(library), "--import-only", str(book)],
        env=env,
        check=True,
        capture_output=True,
    )
    document = json.loads(zlib.decompress(next((library / "cache").glob("*.json.z")).read_bytes()))

    def normalize(text):
        return re.sub(r"\s+", "", text.replace("\u2060", ""))

    wanted = normalize("\n\n".join(block[0] for block in document["blocks"]))
    screen = pyte.Screen(args.columns, 36)
    stream = pyte.Stream(screen)
    child = None

    def launch(*flags):
        return pexpect.spawn(
            command[0],
            command[1:] + ["--library", str(library), *flags],
            env=env,
            encoding="utf-8",
            dimensions=(36, args.columns),
            timeout=6,
        )

    def drain(seconds=0.05):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            try:
                # pyte cannot decode U+2060. Actual PTY bytes are unchanged.
                stream.feed(child.read_nonblocking(262144, timeout=0.01).replace("\u2060", ""))
            except pexpect.TIMEOUT:
                pass

    def lines():
        # Read cells directly: pyte.display indexes char[0] on empty wide-cell
        # continuations during partial CJK redraws. Empty continuations carry no
        # source text. Paging comparisons below already use the same cell grid.
        return [
            "".join(screen.buffer[y][x].data for x in range(screen.columns))
            for y in range(screen.lines)
        ]

    def pages(language="en"):
        line = lines()[-1]
        pattern = r"Page\s+(\d+)\s*/\s*(\d+)" if language == "en" else r"(\d+)\s*/\s*(\d+)\s*页"
        match = re.search(pattern, line)
        return tuple(map(int, match.groups())) if match else None

    def wait(predicate):
        until = time.monotonic() + 9
        while time.monotonic() < until:
            drain()
            if predicate():
                drain()
                return
        raise AssertionError("Timed out waiting for a terminal frame")

    def body():
        left = 26 if screen.columns >= 70 else 0
        return normalize(
            "".join(
                screen.buffer[y][x].data
                for y in range(8, screen.lines - 3)
                for x in range(left, screen.columns - 2)
            )
        )

    def has(text):
        return text in "\n".join(lines())

    try:
        child = launch("--lang", "en", str(book))
        wait(lambda: pages() is not None)
        assert has("Search /")
        if args.columns >= 70:
            assert has("Contents")
        cursor, count, switches = 0, 0, 0
        starts = []
        while True:
            current, total = pages()
            observed = body()
            assert observed and wanted[cursor : cursor + len(observed)] == observed, (
                "Page overlap or gap"
            )
            starts.append(cursor)
            child.send("l")
            drain(0.3)
            wait(lambda: pages("zh") is not None)
            assert pages("zh") == (current, total) and body() == observed
            child.send("l")
            drain(0.3)
            wait(lambda: pages() is not None)
            assert pages() == (current, total) and body() == observed
            switches += 2
            cursor += len(observed)
            count += 1
            if current == total:
                break
            child.send(" ")
            wait(lambda: pages() and pages()[0] == current + 1)
        assert cursor == len(wanted)
        child.send(" ")
        drain(0.2)
        assert body() == observed  # No EOF overlap.
        for key, title in [
            ("?", "MODU · A quiet place to read"),
            ("i", "Add books to your shelf"),
            ("s", "Reading settings"),
            ("/", "Search this book"),
        ]:
            child.send(key)
            wait(lambda: has(title))
            if key == "/":
                child.send("l")
                drain(0.3)
                assert has(title)  # Search input must consume l.
            child.send("\x1b")
            wait(lambda: not has(title))
        wait(lambda: pages() is not None)
        backgrounds = [
            "f5f1e8",
            "19232e",
            "f1e5cf",
            "e6eedf",
            "e8eaed",
            "202224",
            "17231f",
            "121416",
        ]
        for color in backgrounds:
            child.send("t")
            wait(lambda: screen.buffer[8][30].bg == color)
        child.send("\x1b[H")
        wait(lambda: pages() and pages()[0] == 1)
        child.send(" ")
        wait(lambda: pages() and pages()[0] == 2)
        start = starts[1]
        resizes = [
            (42, 24),
            (59, 28),
            (60, 28),
            (69, 30),
            (70, 30),
            (84, 36),
            (85, 36),
            (110, 42),
            (84, 36),
        ] * 2
        for columns, rows in resizes:
            screen.resize(lines=rows, columns=columns)
            child.setwinsize(rows, columns)
            drain(0.5)
            assert wanted[start : start + len(body())] == body(), "Resize changed first character"
            assert pages() is not None
            if columns >= 85:
                assert "Settings s" in lines()[4]
                assert "Settings" not in lines()[3] + lines()[5]
                child.send("l")
                drain(0.3)
                wait(lambda: pages("zh") is not None)
                assert "设置 s" in lines()[4]
                child.send("l")
                drain(0.3)
                wait(lambda: pages() is not None)
                assert "Settings s" in lines()[4]
                assert "Settings" not in lines()[3] + lines()[5]
                assert wanted[start : start + len(body())] == body()
                switches += 2
        child.send("q")
        child.expect(pexpect.EOF)
        child.close()
        assert child.exitstatus == 0
        with sqlite3.connect(library / "library.sqlite3") as db:
            saved = db.execute("SELECT position FROM books").fetchone()[0]
            assert (
                json.loads(
                    db.execute("SELECT value FROM settings WHERE key='language'").fetchone()[0]
                )
                == "en"
            )
        screen = pyte.Screen(args.columns, 36)
        stream = pyte.Stream(screen)
        child = launch()  # No --lang: language and source anchor must persist.
        wait(lambda: pages() is not None)
        assert wanted[start : start + len(body())] == body()
        child.send("q")
        child.expect(pexpect.EOF)
        child.close()
        assert child.exitstatus == 0
        with sqlite3.connect(library / "library.sqlite3") as db:
            assert db.execute("SELECT position FROM books").fetchone()[0] == saved
        result = dict(
            status="PASS",
            transport="real PTY, independent ANSI decoder",
            pages=count,
            non_whitespace_characters=len(wanted),
            duplicate_characters=0,
            skipped_characters=0,
            language_switches=switches,
            english_dialogs=4,
            settings_button_single_line=True,
            themes=8,
            resizes=len(resizes),
            language_persistence=True,
            resume=True,
        )
        (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    except Exception:
        (work / "failure-screen.txt").write_text("\n".join(lines()), encoding="utf-8")
        raise
    finally:
        if child is not None and child.isalive():
            child.close(force=True)


if __name__ == "__main__":
    main()

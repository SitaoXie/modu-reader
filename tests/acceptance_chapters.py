"""Real CLI PTY chapter-break acceptance, decoded without importing MODU internals."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

import pexpect
import pyte


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--command")
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    library = work / "library"
    book = work / "chapters.md"
    chapters = [
        ("First 小窗", "Short chapter. 短章，完整。"),
        ("Second 长路", "The rain has stopped. “雨停了，”她说。 " * 90),
        ("Third 灯火", "A final light. 末尾的一盏灯。"),
        ("Fourth 归途", "Good night. 晚安。"),
    ]
    book.write_text("\n\n".join(f"# {title}\n\n{body}" for title, body in chapters))

    def normalize(value):
        return re.sub(r"\s+", "", value.replace("\u2060", ""))

    pieces = [normalize(title + body) for title, body in chapters]
    wanted = "".join(pieces)
    boundaries = [0]
    for piece in pieces:
        boundaries.append(boundaries[-1] + len(piece))
    command = [args.command] if args.command else [args.python, "-m", "modu"]
    env = os.environ.copy()
    env.update(TERM="xterm-256color", COLORTERM="truecolor", PYTHONUTF8="1")
    env.pop("NO_COLOR", None)
    env.pop("MODU_TEST_TRACE", None)
    screen, stream, child = None, None, None

    def launch():
        nonlocal screen, stream, child
        screen = pyte.Screen(84, 36)
        stream = pyte.Stream(screen)
        child = pexpect.spawn(
            command[0],
            command[1:] + ["--library", str(library), "--lang", "en", str(book)],
            env=env,
            encoding="utf-8",
            dimensions=(36, 84),
            timeout=6,
        )

    def drain(seconds=0.05):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            try:
                stream.feed(child.read_nonblocking(262144, timeout=0.01).replace("\u2060", ""))
            except pexpect.TIMEOUT:
                pass

    def lines():
        return [
            "".join(screen.buffer[y][x].data for x in range(screen.columns))
            for y in range(screen.lines)
        ]

    def pages():
        match = re.search(r"Page\s+(\d+)\s*/\s*(\d+)", lines()[-1])
        return tuple(map(int, match.groups())) if match else None

    def body():
        left = 26 if screen.columns >= 70 else 0
        return normalize(
            "".join(
                screen.buffer[y][x].data
                for y in range(8, screen.lines - 3)
                for x in range(left, screen.columns - 2)
            )
        )

    def wait(predicate):
        until = time.monotonic() + 8
        while time.monotonic() < until:
            drain()
            if predicate():
                drain()
                return
        raise AssertionError("Timed out waiting for chapter frame")

    def has(text):
        return text in "\n".join(lines())

    def setting(expected, toggle=False):
        child.send("s")
        wait(lambda: has("Reading settings"))
        assert has(f"New page per chapter · {expected}")
        child.send("\r" if toggle else "\x1b")
        wait(lambda: not has("Reading settings") and pages() is not None)

    def quit_app():
        child.send("q")
        child.expect(pexpect.EOF)
        child.close()
        assert child.exitstatus == 0

    try:
        launch()
        wait(lambda: pages() is not None)
        setting("On")
        cursor, count = 0, 0
        while True:
            current, total = pages()
            observed = body()
            assert observed and wanted[cursor : cursor + len(observed)] == observed
            next_boundary = next(b for b in boundaries if b > cursor)
            assert cursor + len(observed) <= next_boundary, "Chapter starts within previous page"
            if cursor in boundaries[:-1]:
                title = chapters[boundaries.index(cursor)][0]
                assert observed.startswith(normalize(title))
            cursor += len(observed)
            count += 1
            if current == total:
                break
            child.send(" ")
            wait(lambda: pages() and pages()[0] == current + 1)
        assert cursor == len(wanted) and count == total
        child.send("\x1b[H")
        wait(lambda: pages() and pages()[0] == 1)
        assert body() == pieces[0]
        for columns in (42, 59, 70, 84, 110):
            screen.resize(lines=36, columns=columns)
            child.setwinsize(36, columns)
            drain(0.5)
            setting("On")  # The complete setting must fit on one physical line.
            assert body() == pieces[0]
        setting("On", toggle=True)
        assert body().startswith(pieces[0] + normalize(chapters[1][0]))
        quit_app()
        with sqlite3.connect(library / "library.sqlite3") as db:
            assert (
                json.loads(
                    db.execute("SELECT value FROM settings WHERE key='chapter_breaks'").fetchone()[
                        0
                    ]
                )
                is False
            )
        launch()
        wait(lambda: pages() is not None)
        setting("Off")
        assert body().startswith(pieces[0] + normalize(chapters[1][0]))
        setting("Off", toggle=True)
        assert body() == pieces[0]
        child.send(" ")
        wait(lambda: pages() and pages()[0] == 2)
        resumed_body = body()
        quit_app()
        launch()
        wait(lambda: pages() is not None)
        assert body() == resumed_body and pages()[0] == 2
        setting("On")
        quit_app()
        result = dict(
            status="PASS",
            transport="real CLI PTY, independent ANSI decoder",
            chapters=4,
            pages=count,
            non_whitespace_characters=len(wanted),
            duplicate_characters=0,
            skipped_characters=0,
            default_on=True,
            each_chapter_starts_at_top=True,
            settings_widths=[42, 59, 70, 84, 110],
            toggle_persistence=True,
            resume=True,
        )
        (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    except Exception:
        if screen:
            (work / "failure-screen.txt").write_text("\n".join(lines()))
        raise
    finally:
        if child is not None and child.isalive():
            child.close(force=True)


if __name__ == "__main__":
    main()

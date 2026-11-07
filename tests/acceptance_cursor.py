"""Real CLI PTY regression for terminals that lose DECTCEM state on focus changes.

Only the independent terminal decoder receives the simulated host cursor reset.
The app receives normal FocusIn/FocusOut input bytes, or no event for the fallback.
Raw captures stay in the explicit isolated --work directory, never in releases.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pexpect
import pyte


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    book = Path(__file__).resolve().parents[1] / "examples/first-pages.en.txt"
    env = os.environ.copy()
    env.update(TERM="xterm-256color", COLORTERM="truecolor", HOME=str(work))
    env.pop("NO_COLOR", None)
    env.pop("MODU_HOME", None)
    env.pop("MODU_TEST_TRACE", None)
    command = [args.python, "-m", "modu", "--library", str(work / "library"), "--lang", "en"]
    subprocess.run(command + ["--import-only", str(book)], env=env, check=True, capture_output=True)
    screen = pyte.Screen(110, 36)
    stream = pyte.Stream(screen)
    frames = []
    chunks = []
    child = pexpect.spawn(
        command[0], command[1:] + [str(book)], env=env, encoding="utf-8", dimensions=(36, 110)
    )

    def drain(seconds=0.05):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            try:
                data = child.read_nonblocking(262144, timeout=0.01)
                chunks.append(data)
                stream.feed(data.replace("\u2060", ""))
            except pexpect.TIMEOUT:
                pass

    def text():
        return "\n".join(
            "".join(screen.buffer[y][x].data for x in range(screen.columns))
            for y in range(screen.lines)
        )

    def wait(predicate, timeout=5):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            drain()
            if predicate():
                return
        raise AssertionError("Terminal state did not recover")

    recoveries = []

    def reset_and_recover(phase, event=""):
        drain(0.06)
        before = len(chunks)
        # Model the host making its native cursor visible independently of the app.
        stream.feed("\x1b[?25h")
        assert not screen.cursor.hidden
        started = time.monotonic()
        if event:
            child.send(event)
        wait(lambda: screen.cursor.hidden, timeout=1.3)
        elapsed = time.monotonic() - started
        recoveries.append(elapsed)
        frames.append({"phase": phase, "reset": True, "ansi": "".join(chunks[before:])})

    try:
        wait(lambda: "Page 1 /" in text())
        drain(0.3)
        assert screen.cursor.hidden
        frames.append({"phase": "startup", "reset": False, "ansi": "".join(chunks)})
        for cycle in range(12):
            reset_and_recover(f"blur-{cycle}", "\x1b[O")
            reset_and_recover(f"focus-{cycle}", "\x1b[I")
            assert "Page 1 /" in text(), "Focus switch moved the reading position"
        for cycle in range(3):
            reset_and_recover(f"missing-event-{cycle}")
        for key, title in [("/", "Search this book"), ("i", "Add books to your shelf")]:
            child.send(key)
            wait(lambda: title in text())
            reset_and_recover(f"{key}-blur", "\x1b[O")
            reset_and_recover(f"{key}-focus", "\x1b[I")
            child.send("preview-note")
            wait(lambda: "preview-note" in text())
            # Textual draws its own input caret; the native terminal cursor stays hidden.
            assert screen.cursor.hidden
            drain(0.6)
            frames.append({"phase": "input", "reset": False, "ansi": "".join(chunks)})
            child.send("\x1b")
            wait(lambda: title not in text())
        child.send("q")
        child.expect(pexpect.EOF)
        tail = child.before
        stream.feed(tail.replace("\u2060", ""))
        assert not screen.cursor.hidden, "Shell cursor must be restored on exit"
        child.close()
        assert child.exitstatus == 0
        result = {
            "status": "PASS",
            "transport": "real CLI PTY, independent cursor-state decoder",
            "focus_cycles": 12,
            "missing_event_recoveries": 3,
            "input_dialogs": 2,
            "max_recovery_seconds": round(max(recoveries), 3),
            "reading_position_unchanged": True,
            "shell_cursor_restored": True,
            "scope": "Simulated host cursor reset; native host window not automated",
        }
        (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    finally:
        (work / "frames.json").write_text(json.dumps(frames, ensure_ascii=False))
        if child.isalive():
            child.close(force=True)


if __name__ == "__main__":
    main()

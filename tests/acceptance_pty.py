"""Black-box tmux acceptance: actual ANSI PTY output, isolated library, no web UI.
Run: python tests/acceptance_pty.py /path/to/book.txt --work /absolute/test/folder
"""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shlex
import statistics
import subprocess
import shutil
import sys
import time
import zlib
import unicodedata

p = argparse.ArgumentParser()
p.add_argument("book", type=Path)
p.add_argument("--work", type=Path, required=True)
p.add_argument("--query", default="灯塔", help="A phrase present in the test book")
args = p.parse_args()
ROOT = args.work.resolve()
ROOT.mkdir(parents=True, exist_ok=True)
TRACE = ROOT / "state.json"
LIB = ROOT / "library"
SOCKET = f"modu-test-{os.getpid()}"
TMUX = shutil.which("tmux")
SESSION = "reader"
if TMUX is None:
    raise SystemExit("Install tmux and make it available on PATH to run this POSIX-only test.")


def tmux(*args, check=True):
    return subprocess.run(
        [TMUX, "-L", SOCKET, *map(str, args)], check=check, capture_output=True, text=True
    ).stdout


def state():
    try:
        return json.loads(TRACE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def wait(predicate, timeout=6):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        value = state()
        if value and predicate(value):
            return value
        if tmux("display-message", "-p", "-t", SESSION, "#{pane_dead}", check=False).strip() == "1":
            raise AssertionError("Reader crashed:\n" + tmux("capture-pane", "-p", "-t", SESSION))
        time.sleep(0.008)
    raise AssertionError(
        "Timed out: " + str(state())[:500] + "\n" + tmux("capture-pane", "-p", "-t", SESSION)
    )


def key(*keys):
    tmux("send-keys", "-t", SESSION, *keys)


def capture():
    # U+2060 is a zero-cell output guard, not source text.
    return tmux("capture-pane", "-p", "-N", "-t", SESSION).replace("\u2060", "")


def cell_slice(text, left, right):
    pos = 0
    out = []
    for char in text:
        width = (
            0
            if unicodedata.combining(char)
            else 2
            if unicodedata.east_asian_width(char) in "WF"
            else 1
        )
        if left <= pos < right:
            out.append(char)
        pos += width
    return "".join(out)


def match_frame(s):
    """Compare external terminal cells to independent source slices, not a screenshot API."""
    expected = [row[2].rstrip() for row in s["rows"] if row[2].strip()]
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        frame = capture()
        if all(text in frame for text in expected):
            screen_rows = frame.splitlines()
            margin = max(1, (s["size"][0] - s["width"]) // 2)
            body_x, body_origin, body_width, _ = s["region"]
            for y in range(s["size"][1]):
                row_index = y - 1
                expected_line = (
                    (" " * margin + s["rows"][row_index][2]).rstrip()
                    if 0 <= row_index < len(s["rows"])
                    else ""
                )
                actual_line = cell_slice(
                    screen_rows[body_origin + y], body_x, body_x + body_width
                ).rstrip()
                assert actual_line == expected_line, (
                    "Residual or misplaced text",
                    y,
                    repr(actual_line),
                    repr(expected_line),
                )
            for a, b, text, kind in s["rows"]:
                assert doc_text[a:b] == text, (a, b, kind)
            assert "\ufffd" not in frame
            assert "Traceback" not in frame
            return frame
        time.sleep(0.008)
    raise AssertionError(
        "Rendered frame differs from source\n" + frame + "\nEXPECTED " + repr(expected)
    )


env = os.environ.copy()
env.pop("NO_COLOR", None)
env.update(COLORTERM="truecolor", TERM="xterm-256color")
command = shlex.join(
    [
        sys.executable,
        str(Path(__file__).with_name("pty_driver.py")),
        "--library",
        str(LIB),
        str(args.book.resolve()),
    ]
)
# Trace is strictly local, opt-in and only enabled for the isolated acceptance library.
command = "env MODU_TEST_TRACE=" + shlex.quote(str(TRACE)) + " " + command
try:
    subprocess.run(
        [TMUX, "-L", SOCKET, "new-session", "-d", "-x", "110", "-y", "36", "-s", SESSION, command],
        env=env,
        check=True,
    )
    tmux("set-option", "-t", SESSION, "status", "off")
    tmux("set-option", "-t", SESSION, "remain-on-exit", "on")
    tmux("set-window-option", "-t", SESSION, "window-size", "manual")
    s = wait(lambda x: x["reading"] and x["terminal_size"][0] == 110)
    book_cache = next((LIB / "cache").glob("*.json.z"))
    book = json.loads(zlib.decompress(book_cache.read_bytes()))
    doc_text = "\n\n".join(b[0] for b in book["blocks"])
    # Start from source offset zero even on a rerun.
    key("Home")
    s = wait(lambda x: x["anchor"] == 0)
    time.sleep(2.3)
    s = state()
    match_frame(s)
    frames = ROOT / "frames"
    frames.mkdir(exist_ok=True)
    (frames / "gold.txt").write_text(capture(), encoding="utf-8")
    colored = tmux("capture-pane", "-p", "-e", "-N", "-t", SESSION)
    assert "\x1b[38;2;" in colored or ";38;2;" in colored, "Missing RGB truecolor escapes"
    (frames / "gold.ansi").write_text(colored, encoding="utf-8")
    covered = bytearray(len(doc_text))
    pages = 0
    repeated = set()
    latencies = []
    while True:
        frame = match_frame(s)
        for a, b, text, kind in s["rows"]:
            repeated.update(i for i in range(a, b) if covered[i] and not doc_text[i].isspace())
            covered[a:b] = b"\1" * (b - a)
        old = s["anchor"]
        t = time.perf_counter()
        key("Space")
        # End is the last source line; cannot advance further.
        if s["rows"][-1][1] >= len(doc_text):
            break
        s = wait(lambda x: x["anchor"] != old)
        latencies.append((time.perf_counter() - t) * 1000)
        pages += 1
        if pages % 50 == 0:
            print(f"{pages} actual terminal pages checked", flush=True)
        assert pages < 3000
    missing = [i for i, c in enumerate(doc_text) if not c.isspace() and not covered[i]]
    assert not repeated, f"{len(repeated)} repeated source characters"
    assert not missing, f"{len(missing)} skipped characters, first {missing[:5]}"
    print(f"Full-book coverage PASS: {pages + 1} pages, {len(doc_text)} characters", flush=True)
    # Reverse paging and resize from the middle, with no accumulated anchor drift.
    key("Home")
    wait(lambda x: x["anchor"] == 0)
    for _ in range(min(35, max(1, pages // 2))):
        old = state()["anchor"]
        key("Space")
        wait(lambda x: x["anchor"] != old)
    s = state()
    anchor = s["anchor"]
    resize_count = 0
    for cols, rows in [(72, 26), (132, 42), (45, 18), (80, 24), (110, 36)] * 5:
        tmux("resize-window", "-t", SESSION, "-x", cols, "-y", rows)
        s = wait(lambda x: x["terminal_size"] == [cols, rows])
        assert s["anchor"] == anchor, "Resize moved original source anchor"
        assert s["rows"][0][0] <= anchor <= s["rows"][0][1]
        match_frame(s)
        resize_count += 1
    (frames / "resized.txt").write_text(capture(), encoding="utf-8")
    for theme in [
        "modu-paper",
        "modu-slate",
        "modu-sepia",
        "modu-bamboo",
        "modu-mist",
        "modu-graphite",
        "modu-pine",
        "modu-gold",
    ]:
        key("t")
        s = wait(lambda x: x["theme"] == theme)
        time.sleep(0.08)
        assert s["anchor"] == anchor
        match_frame(s)
        (frames / (theme + ".ansi")).write_text(
            tmux("capture-pane", "-p", "-e", "-N", "-t", SESSION), encoding="utf-8"
        )
    # Mouse protocols go through Textual's actual terminal input parser.
    old = state()["anchor"]
    key("-l", "\x1b[<65;50;15M")  # SGR wheel down
    s = wait(lambda x: x["anchor"] > old)
    match_frame(s)
    assert s["scrollbar"]
    rail_x = s["rail_region"][0] + 1
    key("-l", f"\x1b[<0;{rail_x};12M", f"\x1b[<32;{rail_x};24M", f"\x1b[<0;{rail_x};24m")
    s = wait(lambda x: x["anchor"] > len(doc_text) * 0.5)
    match_frame(s)
    anchor = s["anchor"]
    assert s["scrollbar"]
    hide_start = time.monotonic()
    wait(lambda x: not x["scrollbar"], timeout=3)
    hide_delay = time.monotonic() - hide_start
    # Bookmarks, directory and search via real keyboard, including literal Chinese input.
    key("b")
    time.sleep(0.2)
    key("m")
    wait(lambda x: x["modal"] == "ChoiceModal")
    time.sleep(0.2)
    assert "我的书签" in capture()
    key("Enter")
    wait(lambda x: x["modal"] != "ChoiceModal")
    assert state()["sidebar_visible"] and "章节目录" in capture()
    key("c")
    wait(lambda x: not x["sidebar_visible"])
    time.sleep(0.1)
    assert state()["anchor"] == anchor
    key("c")
    wait(lambda x: x["sidebar_visible"])
    time.sleep(0.1)
    assert "章节目录" in capture()
    key("/")
    wait(lambda x: x["modal"] == "SearchModal")
    key("-l", args.query)
    time.sleep(0.5)
    (frames / "search.txt").write_text(capture(), encoding="utf-8")
    assert "个结果" in capture()
    key("Enter")
    time.sleep(0.1)
    key("Enter")
    s = wait(lambda x: x["modal"] != "SearchModal")
    match_frame(s)
    # Save and resume after process exit in a differently sized terminal.
    for _ in range(4):
        old = s["anchor"]
        key("Space")
        s = wait(lambda x: x["anchor"] != old)
    anchor = s["anchor"]
    key("q")
    deadline = time.monotonic() + 3
    while tmux("display-message", "-p", "-t", SESSION, "#{pane_dead}").strip() != "1":
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert tmux("display-message", "-p", "-t", SESSION, "#{pane_dead_status}").strip() == "0"
    TRACE.unlink(missing_ok=True)
    tmux("resize-window", "-t", SESSION, "-x", "82", "-y", "28")
    resume = shlex.join(
        [sys.executable, str(Path(__file__).with_name("pty_driver.py")), "--library", str(LIB)]
    )
    tmux(
        "respawn-pane",
        "-k",
        "-t",
        SESSION,
        "env MODU_TEST_TRACE=" + shlex.quote(str(TRACE)) + " " + resume,
    )
    s = wait(lambda x: x["reading"] and x["terminal_size"][0] == 82)
    assert s["anchor"] == anchor
    match_frame(s)
    (frames / "resume.txt").write_text(capture(), encoding="utf-8")
    key("q")
    time.sleep(0.2)
    result = {
        "status": "PASS",
        "book": book["title"],
        "source_chars": len(doc_text),
        "chapters": sum(b[1] == "heading" for b in book["blocks"]),
        "actual_terminal_pages": pages + 1,
        "resize_cycles": resize_count,
        "themes": 8,
        "source_characters_repeated": len(repeated),
        "source_characters_skipped": len(missing),
        "wheel": "PASS",
        "scrollbar_drag": "PASS",
        "scrollbar_hide_seconds": round(hide_delay, 3),
        "search": "PASS",
        "bookmarks": "PASS",
        "toc_sidebar": "PASS",
        "exit_resume": "PASS",
        "observed_page_to_state_p50_ms": round(statistics.median(latencies), 2),
        "observed_page_to_state_p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 2),
        "notes": "Latency includes tmux subprocess + diagnostic polling. Source coverage excludes whitespace separators only.",
    }
    (ROOT / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
finally:
    tmux("kill-server", check=False)

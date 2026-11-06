"""Actual PTY -> independent ANSI decoder, exercising rail with CJK punctuation.
Run with pexpect and pyte installed; --python may point at the installed MODU env.
"""

import argparse
import json
import os
import time
from pathlib import Path
import pexpect
import pyte
from terminal_widths import WidthVariantScreen

p = argparse.ArgumentParser()
p.add_argument("--python", required=True)
p.add_argument("--work", type=Path, required=True)
p.add_argument(
    "--capture-frames",
    action="store_true",
    help="Save original-fixture ANSI frames for pixel regression",
)
p.add_argument(
    "--width-model",
    choices=["standard", "narrow-punctuation", "wide-ambiguous"],
    default="standard",
)
a = p.parse_args()
root = a.work.resolve()
root.mkdir(parents=True, exist_ok=True)
trace = root / "state.json"
source = root / "标点滚动回归.txt"
punctuation = [
    "，。！？；：、（）《》【】",
    "“中文引号”与‘单引号’……——·",
    "，" * 24,
    "“”" * 20,
    "「中文」『排版』百分比１００％",
    "普通文字，收尾。",
]
source.write_text("\n".join("第一章 标点\n" + s * 4 for s in punctuation) * 100, encoding="utf-8")
env = os.environ.copy()
env.pop("NO_COLOR", None)
env.update(TERM="xterm-256color", COLORTERM="truecolor", MODU_TEST_TRACE=str(trace))
child = pexpect.spawn(
    a.python,
    [
        str(Path(__file__).with_name("pty_driver.py")),
        "--library",
        str(root / "library"),
        str(source),
    ],
    env=env,
    encoding="utf-8",
    dimensions=(36, 110),
    timeout=3,
)
screen = WidthVariantScreen(110, 36, a.width_model)
stream = pyte.Stream(screen)
raw = []


def drain(duration=0.06):
    end = time.monotonic() + duration
    while time.monotonic() < end:
        try:
            data = child.read_nonblocking(131072, timeout=0.008)
            raw.append(data)
            stream.feed(data)
        except pexpect.TIMEOUT:
            pass


def state():
    try:
        return json.loads(trace.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def wait(pred, timeout=4):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        drain(0.02)
        s = state()
        if s and pred(s):
            drain(0.04)
            # Idle hiding can happen while draining terminal bytes. Compare to
            # the refreshed snapshot, not the visibility captured before drain.
            latest = state()
            if latest and pred(latest):
                return latest
    raise AssertionError("PTY state timeout " + str(state())[:300])


colors = {
    "modu-gold": ("121416", "252a2d", "d4b477"),
    "modu-paper": ("f5f1e8", "e8e0d2", "85632e"),
    "modu-slate": ("19232e", "273544", "91bfc3"),
    "modu-sepia": ("f1e5cf", "e4d5ba", "825a32"),
    "modu-bamboo": ("e6eedf", "d5e1ce", "41674d"),
    "modu-mist": ("e8eaed", "dadfe5", "525e6e"),
    "modu-graphite": ("202224", "2b2e31", "b8ac91"),
    "modu-pine": ("17231f", "24352c", "a3ba94"),
}
checks = 0
cells = 0
frames = []
frame_cursor = 0


def check_rail(s):
    global checks, cells, frame_cursor
    if a.capture_frames:
        frames.append({"state": s, "ansi": "".join(raw[frame_cursor:])})
        frame_cursor = len(raw)
    x, y, w, h = s["rail_region"]
    base, track, thumb = colors[s["theme"]]
    for row in range(y, y + h):
        # Every rail cell is an ASCII space, not a font-dependent line character.
        assert screen.buffer[row][x].data == " ", (row, x, screen.buffer[row][x])
        assert screen.buffer[row][x].bg in {base, track, thumb}, (row, x, screen.buffer[row][x])
        assert screen.buffer[row][x + 1].bg == base, (row, x + 1, screen.buffer[row][x + 1])
        gutter = x - 1 if x else x + w
        assert screen.buffer[row][gutter].bg == base, (
            "Ghost track in content gutter",
            row,
            gutter,
            screen.buffer[row][gutter],
        )
        cells += 3
    if s["scrollbar"]:
        railcolors = {screen.buffer[row][x].bg for row in range(y + 1, y + h - 1)}
        assert thumb in railcolors, railcolors
    else:
        assert all(screen.buffer[row][x].bg == base for row in range(y, y + h))
    checks += 1


try:
    s = wait(lambda s: s["reading"])
    drain(0.2)
    child.send("n")
    wait(lambda s: s["anchor"] > 0)
    for i in range(120):
        old = state()["anchor"]
        # Large downward traversal followed by upward traversal, varying punctuation.
        code = 65 if i < 70 or i >= 110 else 64
        child.send(f"\x1b[<{code};80;18M")
        s = wait(lambda s: s["anchor"] != old)
        check_rail(s)
        if i in (29, 59, 89):
            oldtheme = s["theme"]
            child.send("t")
            s = wait(lambda s: s["theme"] != oldtheme)
            check_rail(s)
    # Complete a cycle through all eight light/dark palettes.
    for _ in range(len(colors) - 3):
        oldtheme = s["theme"]
        child.send("t")
        s = wait(lambda s: s["theme"] != oldtheme)
        check_rail(s)
    # Resize in both directions; replay the real output into matching terminal cells.
    anchor = s["anchor"]
    for cols, rows in [(84, 42), (72, 26), (132, 42), (69, 18), (70, 24), (45, 18), (110, 36)] * 3:
        screen.resize(lines=rows, columns=cols)
        child.setwinsize(rows, cols)
        s = wait(lambda s: s["terminal_size"] == [cols, rows])
        assert s["anchor"] == anchor
        check_rail(s)
    # Show the rail, then verify every cell is restored after idle (no ghost rail).
    child.send("\x1b[<65;80;18M")
    s = wait(lambda s: s["anchor"] != anchor)
    check_rail(s)
    s = wait(lambda s: not s["scrollbar"], timeout=3)
    check_rail(s)
    child.send("q")
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0
    result = {
        "status": "PASS",
        "terminal_width_model": a.width_model,
        "wheel_events": 121,
        "frame_checks": checks,
        "rail_and_gutter_cells_checked": cells,
        "resizes": 21,
        "theme_changes": len(colors),
        "all_rail_glyphs": "ASCII space",
        "misplaced_or_residual_rail_cells": 0,
        "isolated_library": True,
    }
    (root / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if a.capture_frames:
        (root / "frames.json").write_text(json.dumps(frames, ensure_ascii=False))
    (root / "output.ansi").write_text("".join(raw), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
finally:
    if child.isalive():
        child.close(force=True)

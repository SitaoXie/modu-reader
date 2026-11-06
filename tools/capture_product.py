"""Capture real MODU PTYs using only bundled original examples.

Developer tool, not part of the application. Requires pexpect and tmux on POSIX.
Use a new --work directory. Raw terminal output stays outside release assets.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

import pexpect
from modu.library import Library


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        TERM="xterm-256color",
        COLORTERM="truecolor",
        PS1="$ ",
        HISTFILE=os.devnull,
        BASH_SILENCE_DEPRECATION_WARNING="1",
    )
    env.pop("NO_COLOR", None)
    env.pop("MODU_TEST_TRACE", None)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    frames = []

    def fixture(name, language, theme):
        directory = work / name
        directory.mkdir()
        filename = "The Riverside Bookshop.txt" if language == "en" else "河岸书店.txt"
        book = directory / filename
        shutil.copyfile(
            source / "examples" / ("first-pages.en.txt" if language == "en" else "first-pages.txt"),
            book,
        )
        library = Library(directory / "library")
        identity, _ = library.import_file(book)
        library.set_setting("language", language)
        library.set_setting("theme", theme)
        library.set_setting("last_book", identity)
        return library.root

    def read_for(child, duration):
        chunks = []
        end = time.monotonic() + duration
        while time.monotonic() < end:
            try:
                chunks.append(child.read_nonblocking(262144, timeout=0.02))
            except pexpect.TIMEOUT:
                pass
        return "".join(chunks)

    for name, language, theme in [
        ("reading-english", "en", "modu-gold"),
        ("reading-chinese", "zh", "modu-paper"),
    ]:
        library = fixture(name, language, theme)
        child = pexpect.spawn(
            sys.executable,
            ["-m", "modu", "--library", str(library)],
            env=env,
            cwd=source,
            encoding="utf-8",
            dimensions=(34, 110),
        )
        try:
            raw = read_for(child, 3)
            frames.append(dict(name=name, columns=110, rows=34, ansi=raw, theme=theme))
            child.send("q")
            child.expect(pexpect.EOF)
            child.close()
            assert child.exitstatus == 0
        finally:
            if child.isalive():
                child.close(force=True)

    tmux = shutil.which("tmux")
    if not tmux:
        raise SystemExit("tmux is required for the side-by-side product capture")
    socket = f"modu-product-{os.getpid()}"

    def mux(*arguments):
        return subprocess.check_output(
            [tmux, "-L", socket, "-f", os.devnull, *arguments], env=env, text=True
        )

    child = None
    try:
        library = fixture("side-by-side", "en", "modu-gold")
        mux(
            "new-session",
            "-d",
            "-x",
            "148",
            "-y",
            "34",
            "-s",
            "modu-demo",
            "-c",
            str(source),
            "bash --noprofile --norc",
        )
        mux("set-option", "status", "off")
        mux("set-option", "mouse", "on")
        mux(
            "split-window",
            "-h",
            "-l",
            "68",
            "-t",
            "modu-demo:0.0",
            shlex.join([sys.executable, "-m", "modu", "--library", str(library)]),
        )
        mux(
            "send-keys",
            "-t",
            "modu-demo:0.0",
            "git --no-pager diff --stat; python -m pytest -q tests/test_english.py tests/test_i18n.py",
            "Enter",
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            pane = mux("capture-pane", "-p", "-t", "modu-demo:0.0")
            if " passed in " in pane:
                break
            if " failed" in pane:
                raise AssertionError("Product-capture tests failed; do not publish this terminal")
            time.sleep(0.2)
        else:
            raise AssertionError("Tests did not finish before the capture deadline")
        mux("select-pane", "-t", "modu-demo:0.1")
        child = pexpect.spawn(
            tmux,
            ["-L", socket, "attach-session", "-t", "modu-demo"],
            env=env,
            encoding="utf-8",
            dimensions=(34, 148),
        )
        raw = read_for(child, 3)
        frames.append(dict(name="side-by-side", columns=148, rows=34, ansi=raw, theme="modu-gold"))
    finally:
        if child is not None and child.isalive():
            child.close(force=True)
        subprocess.run([tmux, "-L", socket, "kill-server"], capture_output=True)
    (work / "frames.json").write_text(json.dumps(frames, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"captures": [frame["name"] for frame in frames]}))


if __name__ == "__main__":
    main()

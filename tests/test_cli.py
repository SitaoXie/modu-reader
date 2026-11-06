"""Exercise the installed entry point and child parser, using private temporary data."""

import os
from pathlib import Path
import subprocess
import sys


def run_cli(root: Path, *args: str):
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["MODU_TEST_TRACE"] = str(root / "unexpected-trace.json")
    return subprocess.run(
        [sys.executable, "-I", "-m", "modu", "--library", str(root / "library"), *args],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )


def test_installed_cli_unicode_paths_and_no_text_export(tmp_path):
    book = tmp_path / "中文 空格 [测试].txt"
    book.write_text("第一章 夜航\n\n“我们启程吧。”灯光越过河面，映在窗上。", encoding="utf-8")
    imported = run_cli(tmp_path, "--import-only", str(book))
    assert imported.returncode == 0, imported.stderr
    listing = run_cli(tmp_path, "--list")
    assert listing.returncode == 0 and book.stem in listing.stdout
    assert not (tmp_path / "unexpected-trace.json").exists()


def test_cli_errors_cannot_emit_terminal_controls(tmp_path):
    # No such file is created: control characters are invalid filenames on Windows.
    missing = tmp_path / "missing\x1b[31m.txt"
    result = run_cli(tmp_path, "--import-only", str(missing))
    assert result.returncode == 1
    assert "\x1b" not in result.stdout + result.stderr

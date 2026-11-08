"""Test-only JSON bridge between a real CLI PTY and an isolated xterm.js fixture."""

import argparse
import codecs
import fcntl
import json
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True)
    parser.add_argument("--library", required=True)
    parser.add_argument("--book", required=True)
    args = parser.parse_args()
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 36, 110, 0, 0))
    env = os.environ.copy()
    env.update(TERM="xterm-256color", COLORTERM="truecolor", PYTHONUTF8="1")
    env.pop("NO_COLOR", None)
    child = subprocess.Popen(
        [args.python, "-m", "modu", "--library", args.library, "--lang", "en", args.book],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        start_new_session=True,
    )
    os.close(slave)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    pending = b""
    try:
        while True:
            ready, _, _ = select.select([master, sys.stdin.fileno()], [], [], 1)
            if master in ready:
                try:
                    data = os.read(master, 262144)
                except OSError:
                    break
                if not data:
                    break
                print(json.dumps({"output": decoder.decode(data)}), flush=True)
            if sys.stdin.fileno() in ready:
                data = os.read(sys.stdin.fileno(), 65536)
                if not data:
                    break
                pending += data
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    action = json.loads(line)
                    if "input" in action:
                        os.write(master, action["input"].encode())
                    elif "resize" in action:
                        columns, rows = action["resize"]
                        fcntl.ioctl(
                            master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0)
                        )
                        os.kill(child.pid, signal.SIGWINCH)
            if child.poll() is not None and not ready:
                break
    finally:
        os.close(master)
        if child.poll() is None:
            child.terminate()
        child.wait(timeout=5)
        print(json.dumps({"exit": child.returncode}), flush=True)


if __name__ == "__main__":
    main()

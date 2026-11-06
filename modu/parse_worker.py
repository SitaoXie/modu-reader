"""Private child-process entry point for bounded extraction; not an OS security sandbox."""

from __future__ import annotations
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 4:
        return 2
    # Resource limits supplement the parent's wall-clock timeout on POSIX systems.
    # Windows still gets the timeout and all input/output-size limits.
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
        resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    except (ImportError, ValueError, OSError):
        pass  # Limits are optional on platforms that do not implement resource.
    from .parsers import document_bytes, parse_file
    from .safety import atomic_write
    from .model import clean
    import json

    source, result, title = sys.argv[1:]
    try:
        document = parse_file(Path(source), title=title)
        atomic_write(Path(result), document_bytes(document))
        return 0
    except Exception as error:
        # Output goes only to the parent's private staging directory, never stdout.
        atomic_write(
            Path(result),
            json.dumps({"error": clean(str(error))[:500]}, ensure_ascii=False).encode("utf-8"),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

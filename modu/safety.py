"""Resource bounds and local-only file operations; no shell or network access."""

from __future__ import annotations
import os
from pathlib import Path
import re
import tempfile
import zlib

MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 4096
MAX_DOCUMENT_CHARS = 8_000_000
MAX_BLOCKS = 100_000
MAX_CACHE_BYTES = 64 * 1024 * 1024
MAX_PDF_PAGES = 2000
MAX_DIRECTORY_FILES = 1000
PARSE_TIMEOUT_SECONDS = 45


def validate_book_id(book_id: str) -> str:
    if not isinstance(book_id, str) or re.fullmatch(r"[a-f0-9]{64}", book_id) is None:
        raise ValueError("书籍标识无效。")
    return book_id


def read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("文件内容超过允许的大小。")
    return data


def decompress_bounded(data: bytes) -> bytes:
    inflater = zlib.decompressobj()
    result = inflater.decompress(data, MAX_CACHE_BYTES + 1)
    if len(result) > MAX_CACHE_BYTES or inflater.unconsumed_tail or not inflater.eof:
        raise ValueError("缓存大小异常或已损坏。")
    if inflater.unused_data:
        raise ValueError("缓存含多余数据。")
    return result


def atomic_write(path: Path, data: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".modu-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def import_paths(path: Path) -> list[Path]:
    """Explicit folder imports skip hidden entries and symlinks; never traverse other roots."""
    path = path.expanduser()
    if not path.is_dir():
        return [path]
    from .parsers import SUPPORTED

    files = []
    for directory, subdirs, names in os.walk(path, followlinks=False):
        subdirs[:] = sorted(
            d for d in subdirs if not d.startswith(".") and not (Path(directory) / d).is_symlink()
        )
        for name in sorted(names):
            candidate = Path(directory) / name
            if (
                not name.startswith(".")
                and not candidate.is_symlink()
                and candidate.suffix.lower() in SUPPORTED
            ):
                files.append(candidate)
                if len(files) > MAX_DIRECTORY_FILES:
                    raise ValueError("文件夹中的书籍超过 1000 本，请分批导入。")
    return files

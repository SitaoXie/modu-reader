"""Private local library, snapshot imports, bounded parsing and atomic cache writes."""

from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3

# The only subprocess is the fixed, isolated parser module; no shell is used.
import subprocess  # nosec B404
import sys
import tempfile
import time
import zlib
from platformdirs import user_data_path
from .model import clean
from .themes import PALETTES
from .parsers import SUPPORTED, document_bytes, document_from_bytes
from .safety import (
    MAX_SOURCE_BYTES,
    MAX_CACHE_BYTES,
    PARSE_TIMEOUT_SECONDS,
    validate_book_id,
    read_bounded,
    decompress_bounded,
    atomic_write,
)

DEFAULT_HOME = user_data_path("MODU", appauthor=False) / "library"


def parse_isolated(path: Path, title: str, staging: Path):
    """Only a fixed installed Python module is executed; no shell or book-provided code."""
    with tempfile.TemporaryDirectory(prefix=".parse-", dir=staging) as temporary:
        result = Path(temporary) / "result.json"
        try:
            # Fixed interpreter/module; arguments never enter a shell.
            outcome = subprocess.run(  # nosec B603
                [sys.executable, "-I", "-m", "modu.parse_worker", str(path), str(result), title],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=PARSE_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise ValueError("书籍解析超时，已停止解析进程。") from None
        if not result.is_file():
            raise ValueError("无法解析书籍，或解析过程超过资源限制。")
        data = read_bounded(result, MAX_CACHE_BYTES)
        if outcome.returncode:
            try:
                message = json.loads(data).get("error", "书籍无法解析。")
            except (ValueError, AttributeError):
                message = "书籍无法解析。"
            raise ValueError(clean(str(message))[:500])
        return document_from_bytes(data)


class Library:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in ("originals", "cache"):
            path = self.root / name
            if path.is_symlink():
                raise ValueError("书库子目录不能是符号链接。")
            path.mkdir(exist_ok=True, mode=0o700)
        self.db = self.root / "library.sqlite3"
        if self.db.is_symlink():
            raise ValueError("书库索引不能是符号链接。")
        with self.connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS books (
                    id TEXT PRIMARY KEY, title TEXT, author TEXT, format TEXT,
                    chars INTEGER, added REAL, opened REAL DEFAULT 0,
                    position INTEGER DEFAULT 0, source TEXT, warnings TEXT);
                CREATE TABLE IF NOT EXISTS bookmarks (
                    book_id TEXT, position INTEGER, label TEXT, created REAL,
                    PRIMARY KEY(book_id, position));
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            """)
            conn.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(books)")}
            if "archived" not in columns:
                conn.execute("ALTER TABLE books ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
        if os.name == "posix":
            self.db.chmod(0o600)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def books(self, archived=False):
        with self.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM books WHERE archived=? ORDER BY opened DESC, added DESC",
                    (int(archived),),
                )
            ]

    def archive_book(self, book_id, archived=True):
        validate_book_id(book_id)
        with self.connect() as c:
            c.execute("UPDATE books SET archived=? WHERE id=?", (int(archived), book_id))
            if archived:
                c.execute(
                    "DELETE FROM settings WHERE key IN ('last_book', 'web:last_book') AND value=?",
                    (json.dumps(book_id),),
                )

    def delete_book(self, book_id):
        """Remove only content-addressed library copies; never follow DB source paths."""
        validate_book_id(book_id)
        moved = []
        with tempfile.TemporaryDirectory(prefix=".delete-", dir=self.root) as temporary:
            try:
                with self.connect() as c:
                    c.execute("BEGIN IMMEDIATE")
                    book = c.execute("SELECT format FROM books WHERE id=?", (book_id,)).fetchone()
                    if book is None:
                        return
                    extension = "." + book["format"].lower()
                    if extension not in SUPPORTED:
                        raise ValueError("书籍格式无效。")
                    paths = [
                        self.root / "originals" / f"{book_id}{extension}",
                        self.root / "cache" / f"{book_id}.json.z",
                    ]
                    for path in paths:
                        if path.parent.is_symlink() or path.is_symlink():
                            raise ValueError("书库子目录或文件不能是符号链接。")
                        if path.exists() and not path.is_file():
                            raise ValueError("书库副本路径无效。")
                    for path in paths:
                        if path.exists():
                            staged = Path(temporary) / path.name
                            os.replace(path, staged)
                            moved.append((path, staged))
                    c.execute("DELETE FROM bookmarks WHERE book_id=?", (book_id,))
                    c.execute("DELETE FROM books WHERE id=?", (book_id,))
                    c.execute(
                        "DELETE FROM settings WHERE key IN ('last_book', 'web:last_book') AND value=?",
                        (json.dumps(book_id),),
                    )
                    c.execute(
                        "DELETE FROM settings WHERE key IN (?, ?, ?)",
                        (f"web:position:{book_id}", f"web:marks:{book_id}", f"translation_target:{book_id}"),
                    )
            except Exception:
                for path, staged in reversed(moved):
                    os.replace(staged, path)
                raise

    def book(self, book_id):
        with self.connect() as c:
            r = c.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
            return dict(r) if r else None

    def setting(self, key, default=None):
        with self.connect() as c:
            row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            try:
                value = json.loads(row[0]) if row else default
                if key == "sidebar_open" and type(value) is not bool:
                    return default
                if key == "read_width" and (type(value) is not int or not 24 <= value <= 160):
                    return default
                if key == "spacing" and (type(value) is not int or value not in (0, 1, 2)):
                    return default
                if key == "language" and value not in ("zh", "en"):
                    return default
                if key == "theme" and value not in PALETTES:
                    return default
                if key == "last_book" and value is not None:
                    validate_book_id(value)
                return value
            except (ValueError, TypeError):
                return default

    def set_setting(self, key, value):
        with self.connect() as c:
            c.execute(
                "INSERT OR REPLACE INTO settings VALUES (?,?)",
                (key, json.dumps(value, ensure_ascii=False)),
            )

    def import_file(self, path: Path):
        path = path.expanduser().resolve()
        if not path.is_file() or path.suffix.lower() not in SUPPORTED:
            raise ValueError("请选择本地 TXT、EPUB、PDF 或 Markdown 文件。")
        with tempfile.TemporaryDirectory(prefix=".import-", dir=self.root) as temporary:
            snapshot = Path(temporary) / ("book" + path.suffix.lower())
            digest, size = hashlib.sha256(), 0
            with path.open("rb") as source, snapshot.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_SOURCE_BYTES:
                        raise ValueError("单个文件不能超过 64 MB。")
                    digest.update(chunk)
                    output.write(chunk)
            identifier = digest.hexdigest()
            if self.book(identifier):
                return identifier, False
            doc = parse_isolated(snapshot, clean(path.stem), self.root)
            dest = self.root / "cache" / f"{identifier}.json.z"
            atomic_write(dest, zlib.compress(document_bytes(doc), 6))
            original = self.root / "originals" / f"{identifier}{path.suffix.lower()}"
            if os.name == "posix":
                snapshot.chmod(0o600)
            os.replace(snapshot, original)
            with self.connect() as c:
                c.execute(
                    "INSERT OR IGNORE INTO books(id,title,author,format,chars,added,source,warnings) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        identifier,
                        doc.title,
                        doc.author,
                        path.suffix[1:].upper(),
                        len(doc.text),
                        time.time(),
                        original.relative_to(self.root).as_posix(),
                        json.dumps(doc.warnings, ensure_ascii=False),
                    ),
                )
            return identifier, True

    def load(self, book_id):
        validate_book_id(book_id)
        cache = self.root / "cache" / f"{book_id}.json.z"
        try:
            if cache.is_symlink():
                raise ValueError("缓存不能是符号链接。")
            return document_from_bytes(decompress_bounded(read_bounded(cache, MAX_CACHE_BYTES)))
        except (OSError, ValueError, zlib.error, KeyError, TypeError):
            book = self.book(book_id)
            if not book:
                raise ValueError("书籍不在书架中。")
            extension = "." + book["format"].lower()
            if extension not in SUPPORTED:
                raise ValueError("书籍格式无效。")
            # Reconstruct the content-addressed local path; never trust a path in the DB.
            original = self.root / "originals" / f"{book_id}{extension}"
            if original.is_symlink() or not original.is_file():
                raise ValueError("本地原书副本不存在或路径无效，请重新导入。")
            doc = parse_isolated(original, clean(book["title"]), self.root)
            atomic_write(cache, zlib.compress(document_bytes(doc), 6))
            return doc

    def save_position(self, book_id, position):
        with self.connect() as c:
            updated = c.execute(
                "UPDATE books SET position=?,opened=? WHERE id=?",
                (int(position), time.time(), book_id),
            )
            if (
                not updated.rowcount
                or c.execute("SELECT archived FROM books WHERE id=?", (book_id,)).fetchone()[0]
            ):
                return
            c.execute(
                "INSERT OR REPLACE INTO settings VALUES ('last_book',?)", (json.dumps(book_id),)
            )

    def bookmarks(self, book_id):
        with self.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM bookmarks WHERE book_id=? ORDER BY position", (book_id,)
                )
            ]

    def toggle_bookmark(self, book_id, position, label):
        with self.connect() as c:
            if not c.execute("SELECT 1 FROM books WHERE id=?", (book_id,)).fetchone():
                return False
            existing = c.execute(
                "SELECT 1 FROM bookmarks WHERE book_id=? AND position=?", (book_id, position)
            ).fetchone()
            if existing:
                c.execute(
                    "DELETE FROM bookmarks WHERE book_id=? AND position=?", (book_id, position)
                )
            else:
                c.execute(
                    "INSERT INTO bookmarks VALUES (?,?,?,?)",
                    (book_id, position, label, time.time()),
                )
        return not existing

"""Private loopback reader shared by the native WebView and browser launcher."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
from threading import Event, Thread
from urllib.parse import unquote, urlsplit

from .i18n import normalize_language, translate
from . import __version__
from .vocabulary import Vocabulary
from .parsers import SUPPORTED
from .safety import MAX_SOURCE_BYTES, read_bounded, validate_book_id
from .themes import LIGHT_PALETTES, PALETTES
from .translation import (
    LANGUAGES, TranslationError, options_for, pronunciation, set_option, set_target, settings_for, translate_selection,
)
from .web_epub import EpubBook
from .web_pdf import PdfAssets

DEFAULT_PORT = 8765
WEB_FILES = {
    "web.html": "text/html; charset=utf-8",
    "web.css": "text/css; charset=utf-8",
    "web.js": "text/javascript; charset=utf-8",
}
# WebKit needs the sandbox scripting flag to dispatch the reader window's
# keyboard listeners. The publication's own scripts remain blocked by CSP.
BOOK_SANDBOX = (
    "script-src 'none'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'self'; sandbox allow-same-origin allow-scripts"
)
EPUB_BRIDGE = """
:root { color-scheme: var(--modu-scheme, dark); background: var(--modu-bg, #121416); }
body { background: transparent; color: var(--modu-fg, #ddd6c8); overflow-wrap: break-word; }
img, svg { max-width: 100%; }
::selection { background: #d4b477; color: #171717; }
::highlight(modu-words) { background-color: #d4b47740; text-decoration: underline; text-decoration-color: var(--modu-accent, #d4b477); }
"""


def location(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid location")
    index, scroll = value.get("index"), value.get("scroll")
    if type(index) is not int or not 0 <= index < 100_000:
        raise ValueError("Invalid location")
    if type(scroll) not in (float, int) or not 0 <= scroll <= 1:
        raise ValueError("Invalid location")
    result = {"index": index, "scroll": scroll}
    if "offset" in value:
        offset = value["offset"]
        if type(offset) not in (float, int) or not 0 <= offset <= 1:
            raise ValueError("Invalid location")
        result["offset"] = offset
    return result


def chapter_json(chapter):
    return {"name": chapter.name, "label": chapter.label, "fragment": chapter.fragment}


class Reader:
    def __init__(self, library, book_id=None, shelf=False):
        self.library = library
        self.vocabulary = Vocabulary(library)
        self.web_files = {name: Path(__file__).with_name(name).read_bytes() for name in WEB_FILES}
        self.explicit_book = book_id is not None
        self.start_book = book_id or (
            None if shelf else library.setting("web:last_book") or library.setting("last_book")
        )
        self.epub = lru_cache(maxsize=2)(EpubBook)
        self.document = lru_cache(maxsize=2)(library.load)
        self.pdf = PdfAssets(library.root)

    def shelf(self):
        fields = ("id", "title", "author", "format", "archived")
        books = self.library.books() + self.library.books(archived=True)
        theme = self.library.setting("theme")
        language = normalize_language(self.library.setting("language"))
        return {
            "serverVersion": __version__,
            "books": [{key: book[key] for key in fields} for book in books],
            "start": self.start_book,
            "explicitBook": self.explicit_book,
            "language": language,
            "copyPath": str(self.library.root / "originals"),
            "theme": theme if isinstance(theme, str) and theme in PALETTES else "modu-gold",
            "themes": {
                key: {
                    "colors": palette[:5],
                    "label": translate(language, palette[5]),
                    "light": key in LIGHT_PALETTES,
                }
                for key, palette in PALETTES.items()
            },
            "languages": LANGUAGES,
            "translation": settings_for(self.library, None),
            "translationOptions": options_for(self.library),
        }

    def book(self, identifier):
        validate_book_id(identifier)
        book = self.library.book(identifier)
        if book is None:
            raise FileNotFoundError
        extension = "." + book["format"].lower()
        if extension not in SUPPORTED:
            raise FileNotFoundError
        source = self.library.root / "originals" / (identifier + extension)
        if source.parent.is_symlink() or source.is_symlink() or not source.is_file():
            raise FileNotFoundError
        return book, source

    def describe(self, identifier, book, source):
        fmt = book["format"].lower()
        chapters, toc = [], []
        source_language = ""
        if fmt == "epub":
            epub = self.epub(source)
            chapters = [chapter_json(chapter) for chapter in epub.chapters]
            toc = [chapter_json(chapter) for chapter in epub.toc]
            source_language = getattr(epub, "language", "")
        elif fmt != "pdf":
            chapters = [
                {"label": label, "name": str(index), "fragment": ""}
                for index, (_, label) in enumerate(self.document(identifier).chapters)
            ]
        return {
            "id": identifier, "title": book["title"], "author": book["author"],
            "format": fmt, "chapters": chapters, "toc": toc or chapters,
            "sourceLanguage": source_language,
            "position": self.library.setting(f"web:position:{identifier}"),
            "marks": self.library.setting(f"web:marks:{identifier}", []),
            "translation": settings_for(self.library, identifier),
            "pdfReady": self.pdf.ready,
        }

    def text_chapter(self, identifier, index):
        document = self.document(identifier)
        if not 0 <= index < len(document.chapters):
            raise FileNotFoundError
        start, _ = document.chapters[index]
        end = document.chapters[index + 1][0] if index + 1 < len(document.chapters) else len(document.blocks)
        tags = {"heading": "h2", "code": "pre"}
        html = []
        for block in document.blocks[start:end]:
            tag = tags.get(block.kind, "p")
            html.append(f"<{tag}>{escape(block.text)}</{tag}>")
        style = "body{font:1.18rem/1.75 system-ui;margin:1rem auto;max-width:72ch;padding:0 1.5rem}"
        return (
            '<!doctype html><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width"><style>{EPUB_BRIDGE}{style}</style>'
            + "".join(html)
        ).encode()

    def import_book(self, name, data):
        name = unquote(name)
        if (
            not name or len(name) > 220 or name != Path(name).name
            or any(char in name for char in '/\\\x00<>:"|?*')
            or any(ord(char) < 32 for char in name)
            or Path(name).suffix.lower() not in SUPPORTED
        ):
            raise ValueError("Invalid filename")
        with tempfile.TemporaryDirectory(prefix=".web-import-", dir=self.library.root) as directory:
            source = Path(directory) / name
            source.write_bytes(data)
            identifier, _ = self.library.import_file(source)
        return {"id": identifier}

    def update(self, identifier, action, data):
        self.book(identifier)
        if action in {"position", "mark"}:
            return self.save_reading(identifier, action, location(data), data.get("remove") is True)
        if action == "translation":
            set_target(self.library, identifier, data.get("target"))
            return settings_for(self.library, identifier)
        if action == "translate":
            return translate_selection(
                self.library, identifier, data.get("text"), data.get("source", ""),
                data.get("provider", "local"),
            )
        if action == "archive":
            archived = data.get("archived")
            if type(archived) is not bool:
                raise ValueError("Invalid archive state")
            self.library.archive_book(identifier, archived)
            return {}
        if action == "delete":
            self.library.delete_book(identifier)
            self.document.cache_clear()
            self.epub.cache_clear()
            return {}
        raise FileNotFoundError

    def save_reading(self, identifier, action, spot, remove):
        with self.library.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            book = connection.execute("SELECT archived FROM books WHERE id=?", (identifier,)).fetchone()
            if book is None:
                raise FileNotFoundError
            if action == "position":
                connection.execute(
                    "INSERT OR REPLACE INTO settings VALUES (?, ?)",
                    (f"web:position:{identifier}", json.dumps(spot)),
                )
                if not book["archived"]:
                    connection.execute(
                        "INSERT OR REPLACE INTO settings VALUES ('web:last_book', ?)",
                        (json.dumps(identifier),),
                    )
                return {}
            key = f"web:marks:{identifier}"
            row = connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            marks = json.loads(row[0]) if row else []
            if not isinstance(marks, list):
                marks = []
            if remove:
                marks = [mark for mark in marks if mark != spot]
            elif spot not in marks:
                marks = (marks + [spot])[-200:]
            connection.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(marks)))
            return {"marks": marks}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def setup(self):
        self.request.settimeout(20)
        super().setup()

    def log_message(self, *_args):
        # URLs contain a private session capability and book/resource names.
        pass

    def send_data(self, data, mime, status=200, csp=None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy", csp or "default-src 'none'; frame-ancestors 'self'")
        self.end_headers()
        self.wfile.write(data)

    def json(self, value, status=200):
        self.send_data(json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

    def route(self):
        if self.headers.get("Host") != self.server.host:
            raise PermissionError
        path = urlsplit(self.path).path
        if self.server.root_entry and self.command == "GET" and path == "/":
            if (
                self.headers.get("Sec-Fetch-Site") not in {None, "none", "same-origin"}
                or self.headers.get("Sec-Fetch-Dest") not in {None, "document"}
                or self.headers.get("Origin") not in {None, self.server.origin}
            ):
                raise PermissionError
            return None
        if not path.startswith(self.server.prefix):
            raise FileNotFoundError
        return path[len(self.server.prefix):]

    def do_GET(self):
        self.dispatch(self.get)

    def do_POST(self):
        self.dispatch(self.post)

    def dispatch(self, method):
        try:
            method(self.route())
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except PermissionError:
            self.json({"error": "forbidden"}, 403)
        except (FileNotFoundError, KeyError):
            self.json({"error": "missing"}, 404)
        except TranslationError as error:
            self.json({"error": error.code}, 422)
        except (OSError, ValueError, sqlite3.Error, RuntimeError):
            self.json({"error": "operation_failed"}, 422)

    def get(self, route):
        reader = self.server.reader
        if not route or route in WEB_FILES:
            name = route or "web.html"
            csp = (
                "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
                "font-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; worker-src 'self'; "
                "frame-src 'self'; object-src 'none'; base-uri 'none'; "
                "form-action 'none'; frame-ancestors 'none'"
            )
            data = reader.web_files[name]
            if route is None:
                # Keep the visible address at /. Assets and APIs still use the
                # per-launch session path.
                for asset in ("web.css", "web.js"):
                    data = data.replace(f'"{asset}"'.encode(), f'"{self.server.prefix}{asset}"'.encode())
            return self.send_data(data, WEB_FILES[name], csp=csp)
        if route == "api/shelf":
            return self.json(reader.shelf())
        if route == "api/vocabulary":
            return self.json(reader.vocabulary.entries())
        if route.startswith("pdfjs/"):
            mime, data = reader.pdf.resource(route.removeprefix("pdfjs/"))
            # Workers must be able to load the PDF and their packaged assets.
            return self.send_data(data, mime, csp="default-src 'none'; connect-src 'self'; script-src 'self' 'wasm-unsafe-eval'")
        match = re.fullmatch(r"book/([a-f0-9]{64})(?:/(.*))?", route)
        if not match:
            raise FileNotFoundError
        identifier, asset = match.groups()
        book, source = reader.book(identifier)
        if asset is None:
            return self.json(reader.describe(identifier, book, source))
        if asset == "pdf" and source.suffix == ".pdf":
            return self.send_data(read_bounded(source, MAX_SOURCE_BYTES), "application/pdf")
        if asset.startswith("epub/") and source.suffix == ".epub":
            prefix = f"{self.server.prefix}book/{identifier}/epub/"
            mime, data = reader.epub(source).resource(
                unquote(asset.removeprefix("epub/")), prefix=prefix, css=EPUB_BRIDGE
            )
            base = self.server.origin + prefix
            csp = (
                f"default-src 'none'; style-src 'unsafe-inline' {base}; "
                f"img-src {base}; font-src {base}; media-src {base}; "
                + BOOK_SANDBOX
            )
            return self.send_data(data, mime, csp=csp)
        if asset.startswith("text/") and source.suffix in {".txt", ".md", ".markdown"}:
            return self.send_data(
                reader.text_chapter(identifier, int(asset.removeprefix("text/"))),
                "text/html; charset=utf-8",
                csp="default-src 'none'; style-src 'unsafe-inline'; " + BOOK_SANDBOX,
            )
        raise FileNotFoundError

    def post(self, route):
        if self.headers.get("Origin") != self.server.origin:
            raise PermissionError
        reader = self.server.reader
        upload = route == "api/import"
        mime = "application/octet-stream" if upload else "application/json"
        if self.headers.get_content_type() != mime:
            raise ValueError("Invalid media type")
        count = int(self.headers.get("Content-Length", "0"))
        limit = MAX_SOURCE_BYTES if upload else 16_384
        if not 0 < count <= limit:
            raise ValueError("Invalid request size")
        raw = self.rfile.read(count)
        if len(raw) != count:
            raise ValueError("Incomplete request")
        if upload:
            return self.json(reader.import_book(self.headers.get("X-MODU-Filename", ""), raw))
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Invalid request")
        if route == "api/pdf-install":
            reader.pdf.install()
            return self.json({})
        if route == "api/theme" and isinstance(data.get("theme"), str) and data["theme"] in PALETTES:
            reader.library.set_setting("theme", data["theme"])
            return self.json({})
        if route == "api/translation":
            set_target(reader.library, None, data.get("target"))
            return self.json(settings_for(reader.library, None))
        if route == "api/translation-options":
            return self.json(set_option(reader.library, data))
        if route == "api/vocabulary":
            return self.json(reader.vocabulary.update(data))
        if route == "api/phonetics":
            return self.json(reader.vocabulary.phonetics(data))
        if route == "api/pronounce":
            return self.send_data(pronunciation(data.get("text"), data.get("accent", "us")), "audio/mpeg")
        match = re.fullmatch(r"book/([a-f0-9]{64})/(\w+)", route)
        if match:
            identifier, action = match.groups()
            return self.json(reader.update(identifier, action, data))
        raise FileNotFoundError


@contextmanager
def serve(library, book_id=None, *, shelf=False, port=None):
    reader = Reader(library, book_id, shelf)
    with ThreadingHTTPServer(("127.0.0.1", port or 0), Handler) as server:
        server.host = f"127.0.0.1:{server.server_port}"
        server.origin = f"http://{server.host}"
        server.prefix = f"/{secrets.token_urlsafe(24)}/"
        server.root_entry = port is not None
        server.reader = reader
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.origin + ("/" if server.root_entry else server.prefix)
        finally:
            server.shutdown()
            thread.join()


def run(library, book_id=None, *, shelf=False, browser=False, port=None):
    import sys
    import webbrowser

    with serve(library, book_id, shelf=shelf, port=port) as url:
        native = None
        if port is None and not browser and sys.platform in {"darwin", "win32"}:
            try:
                import webview as native
            except ImportError:
                pass
        if native:
            native.create_window(
                "墨读 MODU", url, width=1100, height=780, min_size=(430, 360), text_select=True
            )
            native.start(gui="cocoa" if sys.platform == "darwin" else "edgechromium", private_mode=True)
            return
        language = normalize_language(library.setting("language"))
        print(url, flush=True)
        if port is None:
            webbrowser.open(url)
        print("按 Ctrl+C 结束 Web 阅读。" if language == "zh" else "Press Ctrl+C to stop Web reading.", flush=True)
        try:
            Event().wait()
        except KeyboardInterrupt:
            pass

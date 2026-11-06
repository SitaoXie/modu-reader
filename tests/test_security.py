import json
import os
import subprocess
import zipfile
import zlib
import pytest
from modu.library import Library, parse_isolated
from modu.parsers import parse_file, member_name
from modu.model import clean
from modu import safety
from tests.fixtures import make_pdf


def epub(path, *, container=None, href="one.xhtml", extra=None):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "META-INF/container.xml",
            container
            or '<container><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>',
        )
        z.writestr(
            "content.opf",
            f'<package><manifest><item id="one" href="{href}"/></manifest><spine><itemref idref="one"/></spine></package>',
        )
        z.writestr("one.xhtml", "<h1>第一章</h1><p>原创正文。</p>")
        if extra:
            z.writestr(*extra)


@pytest.mark.parametrize(
    "value", ["\x1b]52;c;payload\x07", "\x1b[31m", "\u009b31m", "\u202eevil", "\u2066hidden\u2069"]
)
def test_terminal_controls_and_bidi_removed(value):
    result = clean(value)
    assert not any(c in result for c in "\x1b\x07\u009b\u202e\u2066\u2069")


@pytest.mark.parametrize(
    "href",
    [
        "../../outside.txt",
        "/absolute.txt",
        "https://example.invalid/book",
        "file:///local/book",
        "%2e%2e/%2e%2e/x",
        "..\\outside",
    ],
)
def test_archive_paths_rejected(href):
    with pytest.raises(ValueError):
        member_name("", href)


def test_epub_entities_and_external_refs_rejected(tmp_path):
    from defusedxml.common import DefusedXmlException

    path = tmp_path / "entity.epub"
    epub(
        path,
        container='<!DOCTYPE x [<!ENTITY external SYSTEM "file:///never-read">]><container>&external;</container>',
    )
    with pytest.raises(DefusedXmlException):
        parse_file(path)
    epub(path, href="https://example.invalid/read")
    with pytest.raises(ValueError):
        parse_file(path)
    epub(path, extra=("../escape.txt", "must not extract"))
    with pytest.raises(ValueError):
        parse_file(path)
    assert not (tmp_path / "escape.txt").exists()


def test_epub_member_limit(tmp_path, monkeypatch):
    import modu.parsers as parsers

    monkeypatch.setattr(parsers, "MAX_MEMBER_BYTES", 256)
    path = tmp_path / "large.epub"
    epub(path, extra=("large.txt", "x" * 257))
    with pytest.raises(ValueError, match="过大"):
        parse_file(path)


def test_encrypted_pdf_rejected(tmp_path):
    path = tmp_path / "encrypted.pdf"
    make_pdf(path, encrypted=True)
    with pytest.raises(ValueError, match="加密"):
        parse_file(path)


def test_import_snapshot_limit_and_cleanup(tmp_path, monkeypatch):
    import modu.library as module

    lib = Library(tmp_path / "library")
    source = tmp_path / "large.txt"
    source.write_bytes(b"x" * 100)
    monkeypatch.setattr(module, "MAX_SOURCE_BYTES", 50)
    with pytest.raises(ValueError, match="64 MB"):
        lib.import_file(source)
    assert not list(lib.root.glob(".import-*")) and lib.books() == []
    assert source.read_bytes() == b"x" * 100


def test_corrupt_cache_rebuilt_and_database_path_not_trusted(tmp_path):
    lib = Library(tmp_path / "library")
    source = tmp_path / "original.txt"
    source.write_text("这是原创测试文字。", encoding="utf-8")
    book_id, _ = lib.import_file(source)
    cache = lib.root / "cache" / f"{book_id}.json.z"
    cache.write_bytes(b"broken")
    with lib.connect() as conn:
        conn.execute("UPDATE books SET source=? WHERE id=?", ("/must-not-be-read", book_id))
    assert lib.load(book_id).text == "这是原创测试文字。"
    assert zlib.decompress(cache.read_bytes()).startswith(b"{")
    for bad in ["../outside", "a" * 63, "A" * 64, "bad/identifier"]:
        with pytest.raises(ValueError):
            lib.load(bad)


def test_decompression_bound_and_malformed_cache(monkeypatch):
    monkeypatch.setattr(safety, "MAX_CACHE_BYTES", 100)
    with pytest.raises(ValueError):
        safety.decompress_bounded(zlib.compress(b"x" * 101))
    from modu.parsers import document_from_bytes

    for value in [{}, {"version": 3, "blocks": []}, {"version": 3, "blocks": [["x", "bad"]]}]:
        with pytest.raises(ValueError):
            document_from_bytes(json.dumps(value).encode())


def test_timeout_cleanup(tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)

    monkeypatch.setattr("modu.library.subprocess.run", timeout)
    with pytest.raises(ValueError, match="超时"):
        parse_isolated(tmp_path / "book.txt", "Test", tmp_path)
    assert not list(tmp_path.glob(".parse-*"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions / symlink semantics")
def test_private_permissions_and_symlink_cache(tmp_path):
    lib = Library(tmp_path / "library")
    source = tmp_path / "original.txt"
    source.write_text("原创安全测试。", encoding="utf-8")
    book_id, _ = lib.import_file(source)
    assert lib.root.stat().st_mode & 0o777 == 0o700
    assert lib.db.stat().st_mode & 0o777 == 0o600
    for file in (lib.root / "originals").iterdir():
        assert file.stat().st_mode & 0o777 == 0o600
    external = tmp_path / "external"
    external.write_bytes(b"never overwrite")
    cache = lib.root / "cache" / f"{book_id}.json.z"
    cache.unlink()
    cache.symlink_to(external)
    assert lib.load(book_id).text == "原创安全测试。"
    assert external.read_bytes() == b"never overwrite" and not cache.is_symlink()


def test_directory_import_skips_hidden_entries(tmp_path):
    (tmp_path / ".private").mkdir()
    (tmp_path / ".private" / "private.txt").write_text("private", encoding="utf-8")
    (tmp_path / "public.txt").write_text("original", encoding="utf-8")
    (tmp_path / ".hidden.txt").write_text("private", encoding="utf-8")
    assert [p.name for p in safety.import_paths(tmp_path)] == ["public.txt"]


@pytest.mark.parametrize(
    "key,value,default",
    [
        ("theme", {}, "modu-gold"),
        ("read_width", "wide", 80),
        ("read_width", 10000, 80),
        ("spacing", -1, 1),
        ("sidebar_open", "false", True),
        ("last_book", "../outside", None),
    ],
)
def test_invalid_settings_fall_back(tmp_path, key, value, default):
    library = Library(tmp_path / "library")
    library.set_setting(key, value)
    assert library.setting(key, default) == default


def test_unhashable_cache_style_rejected():
    from modu.parsers import CACHE_VERSION, document_from_bytes

    payload = {"version": CACHE_VERSION, "blocks": [["text", {}]]}
    with pytest.raises(ValueError):
        document_from_bytes(json.dumps(payload).encode())

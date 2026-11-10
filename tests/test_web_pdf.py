"""Exercise an isolated PDF runtime install without making a network request."""

import base64
from hashlib import sha512
from io import BytesIO
import tarfile

import pytest

from modu import web_pdf


def _runtime_archive(*, linked_worker=False):
    output = BytesIO()
    names = [
        *web_pdf._REQUIRED_ASSETS,
        "cmaps/Adobe-CNS1-0.bcmap",
        "standard_fonts/LiberationSans-Regular.ttf",
        "../outside",
        "legacy/web/pdf_viewer.mjs",
    ]
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name in names:
            item = tarfile.TarInfo(f"package/{name}")
            data = name.encode()
            if linked_worker and name == web_pdf.PDF_WORKER:
                item.type = tarfile.SYMTYPE
                item.linkname = "../../outside"
                archive.addfile(item)
            else:
                item.size = len(data)
                archive.addfile(item, BytesIO(data))
    return output.getvalue()


def _set_download(monkeypatch, data):
    monkeypatch.setattr(web_pdf, "_download", lambda: data)
    monkeypatch.setattr(web_pdf, "ARCHIVE_SHA512", base64.b64encode(sha512(data).digest()).decode())


def test_installs_only_served_pdf_runtime_assets(tmp_path, monkeypatch):
    _set_download(monkeypatch, _runtime_archive())
    assets = web_pdf.PdfAssets(tmp_path)
    assert not assets.ready
    with pytest.raises(FileNotFoundError):
        assets.resource(web_pdf.PDF_MODULE)
    assets.install()
    assert assets.ready
    assert assets.resource(web_pdf.PDF_MODULE) == (web_pdf.JAVASCRIPT, web_pdf.PDF_MODULE.encode())
    assert assets.resource("wasm/openjpeg.wasm")[0] == "application/wasm"
    assert assets.resource("standard_fonts/LiberationSans-Regular.ttf")[0] == "font/ttf"
    assert not (assets.directory.parent / "outside").exists()
    assert not (assets.directory / "legacy/web/pdf_viewer.mjs").exists()
    for name in ("../../outside", "cmaps/../LICENSE", "legacy/web/pdf_viewer.mjs"):
        with pytest.raises(FileNotFoundError):
            assets.resource(name)
    monkeypatch.setattr(web_pdf, "_download", lambda: pytest.fail("ready runtime downloaded again"))
    assets.install()


def test_rejects_corrupted_download_without_publishing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(web_pdf, "_download", _runtime_archive)
    assets = web_pdf.PdfAssets(tmp_path)
    with pytest.raises(ValueError, match="integrity"):
        assets.install()
    assert not assets.directory.exists()


def test_rejects_archive_link_and_cleans_staging_directory(tmp_path, monkeypatch):
    _set_download(monkeypatch, _runtime_archive(linked_worker=True))
    assets = web_pdf.PdfAssets(tmp_path)
    with pytest.raises(ValueError, match="archive member"):
        assets.install()
    assert not list(assets.directory.parent.iterdir())

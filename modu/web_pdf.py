"""Install the pinned PDF.js browser runtime on explicit request."""

from __future__ import annotations

import base64
from hashlib import sha512
from io import BytesIO
from pathlib import Path, PurePosixPath
import re
from shutil import copyfileobj
import tarfile
from tempfile import TemporaryDirectory
from urllib.request import urlopen


VERSION = "6.5.438"
ARCHIVE_URL = f"https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-{VERSION}.tgz"
ARCHIVE_SHA512 = "vg8Pw1x+AFKy4AMDvhuWl5cOYV8d698UoEANoFFhc79hqXDnZQqnOXoxw3HG907WHOg1JYOvLhP756boddFxpA=="  # pragma: allowlist secret
MAX_DOWNLOAD = 30 * 1024 * 1024
MAX_ASSET = 8 * 1024 * 1024
JAVASCRIPT = "text/javascript; charset=utf-8"

PDF_MODULE = "legacy/build/pdf.min.mjs"
PDF_WORKER = "legacy/build/pdf.worker.min.mjs"
_REQUIRED_ASSETS = {
    PDF_MODULE: JAVASCRIPT,
    PDF_WORKER: JAVASCRIPT,
    "wasm/jbig2.wasm": "application/wasm",
    "wasm/openjpeg.wasm": "application/wasm",
    "wasm/qcms_bg.wasm": "application/wasm",
    "wasm/jbig2_nowasm_fallback.js": JAVASCRIPT,
    "wasm/openjpeg_nowasm_fallback.js": JAVASCRIPT,
    "iccs/CGATS001Compat-v2-micro.icc": "application/vnd.iccprofile",
    "LICENSE": "text/plain; charset=utf-8",
}
_FILE_TYPES = {
    ("cmaps", ".bcmap"): "application/octet-stream",
    ("standard_fonts", ".pfb"): "application/octet-stream",
    ("standard_fonts", ".ttf"): "font/ttf",
}


def _asset_type(name: str) -> str | None:
    if name in _REQUIRED_ASSETS:
        return _REQUIRED_ASSETS[name]
    folder, _, filename = name.partition("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", filename):
        return None
    if folder in {"cmaps", "standard_fonts", "iccs", "wasm"} and (
        filename == "LICENSE" or filename.startswith("LICENSE_")
    ):
        return "text/plain; charset=utf-8"
    return _FILE_TYPES.get((folder, PurePosixPath(filename).suffix))


def _download() -> bytes:
    # The source is a fixed HTTPS URL. The archive is verified before extraction.
    with urlopen(ARCHIVE_URL, timeout=30) as response:  # nosec B310
        payload = response.read(MAX_DOWNLOAD + 1)
    if len(payload) > MAX_DOWNLOAD:
        raise ValueError("PDF.js download exceeds the size limit.")
    return payload


def _extract(payload: bytes, destination: Path) -> None:
    installed = set()
    total_size = 0
    with tarfile.open(fileobj=BytesIO(payload), mode="r|gz") as archive:
        for member in archive:
            name = member.name.removeprefix("package/")
            if name == member.name or _asset_type(name) is None:
                continue
            total_size += member.size
            if (
                not member.isfile()
                or name in installed
                or not 0 < member.size <= MAX_ASSET
                or total_size > MAX_DOWNLOAD
            ):
                raise ValueError("Unexpected PDF.js archive member.")
            path = destination.joinpath(*name.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Missing PDF.js archive data.")
            with source, path.open("xb") as output:
                copyfileobj(source, output)
            installed.add(name)
    if not _REQUIRED_ASSETS.keys() <= installed:
        raise ValueError("PDF.js archive is missing runtime files.")


class PdfAssets:
    def __init__(self, library_root: Path):
        self.directory = library_root.resolve() / "web-assets" / f"pdfjs-{VERSION}"

    @property
    def ready(self) -> bool:
        try:
            return self.directory.resolve(strict=True) == self.directory and all(
                (self.directory / name).is_file() for name in _REQUIRED_ASSETS
            )
        except OSError:
            return False

    def install(self) -> None:
        if self.ready:
            return
        cache = self.directory.parent
        cache.mkdir(mode=0o700, exist_ok=True)
        if cache.is_symlink() or self.directory.is_symlink():
            raise ValueError("Invalid PDF.js storage directory.")
        payload = _download()
        digest = base64.b64encode(sha512(payload).digest()).decode("ascii")
        if digest != ARCHIVE_SHA512:
            raise ValueError("PDF.js download failed its integrity check.")
        with TemporaryDirectory(prefix=".pdfjs-", dir=cache) as temporary:
            staged = Path(temporary) / "runtime"
            staged.mkdir()
            _extract(payload, staged)
            try:
                staged.rename(self.directory)
            except OSError:
                # Another reader may have installed the same immutable version.
                if not self.ready:
                    raise

    def resource(self, name: str) -> tuple[str, bytes]:
        mime = _asset_type(name)
        if mime is None or not self.ready:
            raise FileNotFoundError(name)
        path = self.directory.joinpath(*name.split("/"))
        if path.resolve(strict=True) != path or not path.is_file():
            raise FileNotFoundError(name)
        with path.open("rb") as source:
            data = source.read(MAX_ASSET + 1)
        if len(data) > MAX_ASSET:
            raise FileNotFoundError(name)
        return mime, data

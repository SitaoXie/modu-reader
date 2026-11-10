"""Exercise loopback access controls and durable Web reader state."""

import json
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

import pytest

from modu.library import Library
from modu.web_reader import serve


def test_local_entry_keeps_root_url_and_blocks_cross_origin_bootstrap(tmp_path):
    library = Library(tmp_path / "library")
    with serve(library, port=0) as url:
        assert urlsplit(url).hostname == "127.0.0.1"
        assert urlsplit(url).path == "/"
        request = Request(url, headers={"Sec-Fetch-Site": "none", "Sec-Fetch-Dest": "document"})
        with urlopen(request, timeout=3) as response:
            assert response.geturl() == url
            assert response.headers["Cache-Control"] == "no-store"
            module = re.search(rb'src="(/[\w-]+/web\.js)"', response.read())[1].decode()

        with urlopen(url + module[1:].removesuffix("web.js") + "api/shelf", timeout=3) as response:
            assert json.load(response)["books"] == []
        with pytest.raises(HTTPError, match="404"):
            urlopen(url + "api/shelf", timeout=3)
        for headers in (
            {"Sec-Fetch-Site": "cross-site"},
            {"Sec-Fetch-Site": "same-site"},
            {"Sec-Fetch-Dest": "iframe"},
            {"Origin": "https://wrong.test"},
            {"Host": "wrong.test"},
        ):
            with pytest.raises(HTTPError, match="403"):
                urlopen(Request(url, headers=headers), timeout=3)


def test_web_reader_uses_private_capability_and_same_origin(tmp_path):
    library = Library(tmp_path / "library")
    original = tmp_path / "window.txt"
    original.write_text("A quiet evening. <script>original text</script>", encoding="utf-8")
    book, _ = library.import_file(original)
    with serve(library, book) as url:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        def fetch(path, *, headers=None, data=None, base=url):
            request = Request(base + path, headers=headers or {}, data=data)
            try:
                return urlopen(request, timeout=3)
            except HTTPError as error:
                return error

        with fetch("api/shelf", base=origin + "/") as response:
            assert response.status == 404
        with fetch("api/shelf", headers={"Host": "wrong.test"}) as response:
            assert response.status == 403
        route = f"book/{book}"
        with fetch(route + "/text/0") as response:
            assert response.status == 200
            assert b"&lt;script&gt;original text&lt;/script&gt;" in response.read()
            assert "sandbox allow-same-origin" in response.headers["Content-Security-Policy"]
            assert response.headers["Cache-Control"] == "no-store"

        spot = {"index": 0, "scroll": 0.4}
        data = json.dumps(spot).encode()
        headers = {"Content-Type": "application/json", "Origin": "https://wrong.test"}
        with fetch(route + "/position", headers=headers, data=data) as response:
            assert response.status == 403
        assert library.setting("web:last_book") is None

        headers["Origin"] = origin
        with fetch(route + "/position", headers=headers, data=data) as response:
            assert response.status == 200
        with fetch(route + "/mark", headers=headers, data=data) as response:
            assert json.load(response)["marks"] == [spot]
        assert library.setting("web:last_book") == book
        with fetch(route) as response:
            assert json.load(response)["position"] == spot

        library.set_setting(f"translation_target:{book}", "ja")
        with fetch(route + "/delete", headers=headers, data=b"{}") as response:
            assert response.status == 200
        assert original.is_file()
        for key in ("web:last_book", f"web:position:{book}", f"web:marks:{book}", f"translation_target:{book}"):
            assert library.setting(key) is None
        with fetch(route + "/position", headers=headers, data=data) as response:
            assert response.status == 404

"""Translation preferences, on-device inference, and opt-in web providers."""

from __future__ import annotations

import ctypes
from functools import lru_cache
import hashlib
from http.client import HTTPException
import json
import locale
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
from threading import Lock
import time
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import BadZipFile, ZipFile

from bs4 import BeautifulSoup
from platformdirs import user_cache_path


LANGUAGES = {
    "en": "English",
    "zh-Hans": "简体中文",
    "zh-Hant": "繁體中文",
    "ja": "日本語",
    "ko": "한국어",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "ru": "Русский",
    "ar": "العربية",
    "hi": "हिन्दी",
    "vi": "Tiếng Việt",
}

# Versioned packages on the official Argos model CDN. Each row pins both
# directions with English, which is the pivot for other combinations.
_MODELS = {
    "zh-Hans": ("zh", "1_9", "1_9"),
    "zh-Hant": ("zt", "1_9", "1_9"),
    "ja": ("ja", "1_1", "1_1"),
    "ko": ("ko", "1_1", "1_1"),
    "fr": ("fr", "1_9", "1_9"),
    "de": ("de", "1_3", "1_3"),
    # The earlier Spanish model uses the same SentencePiece format as the rest.
    "es": ("es", "1_0", "1_0"),
    "it": ("it", "1_0", "1_0"),
    "pt": ("pt", "1_9", "1_9"),
    "ru": ("ru", "1_9", "1_9"),
    "ar": ("ar", "1_0", "1_0"),
    "hi": ("hi", "1_1", "1_1"),
    "vi": ("vi", "1_9", "1_9"),
}
_ARCHIVE_DIGESTS = {
    "translate-en_zh-1_9": "433e7c4f034d87fbe2353161e05f18646d7999452f801a4e1f0378522b9850ab",  # pragma: allowlist secret
    "translate-en_ja-1_1": "16300cc4eaa85320520cabcf433b63d01be40ef6966251de72043a083408f716",  # pragma: allowlist secret
    "translate-es_en-1_0": "1b963aa0e0cb6e5ce874f0aa1a1949a19bc4d762e833532239a8834340f6b378",  # pragma: allowlist secret
}
_MODEL_FILES = {
    "sentencepiece.model",
    "model/model.bin",
    "model/config.json",
    "model/shared_vocabulary.json",
    "model/shared_vocabulary.txt",
    "model/source_vocabulary.json",
    "model/source_vocabulary.txt",
    "model/target_vocabulary.json",
    "model/target_vocabulary.txt",
}
_REQUIRED_FILES = {"sentencepiece.model", "model/model.bin"}
MODEL_CACHE = user_cache_path("MODU", appauthor=False) / "translation"
MAX_SELECTION = 600
PROVIDERS = {"local", "youdao", "google"}
_GOOGLE_LANGUAGES = {"zh-Hans": "zh-CN", "zh-Hant": "zh-TW"}
_YOUDAO_LANGUAGES = {"en": "EN", "ja": "JA", "ko": "KR", "fr": "FR", "ru": "RU", "es": "SP"}
_MAX_WEB_RESPONSE = 256 * 1024
_MAX_ARCHIVE = 192 * 1024 * 1024
_MAX_EXPANDED = 384 * 1024 * 1024
_LOCK = Lock()


class TranslationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _language_code(value: object) -> str:
    if not isinstance(value, str):
        return ""
    parts = value.strip().replace("_", "-").lower().split(".", 1)[0].split("-")
    if parts[0] == "zh":
        return "zh-Hant" if {"hant", "cht", "tw", "hk", "mo"}.intersection(parts) else "zh-Hans"
    if parts[0] == "zt":
        return "zh-Hant"
    return parts[0] if parts[0] in LANGUAGES else ""


def _mac_language() -> str:
    cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cf.CFLocaleCopyPreferredLanguages.restype = ctypes.c_void_p
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFStringGetCString.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32
    ]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    cf.CFRelease.restype = None
    languages = cf.CFLocaleCopyPreferredLanguages()
    if not languages:
        return ""
    try:
        if cf.CFArrayGetCount(languages) < 1:
            return ""
        language = cf.CFArrayGetValueAtIndex(languages, 0)
        output = ctypes.create_string_buffer(128)
        if cf.CFStringGetCString(language, output, len(output), 0x08000100):  # UTF-8
            return output.value.decode("utf-8")
        return ""
    finally:
        cf.CFRelease(languages)


@lru_cache(maxsize=1)
def system_target() -> str:
    """Use the OS language, independently from the reader's interface setting."""
    try:
        if sys.platform == "darwin":
            system_language = _mac_language()
        elif sys.platform == "win32":
            language_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            system_language = locale.windows_locale.get(language_id, "")
        else:
            system_language = ""
        if system_language:
            return _language_code(system_language) or "en"
        for key in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
            value = os.environ.get(key)
            if value:
                return _language_code(value.split(":", 1)[0]) or "en"
        return _language_code(locale.getlocale()[0]) or "en"
    except (OSError, AttributeError, ValueError):
        return "en"


def settings_for(library, book_id: str | None) -> dict[str, str]:
    system = system_target()
    global_target = _language_code(library.setting("translation_target"))
    book_target = ""
    if book_id is not None:
        book_target = _language_code(library.setting(f"translation_target:{book_id}"))
    return {
        "system_target": system,
        "global_target": global_target,
        "book_target": book_target,
        "target": book_target or global_target or system,
    }


def set_target(library, book_id: str | None, value: str) -> None:
    """An empty value follows the global setting or system language."""
    if not isinstance(value, str) or (value and value not in LANGUAGES):
        raise TranslationError("unsupported_language")
    if book_id is None:
        library.set_setting("translation_target", value)
        return
    with library.connect() as connection:
        saved = connection.execute(
            "INSERT OR REPLACE INTO settings SELECT ?, ? WHERE EXISTS "
            "(SELECT 1 FROM books WHERE id=?)",
            (f"translation_target:{book_id}", json.dumps(value), book_id),
        )
        if not saved.rowcount:
            raise TranslationError("invalid_book")


def options_for(library) -> dict[str, str | bool]:
    provider = library.setting("translation_provider")
    return {
        "provider": provider if isinstance(provider, str) and provider in PROVIDERS else "local",
        "automatic": library.setting("translation_automatic") is True,
    }


def set_option(library, data: dict) -> dict[str, str | bool]:
    if data.keys() == {"provider"} and isinstance(data["provider"], str) and data["provider"] in PROVIDERS:
        library.set_setting("translation_provider", data["provider"])
    elif data.keys() == {"automatic"} and type(data["automatic"]) is bool:
        library.set_setting("translation_automatic", data["automatic"])
    else:
        raise ValueError("Invalid translation preference")
    return options_for(library)


def _guess_source(text: str) -> str:
    for pattern, code in (
        (r"[\u3040-\u30ff\uff66-\uff9d]", "ja"),
        (r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]", "ko"),
        (r"[\u3400-\u9fff\uf900-\ufaff]", "zh-Hans"),
        (r"[\u0400-\u052f]", "ru"),
        (r"[\u0600-\u06ff]", "ar"),
        (r"[\u0900-\u097f]", "hi"),
    ):
        if re.search(pattern, text):
            return code
    return "en"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _web_response(request: Request) -> bytes:
    try:
        with build_opener(_NoRedirect()).open(request, timeout=8) as response:
            data = response.read(_MAX_WEB_RESPONSE + 1)
        if len(data) <= _MAX_WEB_RESPONSE:
            return data
    except (HTTPException, OSError, ValueError):
        pass
    raise TranslationError("web_translation_failed") from None


def pronunciation(text: str) -> bytes:
    if not isinstance(text, str) or not 0 < len(text.strip()) <= 200:
        raise TranslationError("speech_too_long")
    request = Request(  # nosec B310
        "https://dict.youdao.com/dictvoice?" + urlencode({"audio": text.strip(), "type": "2"})
    )
    try:
        data = _web_response(request)
        if data.startswith(b"ID3") or (len(data) > 2 and data[0] == 255 and data[1] & 224 == 224):
            return data
    except TranslationError:
        pass
    raise TranslationError("speech_failed")


def _google(text: str, source: str, target: str) -> tuple[str, str]:
    params = urlencode({
        "client": "gtx", "dt": "t", "q": text,
        "sl": _GOOGLE_LANGUAGES.get(source, source or "auto"),
        "tl": _GOOGLE_LANGUAGES.get(target, target),
    })
    # Consumer web interface. Its response format can change independently of MODU.
    request = Request("https://translate.googleapis.com/translate_a/single?" + params)  # nosec B310
    try:
        result = json.loads(_web_response(request))
        translated = "".join(part[0] for part in result[0] if isinstance(part[0], str))
        if translated.strip():
            return translated, _language_code(result[2]) or source
    except TranslationError:
        raise
    except (IndexError, KeyError, TypeError, ValueError):
        pass
    raise TranslationError("web_translation_failed") from None


def _youdao(text: str, source: str, target: str) -> str:
    if source == "zh-Hans" and target in _YOUDAO_LANGUAGES:
        pair = "ZH_CN2" + _YOUDAO_LANGUAGES[target]
    elif target == "zh-Hans" and source in _YOUDAO_LANGUAGES:
        pair = _YOUDAO_LANGUAGES[source] + "2ZH_CN"
    else:
        raise TranslationError("youdao_language_pair")
    # Submit the same public form as the mobile translation page.
    request = Request(  # nosec B310
        "https://m.youdao.com/translate",
        data=urlencode({"inputtext": text, "type": pair}).encode("ascii"),
    )
    result = BeautifulSoup(_web_response(request), "html.parser").select_one("#translateResult")
    if result is not None and (translated := result.get_text("\n", strip=True)):
        return translated
    raise TranslationError("web_translation_failed")


def _download_model(name: str, archive: Path) -> None:
    # Only a known model name is sent, independently of the selected text.
    url = f"https://argos-net.com/v1/{name}.argosmodel"
    deadline = time.monotonic() + 90
    digest = hashlib.sha256()
    size = 0
    request = Request(url, headers={"User-Agent": "MODU/1.2", "Accept": "application/zip"})  # nosec B310
    with build_opener(_NoRedirect()).open(request, timeout=15) as response, archive.open("xb") as out:
        while chunk := response.read1(1024 * 1024):
            size += len(chunk)
            if size > _MAX_ARCHIVE or time.monotonic() > deadline:
                raise ValueError("Model download exceeded its limit")
            digest.update(chunk)
            out.write(chunk)
    expected = _ARCHIVE_DIGESTS.get(name)
    if expected and digest.hexdigest() != expected:
        raise ValueError("Unexpected model checksum")


def _extract_model(archive: Path, output: Path, source: str, target: str, version: str) -> None:
    with ZipFile(archive) as package:
        names: dict[str, str] = {}
        top_level = set()
        total = 0
        for member in package.infolist():
            path = PurePosixPath(member.filename)
            kind = stat.S_IFMT(member.external_attr >> 16)
            if (
                not path.parts
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in member.filename
                or ":" in member.filename
                or member.flag_bits & 1
                or kind not in (0, stat.S_IFDIR, stat.S_IFREG)
            ):
                raise ValueError("Invalid model archive member")
            top_level.add(path.parts[0])
            if member.is_dir():
                continue
            total += member.file_size
            relative = "/".join(path.parts[1:])
            if not relative or relative in names or total > _MAX_EXPANDED:
                raise ValueError("Invalid model archive contents")
            names[relative] = member.filename
        if len(top_level) != 1 or not _REQUIRED_FILES.issubset(names):
            raise ValueError("Incomplete model archive")
        with package.open(names["metadata.json"]) as metadata_file:
            metadata = json.loads(metadata_file.read(16384))
        if (metadata["from_code"], metadata["to_code"], metadata["package_version"]) != (
            source, target, version.replace("_", ".")
        ):
            raise ValueError("Unexpected model language pair or version")
        # Models are data files only. Leave bundled Stanza/PyTorch data out.
        for name in _MODEL_FILES.intersection(names):
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with package.open(names[name]) as compressed, path.open("xb") as out:
                shutil.copyfileobj(compressed, out, length=1024 * 1024)


def _model_directory(source: str, target: str) -> Path:
    if source == "en":
        argos_source = "en"
        argos_target, _, version = _MODELS[target]
    else:
        argos_source, version, _ = _MODELS[source]
        argos_target = "en"
    name = f"translate-{argos_source}_{argos_target}-{version}"
    destination = MODEL_CACHE / name
    if destination.is_dir():
        return destination
    try:
        MODEL_CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix=".download-", dir=MODEL_CACHE) as staging:
            staging_path = Path(staging)
            archive = staging_path / "package.argosmodel"
            output = staging_path / "extracted"
            _download_model(name, archive)
            _extract_model(archive, output, argos_source, argos_target, version)
            try:
                output.rename(destination)
            except OSError:
                # A second MODU session may finish downloading the same model.
                if not destination.is_dir():
                    raise
    except (BadZipFile, KeyError, OSError, TypeError, ValueError):
        raise TranslationError("model_download") from None
    return destination


@lru_cache(maxsize=2)
def _engine(source: str, target: str):
    # Check the optional dependency before downloading a large model.
    try:
        from ctranslate2 import Translator
        from sentencepiece import SentencePieceProcessor
    except (ImportError, OSError):
        raise TranslationError("dependencies") from None
    model = _model_directory(source, target)
    return (
        Translator(str(model / "model"), device="cpu", inter_threads=1, intra_threads=2),
        SentencePieceProcessor(model_file=str(model / "sentencepiece.model")),
    )


def _translate_pair(text: str, source: str, target: str) -> str:
    translator, tokenizer = _engine(source, target)
    batches = []
    for sentence in re.split(r"(?<=[。！？])\s*|(?<=[.!?])\s+", text):
        tokens = tokenizer.encode(sentence.strip(), out_type=str)
        batches.extend(tokens[i : i + 120] for i in range(0, len(tokens), 120))
    if not batches:
        raise TranslationError("empty")
    translated = translator.translate_batch(
        batches, beam_size=4, max_input_length=120, max_decoding_length=240, replace_unknowns=True
    )
    decoded = " ".join(tokenizer.decode(result.hypotheses[0]) for result in translated)
    # Unknown-token replacement can leave a raw SentencePiece word marker.
    return " ".join(decoded.replace("▁", " ").split())


def translate_selection(
    library, book_id: str, text: str, source: str = "", provider: str = "local"
) -> dict[str, str]:
    if not isinstance(text, str) or not text.strip():
        raise TranslationError("empty")
    text = text.strip()
    if len(text) > MAX_SELECTION:
        raise TranslationError("too_long")
    if provider != options_for(library)["provider"]:
        raise TranslationError("translation_provider_changed")
    from_language = _language_code(source)
    if not isinstance(source, str) or (source and not from_language):
        raise TranslationError("unsupported_language")
    target = settings_for(library, book_id)["target"]
    if provider == "google":
        if from_language != target:
            text, from_language = _google(text, from_language, target)
        return {"text": text, "source": from_language, "target": target}
    from_language = from_language or _guess_source(text)
    if provider == "youdao":
        if from_language != target:
            text = _youdao(text, from_language, target)
        return {"text": text, "source": from_language, "target": target}
    if from_language != target:
        try:
            with _LOCK:
                if from_language != "en" and target != "en":
                    text = _translate_pair(text, from_language, "en")
                    text = _translate_pair(text, "en", target)
                else:
                    text = _translate_pair(text, from_language, target)
                if not text:
                    raise TranslationError("translation_failed")
        except TranslationError:
            raise
        except (OSError, RuntimeError, ValueError):
            raise TranslationError("translation_failed") from None
    return {"text": text, "source": from_language, "target": target}

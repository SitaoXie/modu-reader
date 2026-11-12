from concurrent.futures import ThreadPoolExecutor

import pytest

from modu.library import Library
from modu.vocabulary import Vocabulary
from modu import translation
from modu import vocabulary


def test_vocabulary_persists_deduplicates_and_survives_book_deletion(tmp_path):
    library = Library(tmp_path / "library")
    source = tmp_path / "book.txt"
    source.write_text("A quiet room.", encoding="utf-8")
    book, _ = library.import_file(source)
    words = Vocabulary(library)
    entry = {"word": "Quiet", "source": "en", "target": "zh-Hans", "translation": "安静的"}
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: words.update(entry), range(8)))
    assert len(words.entries()) == 1
    words.update({**entry, "word": "quiet", "translation": "宁静的"})
    words.update({**entry, "target": "fr", "translation": "calme"})
    library.delete_book(book)
    reopened = Vocabulary(Library(library.root))
    assert len(reopened.entries()) == 2
    english = next(row for row in reopened.entries() if row["target"] == "zh-Hans")
    assert english["word_key"] == "quiet" and english["translation"] == "宁静的"
    reopened.update({**entry, "remove": True})
    assert len(reopened.entries()) == 1


@pytest.mark.parametrize("word", ["two words", "<script>", "", "x" * 81, 12])
def test_vocabulary_rejects_invalid_words(tmp_path, word):
    words = Vocabulary(Library(tmp_path))
    with pytest.raises(ValueError):
        words.update({"word": word, "source": "en", "target": "zh-Hans", "translation": "test"})
    assert words.entries() == []


def test_pronunciation_is_bounded_and_rejects_html(monkeypatch):
    monkeypatch.setattr(translation, "_web_response", lambda _: b"ID3audio")
    assert translation.pronunciation("quiet") == b"ID3audio"
    with pytest.raises(translation.TranslationError, match="speech_too_long"):
        translation.pronunciation("x" * 201)
    monkeypatch.setattr(translation, "_web_response", lambda _: b"<html>unavailable</html>")
    with pytest.raises(translation.TranslationError, match="speech_failed"):
        translation.pronunciation("quiet")


def test_phonetics_are_cached_and_local_mode_needs_explicit_lookup(tmp_path, monkeypatch):
    words = Vocabulary(Library(tmp_path))
    calls = []

    def lookup(word):
        calls.append(word)
        return {"uk": "ˈkwaɪət", "us": "ˈkwaɪət"}

    monkeypatch.setattr(vocabulary, "word_phonetics", lookup)
    assert words.phonetics({"word": "quiet", "lookup": False}) == {}
    assert calls == []
    expected = words.phonetics({"word": "Quiet", "lookup": True})
    reopened = Vocabulary(Library(tmp_path))
    assert reopened.phonetics({"word": "QUIET", "lookup": False}) == expected
    assert reopened.phonetics({"word": "quiet", "lookup": True}) == expected
    assert calls == ["quiet"]
    assert words.phonetics({"word": "安静", "lookup": True}) == {}


def test_phonetics_require_matching_dictionary_word(monkeypatch):
    import json
    entry = {"return-phrase": {"l": {"i": "quiet"}}, "ukphone": "ˈkwaɪət", "usphone": "ˈkwaɪət"}
    monkeypatch.setattr(translation, "_web_response", lambda _: json.dumps({"ec": {"word": [entry]}}).encode())
    assert translation.word_phonetics("quiet") == {"uk": "ˈkwaɪət", "us": "ˈkwaɪət"}
    assert translation.word_phonetics("unrecognizedword") == {}


def test_pronunciation_uses_requested_accent(monkeypatch):
    from urllib.parse import parse_qs, urlsplit
    requests = []
    monkeypatch.setattr(translation, "_web_response", lambda request: requests.append(request) or b"ID3audio")
    for accent in ("uk", "us"):
        assert translation.pronunciation("quiet", accent) == b"ID3audio"
    assert [parse_qs(urlsplit(request.full_url).query)["type"] for request in requests] == [["1"], ["2"]]
    with pytest.raises(ValueError, match="Invalid accent"):
        translation.pronunciation("quiet", "other")

import json
from zipfile import ZipFile

import pytest

from modu.library import Library
from modu import translation
from modu.translation import TranslationError


def test_system_global_and_book_translation_settings(tmp_path, monkeypatch):
    library = Library(tmp_path / "library")
    book_ids = []
    for number in (1, 2):
        source = tmp_path / f"Book {number}.txt"
        source.write_text(f"An original book {number}.", encoding="utf-8")
        book_id, _ = library.import_file(source)
        book_ids.append(book_id)
    first, second = book_ids
    monkeypatch.setattr(translation, "system_target", lambda: "zh-Hant")
    library.set_setting("language", "en")
    assert translation.settings_for(library, first)["target"] == "zh-Hant"
    translation.set_target(library, None, "fr")
    translation.set_target(library, first, "ja")
    reopened = Library(library.root)
    assert translation.settings_for(reopened, first)["target"] == "ja"
    assert translation.settings_for(reopened, second)["target"] == "fr"
    translation.set_target(reopened, first, "")
    assert translation.settings_for(reopened, first)["target"] == "fr"
    translation.set_target(reopened, None, "")
    assert translation.settings_for(reopened, first)["target"] == "zh-Hant"
    with pytest.raises(TranslationError, match="unsupported_language"):
        translation.set_target(reopened, first, "unsupported")
    with pytest.raises(TranslationError, match="invalid_book"):
        translation.set_target(reopened, "f" * 64, "ja")


def test_translate_selection_uses_override_and_source_language(tmp_path, monkeypatch):
    library = Library(tmp_path)
    library.set_setting("translation_target", "zh-Hant")
    pairs = []

    def translate(text, source, target):
        pairs.append((text, source, target))
        return target

    monkeypatch.setattr(translation, "_translate_pair", translate)
    result = translation.translate_selection(library, "a" * 64, "Bonjour", "fr-FR")
    assert pairs == [("Bonjour", "fr", "en"), ("en", "en", "zh-Hant")]
    assert result == {"text": "zh-Hant", "source": "fr", "target": "zh-Hant"}
    with pytest.raises(TranslationError, match="too_long"):
        translation.translate_selection(library, "a" * 64, "x" * 601)


@pytest.mark.parametrize("bad_path", ["package/../../outside", "package/model/escape\\file"])
def test_model_extraction_rejects_traversal(tmp_path, bad_path):
    archive = tmp_path / "model.argosmodel"
    with ZipFile(archive, "w") as package:
        package.writestr("package/metadata.json", json.dumps({
            "from_code": "en", "to_code": "zh", "package_version": "1.9"
        }))
        for name in translation._REQUIRED_FILES:
            package.writestr("package/" + name, "model fixture")
        package.writestr(bad_path, "unexpected")
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="Invalid model archive member"):
        translation._extract_model(archive, output, "en", "zh", "1_9")
    assert not output.exists()

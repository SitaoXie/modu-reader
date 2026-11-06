"""English words, contractions and source offsets across terminal reflow."""

import re

import pytest
from rich.cells import cell_len
from modu.model import wrap


@pytest.mark.parametrize("width", [12, 16, 24, 32, 40, 48, 64, 80])
def test_english_words_contractions_and_spaces_stay_intact(width):
    text = (
        "A quiet evening: don't forget Jim’s note. You’ll find it by the café; "
        "she doesn’t mind. Keep ’em a while, and read the résumé tomorrow. "
        "The extraordinary conversation continued until midnight. "
    ) * 3
    lines = wrap(text, width)
    assert "".join(line.text for line in lines) == text
    assert all(cell_len(line.text) <= width for line in lines)
    assert all(a.end == b.start for a, b in zip(lines, lines[1:]))
    boundaries = {line.end for line in lines[:-1]}
    for token in re.finditer(
        r"['’]?[A-Za-zÀ-ž\u0300-\u036f]+(?:['’][A-Za-zÀ-ž\u0300-\u036f]+)*", text
    ):
        if cell_len(token[0]) <= width:
            assert not any(token.start() < cut < token.end() for cut in boundaries), (
                width,
                token[0],
            )


def test_long_tokens_and_mixed_cjk_remain_lossless():
    text = "中文与 English words：don't stop，继续读。 " + "https://example.com/" + "a" * 250
    for width in (12, 24, 40, 80):
        lines = wrap(text, width)
        assert "".join(line.text for line in lines) == text
        assert all(cell_len(line.text) <= width for line in lines)


@pytest.mark.parametrize("heading", ["第一章 雨停以前", "Chapter 1"])
def test_title_followed_by_chapter_is_not_an_author(tmp_path, heading):
    from modu.parsers import parse_file

    book = tmp_path / "Book.txt"
    book.write_text("Book\n\n" + heading + "\n\nA reader opened the book.", encoding="utf-8")
    document = parse_file(book)
    assert document.author == ""
    assert heading in [label for _, label in document.chapters]

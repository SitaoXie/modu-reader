"""Persistent, library-wide vocabulary, independent of a book's lifetime."""

import time
import unicodedata

import regex

from .translation import LANGUAGES, word_phonetics


def word_key(value):
    if not isinstance(value, str):
        raise ValueError("Invalid word")
    value = unicodedata.normalize("NFC", value.strip()).replace("’", "'")
    if len(value) > 80 or not regex.fullmatch(r"\p{L}[\p{L}\p{M}]*(?:['-][\p{L}\p{M}]+)*", value):
        raise ValueError("Select a single word")
    return value.lower()


class Vocabulary:
    def __init__(self, library):
        self.library = library
        with library.connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS vocabulary (
                    word_key TEXT, source TEXT, target TEXT, word TEXT,
                    translation TEXT, created REAL,
                    PRIMARY KEY (word_key, source, target)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS phonetics (
                    word_key TEXT PRIMARY KEY, uk TEXT, us TEXT
                )
            """)

    def phonetics(self, data):
        key = word_key(data.get("word"))
        if not regex.fullmatch(r"[a-z]+(?:['-][a-z]+)*", key):
            return {}
        with self.library.connect() as connection:
            row = connection.execute("SELECT uk, us FROM phonetics WHERE word_key=?", (key,)).fetchone()
        if row is not None:
            return {accent: row[accent] for accent in ("uk", "us") if row[accent]}
        if data.get("lookup") is not True:
            return {}
        result = word_phonetics(key)
        if result:
            with self.library.connect() as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO phonetics VALUES (?, ?, ?)",
                    (key, result.get("uk"), result.get("us")),
                )
        return result

    def entries(self):
        with self.library.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM vocabulary ORDER BY created DESC, word_key"
            )]

    def update(self, data):
        key = word_key(data.get("word"))
        source, target = data.get("source"), data.get("target")
        if not isinstance(source, str) or source not in LANGUAGES or not isinstance(target, str) or target not in LANGUAGES:
            raise ValueError("Invalid language")
        with self.library.connect() as connection:
            if data.get("remove") is True:
                connection.execute(
                    "DELETE FROM vocabulary WHERE word_key=? AND source=? AND target=?",
                    (key, source, target),
                )
            else:
                meaning = data.get("translation")
                if not isinstance(meaning, str) or not 0 < len(meaning.strip()) <= 4000:
                    raise ValueError("Invalid translation")
                connection.execute("""
                    INSERT INTO vocabulary VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(word_key, source, target) DO UPDATE SET
                    word=excluded.word, translation=excluded.translation
                """, (key, source, target, data["word"].strip(), meaning.strip(), time.time()))
        return self.entries()

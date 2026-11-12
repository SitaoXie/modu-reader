import asyncio

import pytest
from textual.widgets import Button, Input, Select, Static

from modu.app import ModuApp
from modu.library import Library
from modu.reader import Reader
from modu.terminal_translation import TranslationModal, TranslationSettings
from modu.translation import set_target, settings_for


@pytest.fixture
def library(tmp_path):
    path = tmp_path / 'sample.txt'
    path.write_text('Chapter 1\n中文，“quiet” e\u0301 quiet quietly QUIET.\n' + ('A quiet room, a peaceful evening.\n' * 45))
    library = Library(tmp_path / 'library')
    identifier, _ = library.import_file(path)
    set_target(library, None, 'zh-Hans')
    return library, identifier


async def test_terminal_translation_selection_toggle_and_settings(library, monkeypatch):
    library, identifier = library
    calls = []

    def translate(lib, book, text, source, provider):
        calls.append((book, text, provider))
        return {'text': '安静的', 'source': 'en', 'target': 'zh-Hans'}

    monkeypatch.setattr('modu.terminal_translation.translate_selection', translate)
    app = ModuApp(library, start_book=identifier)
    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.pause(.4)
        reader = app.query_one(Reader)
        row = next(i for i, value in enumerate(reader.rows) if '中文' in value[2])
        start = reader.rows[row][0]
        assert reader.offset_at(reader.left_margin + 1, row + 1) == start
        assert reader.offset_at(reader.left_margin + 2, row + 1) == start + 1
        reader.selection_start = app.doc.text.index('quiet')
        reader.selection_end = reader.selection_start + 5
        assert reader.selected_text == 'quiet'
        await pilot.press('f')
        await pilot.pause(.5)
        assert isinstance(app.screen, TranslationModal)
        assert calls[-1][1] == 'quiet'
        assert '安静' in str(app.screen.query_one('#lookup-meaning', Static).render())
        assert not app.screen.query_one('#lookup-save', Button).disabled
        app.screen.toggle()
        assert len(app.vocabulary.entries()) == 1
        assert 'quiet' in reader.saved_words
        spans = reader.row_words(start, reader.rows[row][1])
        assert len(spans) == 3  # Whole words, not quietly.
        app.screen.toggle()
        assert app.vocabulary.entries() == []
        app.screen.toggle()
        await pilot.press('escape')
        await pilot.press('w')
        await pilot.pause(.1)
        await pilot.press('tab', 'enter')
        await pilot.pause(.2)
        assert isinstance(app.screen, TranslationModal)
        assert not app.screen.query_one('#lookup-save', Button).disabled
        app.screen.toggle()
        assert app.vocabulary.entries() == []
        await pilot.press('escape', 'escape')
        app.push_screen(TranslationSettings())
        await pilot.pause(.2)
        app.screen.query_one('#translation-book', Select).value = 'fr'
        app.screen.query_one('#translation-engine', Select).value = 'google'
        await pilot.pause(.2)
        assert settings_for(library, identifier)['target'] == 'fr'
        assert settings_for(library, None)['target'] == 'zh-Hans'
        for size in [(44, 20), (100, 36), (60, 24)]:
            await pilot.resize_terminal(*size)
            await pilot.pause(.1)
            assert app.screen.query_one('#lookup-close').region.right <= size[0]
        await pilot.press('escape')
        assert reader.anchor == 0


async def test_stale_lookup_cannot_save_wrong_word(library, monkeypatch):
    library, identifier = library
    from threading import Event
    entered, release = Event(), Event()

    def translate(*args):
        entered.set()
        release.wait(4)
        return {'text': '安静', 'source': 'en', 'target': 'zh-Hans'}

    monkeypatch.setattr('modu.terminal_translation.translate_selection', translate)
    app = ModuApp(library, start_book=identifier)
    async with app.run_test(size=(80, 30)) as pilot:
        await pilot.pause(.3)
        app.push_screen(TranslationModal('quiet', automatic=True))
        await pilot.pause(.2)
        assert entered.is_set()
        app.screen.query_one(Input).value = 'peaceful'
        await pilot.pause(.1)
        release.set()
        await pilot.pause(.3)
        assert app.screen.result is None
        assert app.screen.query_one('#lookup-save', Button).disabled
        await pilot.press('escape')


async def test_audio_process_is_stopped_on_cancellation(monkeypatch):
    from modu.terminal_audio import play
    class Process:
        returncode = None
        killed = False
        async def communicate(self, data):
            await asyncio.sleep(100)
        def kill(self):
            self.killed = True
        async def wait(self):
            self.returncode = -9
    process = Process()
    async def launch(*args, **kwargs):
        return process
    monkeypatch.setattr('modu.terminal_audio.sys.platform', 'darwin')
    monkeypatch.setattr('asyncio.create_subprocess_exec', launch)
    task = asyncio.create_task(play('quiet'))
    await asyncio.sleep(.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed

"""Real PTY acceptance: mouse selection, cached words, IPA and durable preferences.

The upstream translator is replaced with a deterministic synthetic fixture. No
publication text or network service is used. ANSI output is decoded independently.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

import pexpect
import pyte


FIXTURE = r'''
import sys
from pathlib import Path
from modu.app import ModuApp
from modu.library import Library
import modu.terminal_translation as lookup
import modu.vocabulary as vocab
root=Path(sys.argv[1])
source=root/'sample.txt'
source.write_text('Chapter 1\n中文，“quiet” quietly QUIET.\n' + ('A quiet room and a peaceful evening.\n'*30))
library=Library(root/'library')
book,_=library.import_file(source)
library.set_setting('language','en')
library.set_setting('translation_provider','google')
library.set_setting('translation_automatic',len(sys.argv)>2)
library.set_setting('translation_target','zh-Hans')
def translate(lib, identifier, text, source, provider):
    with (root/'calls.jsonl').open('a') as stream:
        import json
        stream.write(json.dumps({'text':text,'provider':provider})+'\n')
    return {'text':'peaceful; without noise','source':'en','target':'zh-Hans'}
lookup.translate_selection=translate
vocab.word_phonetics=lambda word: {'uk':'kwaɪət','us':'kwaɪət'}
ModuApp(library,start_book=book).run()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--python', default=sys.executable)
    args = parser.parse_args()
    root = args.work.resolve()
    root.mkdir(parents=True, exist_ok=False)
    columns, rows = 112, 40
    screen = pyte.Screen(columns, rows)
    stream = pyte.Stream(screen)
    env = {**os.environ, 'TERM': 'xterm-256color', 'COLORTERM': 'truecolor', 'PYTHONUTF8': '1'}
    child = pexpect.spawn(args.python, ['-c', FIXTURE, str(root)], dimensions=(rows, columns), env=env, encoding='utf-8', timeout=5)

    def drain(seconds=.15):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            try:
                stream.feed(child.read_nonblocking(262144, timeout=.02).replace('\u2060', ''))
            except pexpect.TIMEOUT:
                pass

    def lines():
        return [''.join(screen.buffer[y][x].data or ' ' for x in range(screen.columns)) for y in range(screen.lines)]

    def find(text):
        for y, row in enumerate(lines()):
            if text in row:
                return row.index(text), y
        return None

    def wait(text):
        for _ in range(30):
            drain(.1)
            if find(text):
                return find(text)
        raise AssertionError('Not displayed: ' + text)

    def mouse(code, x, y, up=False):
        child.send(f'\x1b[<{code};{x+1};{y+1}{"m" if up else "M"}')
        drain(.08)

    def click(text):
        x, y = wait(text)
        mouse(0, x+1, y)
        mouse(0, x+1, y, True)

    try:
        x, y = wait('quiet')
        mouse(0, x, y)
        mouse(32, x+5, y)
        mouse(0, x+5, y, True)
        child.send('f')
        wait('peaceful; without noise')
        wait('kwaɪət')
        for _ in range(12):
            if find('Save word'):
                break
            mouse(65, 75, 25)
        click('Save word')
        wait('Saved · Press to remove')
        click('Saved · Press to remove')
        wait('Save word')
        click('Save word')
        child.send('\x1b')
        drain(.3)
        x, y = wait('quiet')
        assert screen.buffer[y][x].underscore, 'Saved word lacks an underline'
        mouse(0, x+1, y)
        mouse(0, x+1, y, True)
        wait('peaceful; without noise')
        assert len((root/'calls.jsonl').read_text().splitlines()) == 1, 'Cached word was translated again'
        child.send('\x1b')
        drain(.2)
        child.send('w')
        wait('Vocabulary')
        wait('peaceful; without noise')
        child.send('\x1b')
        drain(.2)
        child.send('q')
        child.expect(pexpect.EOF)
        from modu.library import Library
        from modu.vocabulary import Vocabulary
        library = Library(root/'library')
        assert len(Vocabulary(library).entries()) == 1
        assert library.setting('translation_target') == 'zh-Hans'
        calls = [json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
        assert calls[0]['text'] == 'quiet'
        screen.reset()
        child.close()
        child = pexpect.spawn(args.python, ['-c', FIXTURE, str(root), 'auto'], dimensions=(rows, columns), env=env, encoding='utf-8', timeout=5)
        x, y = wait('peaceful')
        mouse(0, x, y)
        mouse(32, x+8, y)
        assert len((root/'calls.jsonl').read_text().splitlines()) == 1
        mouse(0, x+8, y, True)
        wait('peaceful; without noise')
        calls = [json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
        assert calls[-1]['text'] == 'peaceful' and len(calls) == 2
        child.send('\x1b')
        drain(.2)
        child.send('q')
        child.expect(pexpect.EOF)
        print(json.dumps({'automatic_after_release': True, 'mouse_selection': True, 'ipa': True, 'toggle': True, 'cached_click': True, 'durable': True}))
    finally:
        (root/'last-screen.txt').write_text('\n'.join(lines()))
        child.close(force=True)


if __name__ == '__main__':
    main()

import zipfile

import pytest
from bs4 import BeautifulSoup

from modu.library import Library
from modu.web_reader import Reader
from modu.web_content import reading_options, scoped_css


def epub_library(tmp_path):
    source = tmp_path / 'sample.epub'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>')
        archive.writestr('book.opf', '<package><metadata><title>Sample</title></metadata><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="two.xhtml" media-type="application/xhtml+xml"/><item id="css" href="main.css" media-type="text/css"/></manifest><spine><itemref idref="one"/><itemref idref="two"/></spine></package>')
        archive.writestr('main.css', 'body {color:red} .body {color:blue} @media (min-width:1px) {html p{color:green}}')
        for name in ['one', 'two']:
            archive.writestr(name+'.xhtml', '<html><head><link rel="stylesheet" href="main.css"/></head><body><h1>'+name+'</h1><p>中文，qu<em>iet</em> quietly quiet.</p><script>alert(1)</script><img src="https://invalid.test/pixel"/></body></html>')
    library = Library(tmp_path/'library')
    identifier, _ = library.import_file(source)
    return Reader(library), identifier


def test_search_uses_original_spine_and_inline_text(tmp_path):
    reader, identifier = epub_library(tmp_path)
    data = reader.content.search(identifier, 'quiet')
    assert [(x['index'], x['occurrence']) for x in data['results']] == [(0,0),(0,1),(0,2),(1,0),(1,1),(1,2)]
    assert reader.content.search(identifier, '中文，quiet')['results'][0]['index'] == 0
    assert reader.content.search(identifier, 'alert')['results'] == []
    assert reader.content.search(identifier, '[')['results'] == []
    with pytest.raises(ValueError):
        reader.content.search(identifier, 'q'*201)


def test_flow_preserves_styles_without_enabling_publication_scripts(tmp_path):
    reader, identifier = epub_library(tmp_path)
    soup = BeautifulSoup(reader.content.section(identifier, 1, '/safe/'), 'html.parser')
    assert soup.select_one('[data-modu-section="1"] .modu-body em').text == 'iet'
    assert soup.script is None
    assert not soup.img.get('src')
    css = soup.style.text
    assert '[data-modu-section="1"] .modu-body ' in css
    assert '[data-modu-section="1"] .body ' in css
    assert '[data-modu-section="1"] .modu-html p' in css
    assert 'https://' not in css


def test_scoped_css_handles_import_cycles_and_selectors():
    calls = []
    def importer(url):
        calls.append(url)
        return '@import "same"; body {margin:0}'
    text = scoped_css('@import "same"; :root, .body, [title="body"] {color:red} @supports(display:grid){body{display:grid}}', '#section', importer)
    assert calls == ['same']
    assert '#section .modu-html' in text
    assert '#section  .body' in text
    assert '[title="body"]' in text
    assert '@supports' in text
    assert '<' not in scoped_css('p::before{content:"</style>"}', '#section', importer)


def test_reading_settings_validate_before_mutation(tmp_path):
    library = Library(tmp_path)
    assert reading_options(library) == {'read_width':80,'spacing':1,'chapter_breaks':True}
    assert reading_options(library, {'chapter_breaks':False})['chapter_breaks'] is False
    for data in [{'read_width':True}, {'spacing':-1}, {'chapter_breaks':1}, {'read_width':64,'spacing':99}, {'extra':'value'}]:
        with pytest.raises(ValueError):
            reading_options(library, data)
    assert reading_options(Library(tmp_path))['read_width'] == 80


def test_plain_text_flow_and_search(tmp_path):
    path=tmp_path/'sample.txt'
    path.write_text('An introductory note before the first heading.\n\nChapter 1\nA qu<iet room.\nChapter 2\nA quiet night.')
    library=Library(tmp_path/'library')
    identifier,_=library.import_file(path)
    reader=Reader(library)
    assert reader.content.search(identifier,'introductory note')['results'][0]['index'] == 0
    assert reader.content.search(identifier,'quiet')['results'][0]['index'] == 1
    assert 'qu&lt;iet' in reader.content.section(identifier,0,'/safe/')
    assert reader.content.search(identifier,'qu<iet')['results'][0]['index'] == 0

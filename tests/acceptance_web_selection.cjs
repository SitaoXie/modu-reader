/** Real-browser regression for translation gestures and book image zoom. */
const {spawn} = require('node:child_process');
const readline = require('node:readline');
const {parseArgs} = require('node:util');
const assert = require('node:assert/strict');
const path = require('node:path');
const {values} = parseArgs({options:{
  python:{type:'string'}, modules:{type:'string'}, browser:{type:'string'}, work:{type:'string'},
}});
for (const key of ['python','modules','browser','work']) {
  if (!values[key]) throw Error('Missing --' + key);
}
const {chromium} = require(path.join(path.resolve(values.modules), 'playwright-core'));
const fixture = String.raw`
import sys
from pathlib import Path
from threading import Event
from zipfile import ZipFile

from modu import translation
from modu.library import Library
from modu.web_reader import serve

work = Path(sys.argv[1]).resolve()
work.mkdir(parents=True, exist_ok=True)
source = work / "Illustrated Book.epub"
with ZipFile(source, "w") as archive:
    archive.writestr("META-INF/container.xml", """<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>""")
    archive.writestr("book.opf", """<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Illustrated Book</dc:title><dc:language>en</dc:language></metadata>
    <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
    <item id="plate" href="plate.svg" media-type="image/svg+xml"/></manifest>
    <spine><itemref idref="chapter"/></spine></package>""")
    archive.writestr("chapter.xhtml", """<html xmlns="http://www.w3.org/1999/xhtml"><head>
    <style>body { margin: 1rem; font: 16px/1.6 sans-serif; } img { width: 160px; }</style></head>
    <body><p id="line">A quiet room is a good place to read.</p>
    <p id="repeat">QUIET quietly qu<em>iet</em></p>
    <img src="plate.svg" alt="A blue illustration"/>
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 50" width="80" height="50">
    <image href="plate.svg" width="80" height="50"/></svg></body></html>""")
    archive.writestr("plate.svg", """<svg xmlns="http://www.w3.org/2000/svg" width="960" height="600">
    <rect x="0" y="0" width="960" height="600" fill="#3978b1"/></svg>""")
library = Library(work / "library")
library.set_setting("language", "en")
library.set_setting("translation_target", "zh-Hans")
book, _ = library.import_file(source)
second = work / "Second Book.txt"
second.write_text("A QUIET place. Quietly is a different word.", encoding="utf-8")
library.import_file(second)
translation._google = lambda text, source, target: ("安静的房间是读书的好地方。", "en")
translation._youdao = lambda text, source, target: "安静的" if text.lower() == "quiet" else "适合读书的安静房间。"
with serve(library, book, port=0) as url:
    print(url, flush=True)
    Event().wait()
`;

(async () => {
  let browser;
  const server = spawn(values.python, ['-c', fixture, values.work], {stdio:['ignore','pipe','inherit']});
  try {
    const url = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(Error('Timed out waiting for fixture server')), 15000);
      server.once('error', reject);
      server.once('exit', code => reject(Error('Fixture server exited: ' + code)));
      readline.createInterface({input:server.stdout}).once('line', line => {
        clearTimeout(timeout);
        resolve(line);
      });
    });
    browser = await chromium.launch({executablePath:path.resolve(values.browser), headless:true});
    const page = await browser.newPage({viewport:{width:460,height:560}});
    page.setDefaultTimeout(7000);
    const requests = [];
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().endsWith('/translate')) requests.push(request.postDataJSON());
    });
    await page.goto(url);
    const chapter = page.frameLocator('#book-frame');
    await chapter.locator('#line').waitFor();
    async function dragText() {
      const rect = await chapter.locator('#line').evaluate(node => {
        const range = node.ownerDocument.createRange();
        range.selectNodeContents(node);
        const {left, right, top, height} = range.getBoundingClientRect();
        return {left, right, y:top + height / 2};
      });
      const frame = await page.locator('#book-frame').boundingBox();
      await page.mouse.move(frame.x + rect.left + 0.5, frame.y + rect.y);
      await page.mouse.down();
      await page.mouse.move(frame.x + rect.right + 2, frame.y + rect.y, {steps:12});
    }
    const settings = page.locator('#settings-button');
    const engine = page.getByRole('combobox', {name:'Translation engine'});
    const automatic = page.getByRole('checkbox', {name:'Translate automatically when selection ends'});
    const preview = page.locator('#selection-preview');
    await settings.click();
    assert.equal(await engine.inputValue(), 'local');
    assert.equal(await automatic.isChecked(), false);
    await engine.selectOption('google');
    await page.getByText(/Online translation sends/).waitFor();
    await page.keyboard.press('Escape');
    await dragText();
    await page.mouse.up();
    await page.locator('#selection').waitFor();
    assert.equal(requests.length, 0, 'Manual mode sent a request without a click');
    await page.locator('#selection').click();
    await page.locator('.translation-result').getByText('安静的房间是读书的好地方。').waitFor();
    await page.keyboard.press('Escape');
    await settings.click();
    await engine.selectOption('youdao');
    await page.waitForFunction(() => !document.querySelector('#dialog select').disabled);
    await automatic.check();
    await page.waitForFunction(() => !document.querySelector('#dialog input[type=checkbox]').disabled);
    await page.keyboard.press('Escape');
    await page.reload();
    await chapter.locator('#line').waitFor();
    await dragText();
    await page.waitForTimeout(380);
    assert.equal(requests.length, 1, 'Drag in progress sent a request');
    await page.mouse.up();
    await preview.getByText('适合读书的安静房间。').waitFor();
    await page.waitForTimeout(330);
    assert.deepEqual(requests, ['google', 'youdao'].map(provider => ({
      text:'A quiet room is a good place to read.', source:'en', provider,
    })));
    await preview.getByRole('button', {name:'Close'}).click();
    assert.equal(await preview.isVisible(), false);
    // Double-click an individual word, save it, and inspect all later matches.
    const quiet = await chapter.locator('#line').evaluate(node => {
      const range = node.ownerDocument.createRange();
      range.setStart(node.firstChild, 2);
      range.setEnd(node.firstChild, 7);
      const rect = range.getBoundingClientRect();
      return {x:rect.x + rect.width / 2, y:rect.y + rect.height / 2};
    });
    const frameBox = await page.locator('#book-frame').boundingBox();
    await page.mouse.dblclick(frameBox.x + quiet.x, frameBox.y + quiet.y);
    await preview.getByText('安静的', {exact:true}).waitFor();
    await preview.getByRole('button', {name:'Save word', exact:true}).click();
    await preview.getByRole('button', {name:'Word saved', exact:true}).waitFor();
    const highlighted = () => page.evaluate(() => {
      const win = document.querySelector('#book-frame').contentWindow;
      return [...win.CSS.highlights.get('modu-words')].map(range => range.toString());
    });
    assert.deepEqual(await highlighted(), ['quiet','QUIET','quiet']);
    const before = requests.length;
    await page.reload();
    await chapter.locator('#line').waitFor();
    await page.waitForFunction(() => document.querySelector('#book-frame').contentWindow.CSS.highlights.get('modu-words')?.size === 3);
    const repeat = await chapter.locator('#repeat').evaluate(node => {
      const range = node.ownerDocument.createRange();
      range.setStart(node.firstChild, 0);
      range.setEnd(node.firstChild, 5);
      const rect = range.getBoundingClientRect();
      return {x:rect.x + rect.width / 2, y:rect.y + rect.height / 2};
    });
    const frameAfter = await page.locator('#book-frame').boundingBox();
    await page.mouse.click(frameAfter.x + repeat.x, frameAfter.y + repeat.y);
    await preview.getByText('安静的', {exact:true}).waitFor();
    assert.equal(requests.length, before, 'Saved word made a new translation request');
    await preview.getByRole('button', {name:'Close'}).click();
    await page.getByRole('button', {name:'Vocabulary', exact:true}).click();
    await page.getByRole('button', {name:'quiet · 安静的', exact:true}).click();
    await page.getByRole('textbox', {name:'Meaning', exact:true}).fill('宁静的');
    await page.getByRole('button', {name:'Save', exact:true}).click();
    await page.getByRole('button', {name:'quiet · 宁静的', exact:true}).waitFor();
    await page.keyboard.press('Escape');
    for (const target of ['img', 'svg image']) {
      await chapter.locator(target).click();
      const enlarged = page.locator('.image-viewport img');
      await enlarged.waitFor();
      await page.getByRole('button', {name:'Zoom in', exact:true}).waitFor();
      await page.waitForFunction(() => document.querySelector('.image-viewport img').naturalWidth === 960
        && document.querySelector('.image-toolbar output').textContent.endsWith('%'));
      const size = () => enlarged.evaluate(node => node.getBoundingClientRect().width);
      const fit = await size();
      await page.getByRole('button', {name:'Zoom in', exact:true}).click();
      const zoomed = await size();
      assert.ok(zoomed > fit, `Zoom did not enlarge the ${target} from ${fit} px (got ${zoomed} px)`);
      await page.getByRole('button', {name:'Fit', exact:true}).click();
      assert.equal(await size(), fit);
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#dialog').isVisible(), false);
    }
    await page.locator('#back-button').click();
    await page.getByRole('button', {name:/Second Book/}).click();
    await page.waitForFunction(() => document.querySelector('#book-frame').contentWindow.CSS.highlights.get('modu-words')?.size === 1);
    assert.deepEqual(await highlighted(), ['QUIET']);
    await page.getByRole('button', {name:'Vocabulary', exact:true}).click();
    await page.getByRole('button', {name:'quiet · 宁静的', exact:true}).click();
    await page.getByRole('button', {name:'Delete', exact:true}).click();
    await page.getByRole('button', {name:'Delete', exact:true}).click();
    await page.getByText('No saved words yet.', {exact:false}).waitFor();
    assert.deepEqual(await highlighted(), []);
    console.log(JSON.stringify({width:460, requests:requests.length, autoAfterRelease:true, zoomedImages:2, vocabularyPersistence:true, wholeWordMatches:3, inlineWordMatch:true, crossBook:true, removal:true}));
  } finally {
    await browser?.close();
    server.kill();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

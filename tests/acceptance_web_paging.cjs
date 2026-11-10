/** Optional real-browser regression for page continuity and reading-frame keyboard events. */
const {spawn} = require('node:child_process');
const readline = require('node:readline');
const {parseArgs} = require('node:util');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {values} = parseArgs({options:{
  python:{type:'string'}, modules:{type:'string'}, browser:{type:'string'}, work:{type:'string'},
}});
for (const key of ['python','modules','browser','work']) {
  if (!values[key]) throw Error('Missing --' + key);
}
const work = path.resolve(values.work);
fs.mkdirSync(work);
const {chromium} = require(path.join(path.resolve(values.modules),'playwright-core'));
const fixture = String.raw`
import sys
from pathlib import Path
from threading import Event
from zipfile import ZipFile

from modu.library import Library
from modu.web_reader import serve

work = Path(sys.argv[1]).resolve()
work.mkdir(parents=True, exist_ok=True)
source = work / "Continuous Pages.epub"
container = """<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>
<rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>"""
opf = """<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Continuous Pages</dc:title><dc:language>en</dc:language></metadata>
<manifest><item id="first" href="first.xhtml" media-type="application/xhtml+xml"/><item id="second" href="second.xhtml" media-type="application/xhtml+xml"/></manifest>
<spine><itemref idref="first"/><itemref idref="second"/></spine></package>"""
with ZipFile(source, "w") as archive:
    archive.writestr("META-INF/container.xml", container)
    archive.writestr("book.opf", opf)
    for filename, start, end in (("first.xhtml", 1, 81), ("second.xhtml", 81, 118)):
        paragraphs = "".join(f'<p id="line-{i}">Line {i:03d} · 灯光，静静地亮着。</p>' for i in range(start, end))
        archive.writestr(filename, """<html xmlns="http://www.w3.org/1999/xhtml"><head>
<style>body { margin: 13px 17px 19px; font: 18px/29.5px system-ui; }
p { margin: 0; } p:nth-child(5n) { padding-bottom: 4px; }</style></head><body>""" + paragraphs + "</body></html>")
library = Library(work / "library")
library.set_setting("language", "en")
book, _ = library.import_file(source)
with serve(library, book, port=0) as url:
    print(url, flush=True)
    Event().wait()
`;
(async()=>{
  let browser;
  const server = spawn(values.python, ['-c', fixture, work], {stdio:['ignore','pipe','inherit']});
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
    browser = await chromium.launch({executablePath:path.resolve(values.browser),headless:true});
    const page = await browser.newPage({viewport:{width:460,height:515}});
    page.setDefaultTimeout(10000);
    await page.goto(url);
    await page.waitForFunction(()=>document.querySelector('#book-frame').contentDocument?.getElementById('line-1'));
    await page.waitForFunction(()=>!document.querySelector('#next').disabled);
    const snapshot=()=>page.evaluate(()=>{
      const frame=document.querySelector('#book-frame');
      const doc=frame.contentDocument;
      const cut=Number(frame.style.clipPath.split(/\s+/)[2]?.match(/([\d.]+)px/)?.[1] || 0);
      const bottom=frame.clientHeight-cut;
      const visible=[];
      const partial=[];
      for (const node of doc.querySelectorAll('[id^=line-]')) {
        const range=doc.createRange();
        range.selectNodeContents(node);
        const rect=range.getBoundingClientRect();
        const number=Number(node.id.split('-')[1]);
        if (rect.top >= -0.99 && rect.bottom <= bottom+0.99) visible.push(number);
        else if (rect.bottom > 1 && rect.top < bottom-1) partial.push(number);
      }
      return {visible,partial,top:doc.scrollingElement.scrollTop,cut,height:frame.clientHeight};
    });
    await page.frameLocator('#book-frame').locator('#line-1').click();
    // A listener from the reader window can handle keyboard events. An
    // inline script in the publication must still be blocked by its CSP.
    const executed=await page.evaluate(()=>{
      const doc=document.querySelector('#book-frame').contentDocument;
      const probe=doc.createElement('script');
      probe.textContent="document.body.dataset.pagingProbe='executed'";
      doc.body.append(probe);
      return doc.body.dataset.pagingProbe;
    });
    assert.equal(executed,undefined,'Publication script ran');
    const pages=[];
    for(let turn=0;turn<40;turn++) {
      const current=await snapshot();
      assert.ok(current.visible.length,'Empty screen');
      assert.deepEqual(current.partial,[],'Visible clipped text line');
      if(pages.length) assert.equal(current.visible[0],pages.at(-1).visible.at(-1)+1,'Skipped or duplicated line');
      pages.push(current);
      if(await page.locator('#next').isDisabled()) break;
      const previous=current.visible[0];
      if(turn%2===0) await page.keyboard.press('ArrowRight');
      else await page.click('#next');
      await page.waitForFunction(previous=>{
        const doc=document.querySelector('#book-frame').contentDocument;
        const line=doc?.getElementById('line-'+previous);
        return !line || line.getBoundingClientRect().bottom<0;
      },previous);
      await page.waitForTimeout(60);
    }
    assert.deepEqual(pages.flatMap(page=>page.visible),Array.from({length:117},(_,i)=>i+1));
    for(let index=pages.length-2;index>=0;index--){
      await page.keyboard.press('ArrowLeft');
      await page.waitForTimeout(80);
      assert.deepEqual((await snapshot()).visible,pages[index].visible,'Left did not restore exact page');
    }
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('ArrowRight');
    const anchor=(await snapshot()).visible[0];
    await page.setViewportSize({width:875,height:650});
    await page.waitForTimeout(200);
    const before=await snapshot();
    assert.equal(before.visible[0],anchor,"Resize changed the first line");
    await page.keyboard.press('PageDown');
    const after=await snapshot();
    assert.equal(after.visible[0],before.visible.at(-1)+1);
    console.log(JSON.stringify({screens:pages.length,lines:117,reverse:pages.length-1,resized:true}));
  } finally {
    await browser?.close();
    server.kill();
  }
})().catch(e=>{console.error(e);process.exitCode=1;});

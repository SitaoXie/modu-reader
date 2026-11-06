/** Render genuine PTY captures in an isolated xterm.js terminal. Not runtime code. */
const fs = require('node:fs');
const path = require('node:path');
const { parseArgs } = require('node:util');
const { values } = parseArgs({ options: {
  frames: { type: 'string' }, modules: { type: 'string' },
  browser: { type: 'string' }, output: { type: 'string' }
}});
for (const key of ['frames', 'modules', 'browser', 'output']) {
  if (!values[key]) throw new Error(`Missing --${key}`);
}
const modules = path.resolve(values.modules);
const { chromium } = require(path.join(modules, 'playwright-core'));
const xterm = path.join(modules, '@xterm/xterm');
if (require(path.join(xterm, 'package.json')).version !== '6.0.0') throw new Error('Use xterm.js 6.0.0');
(async () => {
  fs.mkdirSync(values.output, { recursive: true });
  const browser = await chromium.launch({ executablePath: path.resolve(values.browser), headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 2200, height: 1200 }, deviceScaleFactor: 2 });
    await page.route('**/*', route => route.abort());
    await page.setContent('<html><body style="margin:0"><div id="term" style="width:max-content"></div></body></html>');
    await page.addStyleTag({ path: path.join(xterm, 'css/xterm.css') });
    await page.addScriptTag({ path: path.join(xterm, 'lib/xterm.js') });
    const results = [];
    for (const frame of JSON.parse(fs.readFileSync(values.frames, 'utf8'))) {
      const result = await page.evaluate(async frame => {
        window.term?.dispose?.();
        const host = document.querySelector('#term'); host.innerHTML = '';
        const paper = frame.theme === 'modu-paper';
        window.term = new Terminal({ cols: frame.columns, rows: frame.rows,
          fontFamily: 'Menlo, ui-monospace, Consolas, monospace', fontSize: 16,
          theme: { background: paper ? '#f5f1e8' : '#121416', foreground: paper ? '#383c3c' : '#ddd6c8' },
          allowProposedApi: true, cursorBlink: false });
        term.open(host);
        await new Promise(resolve => setTimeout(resolve, 150));
        await new Promise(resolve => term.write(frame.ansi, resolve));
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const text = [...document.querySelectorAll('.xterm-rows>div')].map(row => row.textContent).join('\n').replaceAll('\u2060', '');
        if (text.includes('/Users/') || text.includes('Traceback') || text.includes('@') || text.includes('gho_')) throw new Error('Capture needs privacy review');
        if (!text.includes('MODU') || !(text.includes('Page ') || text.includes(' 页'))) throw new Error('Reader missing');
        if (frame.name === 'side-by-side' && !text.includes('passed in')) throw new Error('Real test result missing');
        const rect = document.querySelector('.xterm-screen').getBoundingClientRect();
        return { name: frame.name, columns: frame.columns, rows: frame.rows,
          width: Math.ceil(rect.width), height: Math.ceil(rect.height), renderer: 'xterm.js 6.0.0 DOM' };
      }, frame);
      await page.screenshot({ path: path.join(values.output, frame.name + '.png'),
        clip: { x: 0, y: 0, width: result.width, height: result.height } });
      results.push(result);
    }
    console.log(JSON.stringify(results, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

/** Replay test-only PTY output in xterm.js 6's DOM renderer.
 * This browser is an isolated regression fixture, never part of the reader.
 * Install the exact optional tools listed in docs/validation.md.
 * Frame files can contain book text: use original fixtures and ignored output dirs.
 */
const fs = require('node:fs');
const path = require('node:path');
const { parseArgs } = require('node:util');
const { values } = parseArgs({ options: {
  frames: { type: 'string' }, modules: { type: 'string' },
  browser: { type: 'string' }, work: { type: 'string' }
}});
for (const key of ['frames', 'modules', 'browser', 'work']) {
  if (!values[key]) throw new Error(`Missing --${key}`);
}
const moduleDir = path.resolve(values.modules);
const work = path.resolve(values.work);
fs.mkdirSync(work, { recursive: true });
const { chromium } = require(path.join(moduleDir, 'playwright-core'));
const xtermDir = path.join(moduleDir, '@xterm/xterm');
if (require(path.join(xtermDir, 'package.json')).version !== '6.0.0') {
  throw new Error('The unfixed negative control requires xterm.js 6.0.0');
}
// WidthCache rounds the total advance of 32 glyphs to integer pixels. Allow
// up to 1.25 CSS pixels of accumulated rounding, never a displaced terminal cell.
const tolerance = 1.25;
(async()=>{
 const frames=JSON.parse(fs.readFileSync(values.frames,'utf8'));
 const browser=await chromium.launch({executablePath:path.resolve(values.browser),headless:true});
 try {
 const page=await browser.newPage({viewport:{width:2100,height:1300}});
 await page.route('**/*', route => route.abort());
 await page.setContent('<html><body style="margin:0;background:#121416"><div id="term"></div></body></html>');
 await page.addStyleTag({path:path.join(xtermDir,'css/xterm.css')});
 await page.addScriptTag({path:path.join(xtermDir,'lib/xterm.js')});
 const all=[];
 for(const mode of ['old','guarded']) for(const fontSize of [13,18,22]) {
  const result=await page.evaluate(async({frames,mode,fontSize,tolerance})=>{
   window.term?.dispose?.();window.reference?.dispose?.();document.querySelector('#calibration')?.remove();document.querySelector('#term').innerHTML='';
   window.term=new Terminal({cols:110,rows:36,fontFamily:'ui-monospace, Menlo, Consolas, monospace',fontSize,theme:{background:'#121416',foreground:'#ddd6c8'},allowProposedApi:true});
   term.open(document.querySelector('#term'));
   const calibration=document.createElement('div');calibration.id='calibration';calibration.style.cssText='position:absolute;left:0;top:0;opacity:0;pointer-events:none';document.body.append(calibration);
   window.reference=new Terminal({cols:200,rows:1,fontFamily:'ui-monospace, Menlo, Consolas, monospace',fontSize,theme:{background:'#121416',foreground:'#ddd6c8'},allowProposedApi:true});reference.open(calibration);
   const baselines={};
   await new Promise(r=>setTimeout(r,100));
   const colors={'modu-gold':['rgb(37, 42, 45)','rgb(212, 180, 119)'],'modu-paper':['rgb(232, 224, 210)','rgb(133, 99, 46)'],'modu-slate':['rgb(39, 53, 68)','rgb(145, 191, 195)'],'modu-sepia':['rgb(228, 213, 186)','rgb(130, 90, 50)'],'modu-bamboo':['rgb(213, 225, 206)','rgb(65, 103, 77)'],'modu-mist':['rgb(218, 223, 229)','rgb(82, 94, 110)'],'modu-graphite':['rgb(43, 46, 49)','rgb(184, 172, 145)'],'modu-pine':['rgb(36, 53, 44)','rgb(163, 186, 148)']};
   let checked=0,maxDrift=0,failed=0,missing=0;const samples=[];
   for(let i=0;i<frames.length;i++){
    const {state:s}=frames[i];const [cols,rows]=s.terminal_size;
    if(term.cols!==cols||term.rows!==rows)term.resize(cols,rows);
    await new Promise(r=>term.write(mode==='old'?frames[i].ansi.replaceAll('\u2060',''):frames[i].ansi,r));
    await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
    const [x,y,w,h]=s.rail_region;
    const bounds=document.querySelector('.xterm-rows').getBoundingClientRect();
    if(baselines[x]===undefined){
     await new Promise(r=>reference.write('\x1b[?25l\x1b[0m\x1b[2J\x1b[H'+' '.repeat(x)+'\x1b[48;2;1;2;3m \x1b[0m',r));
     await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
     const marker=[...calibration.querySelectorAll('.xterm-rows span')].find(e=>e.style.backgroundColor==='rgb(1, 2, 3)');
     baselines[x]=marker.getBoundingClientRect().x;
    }
    const expected=bounds.x+baselines[x];
    const lines=[...document.querySelectorAll('#term .xterm-rows>div')];
    for(let row=y;row<y+h;row++){
     let column=0,rail=null,railRange=null;
     for(const el of lines[row].children){
      let offset=0;
      while(offset<el.textContent.length){
       const cellData=term.buffer.active.getLine(row).getCell(column);
       if(!cellData)throw new Error('No cell while mapping DOM span');
       const chars=cellData.getChars()||' ';const width=cellData.getWidth();
       if(width===0){column++;continue;}
       if(!el.textContent.startsWith(chars,offset))throw new Error('Cell/DOM text differs');
       if(column===x){
        rail=el;railRange=document.createRange();
        railRange.setStart(el.firstChild,offset);railRange.setEnd(el.firstChild,offset+chars.length);
       }
       offset+=chars.length;column+=width;
      }
     }
     if(!rail||!railRange){missing++;continue;}
     const base={'modu-gold':'rgb(18, 20, 22)','modu-paper':'rgb(245, 241, 232)','modu-slate':'rgb(25, 35, 46)','modu-sepia':'rgb(241, 229, 207)','modu-bamboo':'rgb(230, 238, 223)','modu-mist':'rgb(232, 234, 237)','modu-graphite':'rgb(32, 34, 36)','modu-pine':'rgb(23, 35, 31)'}[s.theme];
     const expectedColors=s.scrollbar&&row>y&&row<y+h-1?colors[s.theme]:[base];
     if(!expectedColors.includes(rail.style.backgroundColor))throw new Error('Visible/hidden rail color mismatch');
     const actual=railRange.getBoundingClientRect().x;const drift=Math.abs(actual-expected);
     checked++;maxDrift=Math.max(maxDrift,drift);if(drift>tolerance){failed++;if(samples.length<6)samples.push({frame:i,row,actual,expected,drift});}
    }
   }
   return {mode,fontSize,frames:frames.length,checked,failed,missing,maxDrift,samples,browser:navigator.userAgent};
  },{frames,mode,fontSize,tolerance});
  all.push(result);console.log(JSON.stringify(result));
 }
 fs.writeFileSync(path.join(work,'result.json'),JSON.stringify({tolerance,results:all},null,2));
 if(all.filter(r=>r.mode==='guarded').some(r=>r.failed||r.missing))process.exitCode=1;
 if(!all.filter(r=>r.mode==='old').every(r=>r.failed>0))process.exitCode=1;
 } finally { await browser.close(); }
})();

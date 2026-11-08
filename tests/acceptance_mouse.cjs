/** Live real-PTY mouse regression in an isolated xterm.js DOM terminal.
 * Only the test terminal has modes reset. No host app or personal profile is used.
 * Optional dependencies: @xterm/xterm 6.0.0 and playwright-core 1.65.0.
 */
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const { parseArgs } = require('node:util');
const { values } = parseArgs({ options: {
  python: {type:'string'}, modules: {type:'string'}, browser: {type:'string'}, work: {type:'string'}, extended: {type:'boolean'}
}});
for (const key of ['python','modules','browser','work']) if (!values[key]) throw Error(`Missing --${key}`);
const work = path.resolve(values.work);
fs.mkdirSync(work); // A fresh, isolated library on every run.
const book = path.join(work,'mouse-check.md');
fs.writeFileSync(book, Array.from({length:values.extended?40:3}, (_,c) => `# Chapter ${c+1} 山间灯火\n\n` +
  Array.from({length:values.extended?3:30}, (_,i) => `Passage ${c+1}.${i+1}. ` + 'The window is quiet. “雨停了，”她说。灯还亮着。 '.repeat(12)).join('\n\n')).join('\n\n'));
const originalBytes=fs.readFileSync(book);
const { chromium } = require(path.join(path.resolve(values.modules), 'playwright-core'));
const xterm = path.join(path.resolve(values.modules),'@xterm/xterm');
const sleep = ms => new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser = await chromium.launch({executablePath:path.resolve(values.browser),headless:true});
 let child, page, exitCode, queue=Promise.resolve(), bridgeError;
 try {
  page = await browser.newPage({viewport:{width:1700,height:1000}});
  await page.route('**/*', route=>route.abort());
  await page.setContent('<div id="term"></div><input id="outside">');
  await page.addStyleTag({path:path.join(xterm,'css/xterm.css')});
  await page.addScriptTag({path:path.join(xterm,'lib/xterm.js')});
  await page.exposeFunction('sendToPty', data=>child?.stdin.write(JSON.stringify({input:data})+'\n'));
  await page.evaluate(()=>{
   window.inputs=[];
   window.term=new Terminal({cols:110,rows:36,fontSize:16,fontFamily:'Menlo,monospace',allowProposedApi:true});
   term.open(document.querySelector('#term')); term.focus();
   term.onData(data=>{inputs.push(data);window.sendToPty(data);});
   window.writeTerm=data=>new Promise(r=>term.write(data,r));
   window.screenText=()=>Array.from({length:term.rows},(_,y)=>term.buffer.active.getLine(y)?.translateToString(true)||'').join('\n');
   window.progress=()=>screenText().split('\n').at(-1).match(/([\d.]+)%/)?.[1];
  });
  child=spawn(values.python,[path.join(__dirname,'mouse_pty_bridge.py'),'--python',values.python,'--library',path.join(work,'library'),'--book',book],{stdio:['pipe','pipe','pipe']});
  child.stderr.on('data',data=>fs.appendFileSync(path.join(work,'bridge.log'),data));
  readline.createInterface({input:child.stdout}).on('line',line=>{
   const message=JSON.parse(line);
   if ('exit' in message) exitCode=message.exit;
   if (message.output) queue=queue.then(()=>page.evaluate(data=>writeTerm(data),message.output)).catch(error=>{bridgeError=error;});
  });
  async function wait(check,label,timeout=6000){
   const start=Date.now();
   while(Date.now()-start<timeout){
    if(bridgeError) throw bridgeError;
    if(await check()) return Date.now()-start;
    await sleep(30);
   }
   throw Error('Timed out: '+label);
  }
  async function cell(col,row){
   const box=await page.locator('.xterm-screen').boundingBox();
   const size=await page.evaluate(()=>[term.cols,term.rows]);
   return {x:box.x+(col+0.5)*box.width/size[0],y:box.y+(row+0.5)*box.height/size[1]};
  }
  async function mouseAt(col,row){ const p=await cell(col,row);await page.mouse.move(p.x,p.y); }
  async function clickText(text,last=false){
   await sleep(350); // Let Textual's button press feedback finish before reuse.
   const pos=await page.evaluate(({text,last})=>{
    for(let index=0;index<term.rows;index++) for(let col=0;col<term.cols;col++) {
     const row=last?term.rows-index-1:index;
     let rest='';for(let x=col;x<term.cols;x++) rest+=term.buffer.active.getLine(row).getCell(x).getChars()||' ';
     if(rest.startsWith(text)&&(!last||/^\s{2}/.test(rest.slice(text.length))))return [col,row];
    }
   },{text,last});
   if(!pos)throw Error('Missing button '+text);
   const p=await cell(...pos);await page.mouse.click(p.x,p.y);
  }
  await wait(()=>page.evaluate(()=>screenText().includes('Page 1 /')),'startup');
  await page.evaluate(()=>term.focus());
  const recoveries=[];
  for(let cycle=0;cycle<12;cycle++){
   await page.keyboard.press('Home');
   await wait(()=>page.evaluate(()=>progress()==='0.0'),'home');
   // Reset the host terminal's mouse state, never the reader's input stream.
   await page.evaluate(async fallback=>{
    await writeTerm('\x1b[?1000l\x1b[?1003l\x1b[?1006l'+(fallback?'\x1b[?1004l':''));
    if(term.modes.mouseTrackingMode!=='none')throw Error('Reset failed');
    document.querySelector('#outside').focus();term.focus();
   },cycle>=8);
   recoveries.push(await wait(()=>page.evaluate(()=>term.modes.mouseTrackingMode==='any'),'mouse-mode recovery',1400));
   const before=await page.evaluate(()=>progress());
   await mouseAt(70,18);await page.mouse.wheel(0,100);
   await wait(()=>page.evaluate(before=>progress()!==before,before),'wheel');
   await clickText('Settings s');
   await wait(()=>page.evaluate(()=>screenText().includes('Reading settings')),'settings click');
   await page.keyboard.press('Escape');
   await wait(()=>page.evaluate(()=>!screenText().includes('Reading settings')),'close');
   await mouseAt(109,15);await page.mouse.down();
   await sleep(600); // Cross a periodic recovery while the button is held.
   await mouseAt(109,27);await page.mouse.up();
   await wait(()=>page.evaluate(()=>Number(progress())>60),'drag');
  }
  // MouseUp lost while outside the terminal must not leave the rail captured.
  await page.evaluate(()=>writeTerm('\x1b[?1004h'));
  await sleep(60);
  await mouseAt(109,19);await page.mouse.down();
  await sleep(100);
  const heldPosition=await page.evaluate(()=>progress());
  await page.evaluate(()=>{document.querySelector('#outside').focus();term.focus();});
  await sleep(100);
  await mouseAt(70,15);await page.mouse.up();
  await sleep(100);
  if(await page.evaluate(()=>progress())!==heldPosition)throw Error('Interrupted drag changed reading position');
  await clickText('Settings s');
  await wait(()=>page.evaluate(()=>screenText().includes('Reading settings')),'click after interrupted drag');
  await page.keyboard.press('Escape');
  await wait(()=>page.evaluate(()=>!screenText().includes('Reading settings')),'close final settings');
  let tocChecks=0,shelfActions=false;
  if(values.extended){
   let track=0x252a2d;
   async function checkToc(){
    await sleep(100);
    const expected=await page.evaluate(track=>{
     const bar=[];let first=-1;
     for(let y=12;y<term.rows-4;y++){
      const cell=term.buffer.active.getLine(y).getCell(23);
      if(cell.getChars()!==' '&&cell.getChars()!=='')throw Error('Fractional glyph on TOC rail');
      const color=cell.getBgColor();bar.push(color);
      if(color!==track&&first<0)first=y;
     }
     const thumb=bar.map((c,i)=>c!==track?i:-1).filter(i=>i>=0);
     if(!thumb.length||thumb.at(-1)-thumb[0]+1!==thumb.length)throw Error('Split TOC thumb');
     if(new Set(thumb.map(i=>bar[i])).size!==1)throw Error('Uneven TOC thumb');
     const box=document.querySelector('.xterm-screen').getBoundingClientRect();
     return {bar,first,x:box.x+23.5*box.width/term.cols,y:box.y,cellHeight:box.height/term.rows};
    },track);
    const png=await page.screenshot();
    await page.evaluate(async({png,expected})=>{
     const image=new Image();image.src='data:image/png;base64,'+png;await image.decode();
     const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
     const context=canvas.getContext('2d');context.drawImage(image,0,0);
     for(let i=0;i<expected.bar.length;i++)for(const part of [0.15,0.5,0.85]){
      const p=context.getImageData(Math.floor(expected.x),Math.floor(expected.y+(12+i+part)*expected.cellHeight),1,1).data;
      if((p[0]<<16|p[1]<<8|p[2])!==expected.bar[i])throw Error('TOC pixel seam or displacement');
     }
    },{png:png.toString('base64'),expected});
    tocChecks++;return expected.first;
   }
   await mouseAt(10,20);await page.mouse.wheel(0,150);await sleep(200);
   const thumbRow=await checkToc();
   const beforeDrag=await page.evaluate(()=>screenText());
   await mouseAt(23,thumbRow);await page.mouse.down();await sleep(600);await mouseAt(23,30);await page.mouse.up();
   await wait(()=>page.evaluate(text=>screenText()!==text,beforeDrag),'TOC dragging');await checkToc();
   await mouseAt(70,18);await page.mouse.click((await cell(70,18)).x,(await cell(70,18)).y);
   await page.keyboard.press('End');
   await wait(()=>page.evaluate(()=>screenText().includes('> 40')),'last chapter follows');await checkToc();
   for(const color of ['e8e0d2','273544','e4d5ba','d5e1ce','dadfe5','2b2e31','24352c','252a2d']){
    await page.keyboard.press('t');track=parseInt(color,16);await sleep(160);await checkToc();
   }
   for(const [columns,rows] of [[70,28],[84,36],[110,42],[110,36]]){
    await page.evaluate(([c,r])=>term.resize(c,r),[columns,rows]);
    child.stdin.write(JSON.stringify({resize:[columns,rows]})+'\n');
    await sleep(350);await checkToc();
    if(!await page.evaluate(()=>screenText().includes('> 40')))throw Error('Current chapter hidden after resize');
   }
   await page.screenshot({path:path.join(work,'toc-verified.png')});
   await page.keyboard.press('Escape');
   await wait(()=>page.evaluate(()=>screenText().includes('Archive a')),'shelf');
   await clickText('Archive a');await wait(()=>page.evaluate(()=>screenText().includes('Archive this book?')),'archive confirmation');
   await page.keyboard.press('Enter');await wait(()=>page.evaluate(()=>!screenText().includes('Archive this book?')),'default cancel');
   await clickText('Archive a');await wait(()=>page.evaluate(()=>screenText().includes('Archive this book?')),'archive again');
   await clickText('Archive',true);await wait(()=>page.evaluate(()=>screenText().includes('Press i to import')),'archive complete');
   await clickText('Archived v');await wait(()=>page.evaluate(()=>screenText().includes('Restore a')),'archived shelf');
   await clickText('Restore a');await wait(()=>page.evaluate(()=>screenText().includes('Restore this book?')),'restore confirmation');
   await clickText('Restore',true);await wait(()=>page.evaluate(()=>screenText().includes('No archived books yet.')),'restored');
   await clickText('Shelf v');await wait(()=>page.evaluate(()=>screenText().includes('Archive a')),'active shelf');
   await clickText('Delete d');await wait(()=>page.evaluate(()=>screenText().includes('Delete this book?')),'delete confirmation');
   await page.keyboard.press('Escape');await wait(()=>page.evaluate(()=>!screenText().includes('Delete this book?')),'cancel delete');
   await clickText('Delete d');await wait(()=>page.evaluate(()=>screenText().includes('Delete this book?')),'delete again');
   await page.screenshot({path:path.join(work,'delete-confirmation.png')});
   await clickText('Delete',true);await wait(()=>page.evaluate(()=>screenText().includes('Press i to import')),'deleted');
   if(!originalBytes.equals(fs.readFileSync(book)))throw Error('Original file changed');
   for(const folder of ['cache','originals'])if(fs.readdirSync(path.join(work,'library',folder)).length)throw Error('Library copy remains');
   shelfActions=true;
  }
  await page.keyboard.press('q');
  await wait(()=>exitCode!==undefined,'exit');
  await queue;
  if(exitCode!==0)throw Error('CLI failed');
  if(await page.evaluate(()=>term.modes.mouseTrackingMode!=='none'))throw Error('Shell mouse mode not restored');
  const sgr=await page.evaluate(()=>inputs.filter(x=>/^\x1b\[</.test(x)).length);
  if(sgr<60)throw Error('Mouse reports were not generated by xterm');
  const result={status:'PASS',transport:'Live CLI PTY and xterm.js DOM mouse events',focus_cycles:8,missing_focus_cycles:4,real_wheel_checks:12,real_button_clicks:13,real_drags:12,interrupted_drag:true,generated_sgr_reports:sgr,max_recovery_ms:Math.max(...recoveries),shell_mouse_mode_restored:true,toc_pixel_frames:tocChecks,confirmed_archive_restore_delete:shelfActions,scope:'Isolated terminal with simulated host mode loss; no host app automated'};
  fs.writeFileSync(path.join(work,'result.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
 } catch(error) {
  if(page){
   fs.writeFileSync(path.join(work,'failure.json'),JSON.stringify(await page.evaluate(()=>({text:screenText(),inputs,modes:term.modes})),null,2));
   await page.screenshot({path:path.join(work,'failure.png')});
  }
  throw error;
 } finally { child?.stdin.end(); await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});

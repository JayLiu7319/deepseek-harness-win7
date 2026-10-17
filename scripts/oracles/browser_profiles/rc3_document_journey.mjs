/** Trusted browser gestures against the unchanged rc.3 document and Dockkit UI. */
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {join} from 'node:path';

// Same deterministic vector document as the pinned upstream PDF test fixture.
function pdfFixture(){
  const streams=['0.9 0.1 0.1 rg 10 10 100 80 re f','0.1 0.1 0.9 rg 10 10 100 80 re f'];
  const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 120 100] /Resources << >> /Contents 4 0 R >>',
    `<< /Length ${streams[0].length} >>\nstream\n${streams[0]}\nendstream`,
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 120 100] /Resources << >> /Contents 6 0 R >>',
    `<< /Length ${streams[1].length} >>\nstream\n${streams[1]}\nendstream`];
  let text='%PDF-1.4\n';const offsets=[0];
  objects.forEach((object,index)=>{offsets.push(text.length);text+=`${index+1} 0 obj\n${object}\nendobj\n`;});
  const xref=text.length;text+=`xref\n0 ${objects.length+1}\n0000000000 65535 f \n`;
  for(const offset of offsets.slice(1))text+=`${String(offset).padStart(10,'0')} 00000 n \n`;
  return Buffer.from(text+`trailer\n<< /Size ${objects.length+1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`,'ascii');
}

export async function prepareDocuments(workspace){
  await mkdir(workspace,{recursive:true});
  const files={
    'journey.md':'# RC3 document heading\n\nOriginal Markdown renderer.\n',
    'journey.unknown':Array.from({length:12000},(_,index)=>`RC3_LINE_${String(index+1).padStart(5,'0')} `+'visible text '.repeat(12)).join('\n'),
    'journey.html':'<!doctype html><link rel="stylesheet" href="./journey.css"><h1>RC3 HTML heading</h1><p id="local">pending</p><script>window.parentAccess="unexpected";try{parent.document.documentElement.setAttribute("data-rc3-escape","true")}catch(error){window.parentAccess=error.name}</script><script src="./journey.js"></script>',
    'journey.css':'#local {color:rgb(12,34,56)}',
    'journey.js':'document.getElementById("local").textContent="LOCAL_JS_OK";parent.postMessage({kind:"rc3-html-observation",heading:document.querySelector("h1").textContent,local:document.getElementById("local").textContent,color:getComputedStyle(document.getElementById("local")).color,parentAccess:window.parentAccess},"*");',
    'journey.png':Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64'),
    'journey.pdf':pdfFixture(),
  };
  for(const [name,body] of Object.entries(files))await writeFile(join(workspace,name),body,typeof body==='string'?'utf8':undefined);
}

export async function documentJourney({cdp,click,until,state,output,phase}){
  const observed=state.documents={};
  const shown=selector=>cdp.evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});return !!n&&n.getBoundingClientRect().width>0;})()`);
  if(!await shown('[data-sidebar-right-open]'))await click(cdp,'[data-sidebar-right-expand]');
  await until(()=>shown('[data-files-state="tree"]'),'original Files tree');
  await click(cdp,'[data-files-reload]');
  const tab='[data-dockkit-tab]';
  observed.initialTitles=await cdp.evaluate(`Array.from(document.querySelectorAll('[data-dockkit-tab-title]'),n=>n.textContent)`);
  assert.deepEqual(observed.initialTitles,['Files']);
  await click(cdp,'[data-dockkit-add-tab]');
  await until(()=>shown('[data-sidebar-right-guide]'),'manual guide tab');
  await click(cdp,'[data-dockkit-tab]:last-child [data-dockkit-tab-close]');
  await until(()=>cdp.evaluate(`document.querySelectorAll(${JSON.stringify(tab)}).length===1`),'guide closes with Files retained');
  const preview='[data-document-preview]';
  const open=async name=>{
    await click(cdp,tab,'Files');
    await click(cdp,'[data-files-entry="file"] > button',name);
    await until(()=>cdp.evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(preview)})).some(n=>n.getAttribute('data-textpreview-url')?.endsWith('/'+${JSON.stringify(name)}))`),'document selection '+name);
  };
  await open('journey.md');
  observed.markdown=await until(()=>cdp.evaluate(`document.querySelector('[data-document-markdown] h1')?.textContent`),'Markdown heading');
  assert.equal(observed.markdown,'RC3 document heading');
  const markdownId=await cdp.evaluate(`Array.from(document.querySelectorAll('${tab}')).find(n=>n.textContent.includes('journey.md'))?.getAttribute('data-dockkit-tab')`);
  observed.viewers=[];
  for(const label of ['Code','Plain text','Markdown']){
    await click(cdp,'[data-document-viewer-menu]');
    await click(cdp,'[role="menuitem"]',label);
    await until(()=>cdp.evaluate(`document.querySelector('[data-document-viewer-menu]')?.textContent===${JSON.stringify(label)}`),'original viewer '+label);
    observed.viewers.push(label);
    assert.equal(await cdp.evaluate(`Array.from(document.querySelectorAll('${tab}')).find(n=>n.textContent.includes('journey.md'))?.getAttribute('data-dockkit-tab')`),markdownId);
  }
  await open('journey.unknown');
  observed.pagingBefore=await until(()=>cdp.evaluate(`(()=>{const rows=[...document.querySelectorAll('[data-textpreview-line]')];const more=document.querySelector('[data-textpreview-more]');return rows.length>0&&more&&!more.disabled&&{lines:rows.length,tail:rows.at(-1).textContent};})()`),'bounded initial text page');
  assert.ok(observed.pagingBefore.lines<12000);
  // Scroll the original document owner, as upstream's end-to-end test does.
  // Scrolling the offscreen More button into view itself starts this read.
  for(let page=0;page<32;page++){
    const done=await cdp.evaluate(`document.querySelector('[data-textpreview-body]')?.textContent.includes('RC3_LINE_12000')`);
    if(done)break;
    const before=await cdp.evaluate(`document.querySelectorAll('[data-textpreview-line]').length`);
    await cdp.evaluate(`(()=>{const body=document.querySelector('[data-textpreview-body]');if(body.scrollHeight<=body.clientHeight)throw new Error('paging fixture must overflow');body.scrollTop=body.scrollHeight;})()`);
    await until(()=>cdp.evaluate(`document.querySelectorAll('[data-textpreview-line]').length>${before}`),'additional real text page');
  }
  observed.pagingAfter=await cdp.evaluate(`({lines:document.querySelectorAll('[data-textpreview-line]').length,tail:document.querySelector('[data-textpreview-body]')?.textContent.includes('RC3_LINE_12000'),more:!!document.querySelector('[data-textpreview-more]')})`);
  assert.equal(observed.pagingAfter.tail,true);assert.equal(observed.pagingAfter.more,false);
  await cdp.evaluate(`window.__rc3HtmlMessages=[];window.addEventListener('message',event=>{if(event.data?.kind==='rc3-html-observation')window.__rc3HtmlMessages.push({data:event.data,origin:event.origin,fromPreview:event.source===document.querySelector('[data-html-preview]')?.contentWindow})})`);
  await open('journey.html');
  observed.html=await until(()=>cdp.evaluate('window.__rc3HtmlMessages[0]??false'),'isolated HTML scripts and local assets');
  assert.deepEqual(observed.html,{data:{kind:'rc3-html-observation',heading:'RC3 HTML heading',local:'LOCAL_JS_OK',color:'rgb(12, 34, 56)',parentAccess:'SecurityError'},origin:'null',fromPreview:true});
  assert.equal(await cdp.evaluate(`document.querySelector('[data-html-preview]').getAttribute('sandbox')`),'allow-scripts');
  assert.equal(await cdp.evaluate(`document.documentElement.hasAttribute('data-rc3-escape')`),false);
  await open('journey.png');
  observed.image=await until(()=>cdp.evaluate(`(()=>{const n=document.querySelector('[data-image-preview] img');return n?.complete&&n.naturalWidth>0&&{width:n.naturalWidth,height:n.naturalHeight};})()`),'decoded original image renderer');
  assert.deepEqual(observed.image,{width:1,height:1});
  await open('journey.pdf');
  observed.pdf=[];
  for(const page of [1,2]){
    const selector=`[data-pdf-page="${page}"]`;
    await until(()=>shown(selector),'PDF page container '+page);
    await cdp.evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'center'})`);
    const pixel=await until(()=>cdp.evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector+' canvas')});if(!n||!n.width||!n.height)return false;const p=n.getContext('2d').getImageData(Math.floor(n.width/2),Math.floor(n.height/2),1,1).data;return p[3]===255&&(${page}===1?p[0]-p[2]>150:p[2]-p[0]>150)&&{page:${page},rgba:Array.from(p),width:n.width,height:n.height};})()`),'PDF worker rasterizes page '+page,30000);
    assert.ok(page===1?pixel.rgba[0]-pixel.rgba[2]>150:pixel.rgba[2]-pixel.rgba[0]>150);
    observed.pdf.push(pixel);
  }
  const screenshot=await cdp.call('Page.captureScreenshot');
  await writeFile(join(output,phase+'.documents.png'),Buffer.from(screenshot.data,'base64'));
  observed.finalTitles=await cdp.evaluate(`Array.from(document.querySelectorAll('[data-dockkit-tab-title]'),n=>n.textContent)`);
  assert.ok(['Files','journey.md','journey.unknown','journey.html','journey.png','journey.pdf'].every(title=>observed.finalTitles.includes(title)));
  observed.workersBeforeClose=await cdp.evaluate(`globalThis[Symbol.for('deepseek-win7.host.workers')]?.facts??null`);
  await click(cdp,'[data-dockkit-tab]:last-child [data-dockkit-tab-close]');
  await until(()=>cdp.evaluate(`!Array.from(document.querySelectorAll('[data-dockkit-tab-title]')).some(n=>n.textContent==='journey.pdf')`),'PDF document closes');
  if(observed.workersBeforeClose){
    observed.workersAfterClose=await until(()=>cdp.evaluate(`(()=>{const f=globalThis[Symbol.for('deepseek-win7.host.workers')].facts;return f.activeWorkers===0&&f.activeUrls===0&&f;})()`),'PDF worker termination and Blob URL release');
    assert.equal(observed.workersAfterClose.created,1);
    assert.equal(observed.workersAfterClose.terminated,1);
    assert.deepEqual(observed.workersAfterClose.errors,[]);
  }
  observed.dock=[];
  await click(cdp,'[data-sidebar-right-mode="fullscreen"]');
  await until(()=>shown('[data-sidebar-right-panel="fullscreen"]'),'sidebar fullscreen mode');
  observed.dock.push('fullscreen');
  await click(cdp,'[data-dockkit-split-button]');
  observed.split=await until(()=>cdp.evaluate(`(()=>{const panes=[...document.querySelectorAll('[data-sidebar-right-panel] [data-dockkit-pane]')];return panes.length===2&&panes.map(n=>({id:n.getAttribute('data-dockkit-pane'),tabs:[...n.querySelectorAll('[data-dockkit-tab-title]')].map(t=>t.textContent)}));})()`),'two real Dockkit panes');
  assert.equal(await cdp.evaluate(`Array.from(document.querySelectorAll('[data-dockkit-split-button]')).every(n=>n.disabled)`),true);
  await click(cdp,'[data-sidebar-right-mode="push"]');
  await until(()=>shown('[data-sidebar-right-panel="push"]'),'sidebar returns to push mode');
  observed.dock.push('push');
  await click(cdp,'[data-sidebar-right-toggle]');
  await until(()=>cdp.evaluate(`!document.querySelector('[data-sidebar-right-open]')`),'sidebar collapses');
  await click(cdp,'[data-sidebar-right-expand]');
  await until(()=>shown('[data-sidebar-right-open]'),'sidebar reopens');
  assert.equal(await cdp.evaluate(`document.querySelectorAll('[data-sidebar-right-panel] [data-dockkit-pane]').length`),2);
  observed.dock.push('collapse/reopen preserves split');
  const drag=async(from,to)=>{
    await cdp.call('Input.dispatchMouseEvent',{type:'mouseMoved',...from});
    await cdp.call('Input.dispatchMouseEvent',{type:'mousePressed',...from,button:'left',buttons:1,clickCount:1});
    for(const fraction of [0.2,0.5,1])await cdp.call('Input.dispatchMouseEvent',{type:'mouseMoved',
      x:from.x+(to.x-from.x)*fraction,y:from.y+(to.y-from.y)*fraction,button:'left',buttons:1});
    await cdp.call('Input.dispatchMouseEvent',{type:'mouseReleased',...to,button:'left',clickCount:1});
  };
  const rectangle=selector=>cdp.evaluate(`(()=>{const n=document.querySelector(${JSON.stringify(selector)});if(!n)return false;const r=n.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})()`);
  const titlePoint=await cdp.evaluate(`(()=>{const title=[...document.querySelectorAll('[data-sidebar-right-panel] [data-dockkit-tab-title]')].find(n=>n.textContent==='journey.md');title.scrollIntoView({block:'nearest'});const r=title.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
  await drag(titlePoint,{x:100,y:250});
  observed.float=await until(async()=>{
    const rect=await rectangle('[data-dockkit-float]');
    const title=await cdp.evaluate(`document.querySelector('[data-dockkit-float-title]')?.textContent`);
    return rect&&title?.includes('journey.md')&&{rect,title};
  },'trusted drag floats original document');
  const grip=await rectangle('[data-dockkit-float-grip]');
  await drag({x:grip.x+40,y:grip.y+grip.height/2},{x:grip.x+100,y:grip.y+grip.height/2+40});
  observed.floatMoved=await until(async()=>{const rect=await rectangle('[data-dockkit-float]');return rect&&rect.x>observed.float.rect.x+30&&rect.y>observed.float.rect.y+20&&rect;},'floating document moves');
  const handle=await rectangle('[data-dockkit-float-resize]');
  await drag({x:handle.x+handle.width/2,y:handle.y+handle.height/2},
    {x:handle.x+handle.width/2+70,y:handle.y+handle.height/2+40});
  observed.floatResized=await until(async()=>{const rect=await rectangle('[data-dockkit-float]');return rect&&rect.width>observed.floatMoved.width+30&&rect.height>observed.floatMoved.height+20&&rect;},'floating document resizes');
  await click(cdp,'[data-dockkit-float-dock]');
  await until(()=>cdp.evaluate(`!document.querySelector('[data-dockkit-float]')&&[...document.querySelectorAll('[data-sidebar-right-panel] [data-dockkit-tab-title]')].some(n=>n.textContent==='journey.md')`),'floating document docks back');
  assert.equal(await cdp.evaluate(`Array.from(document.querySelectorAll('${tab}')).find(n=>n.textContent.includes('journey.md'))?.getAttribute('data-dockkit-tab')`),markdownId);
  observed.dock.push('float/move/resize/dock preserves tab identity');
  observed.passed=true;
}

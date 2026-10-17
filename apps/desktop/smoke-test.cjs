'use strict';
// Development-only integration entry, unavailable in packaged applications.
const {mkdir,writeFile,readFile,cp}=require('node:fs/promises');
const {join,resolve}=require('node:path');
const assert=require('node:assert/strict');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function evaluate(window,expression,timeout=45000){
  let timer;
  try{return await Promise.race([window.webContents.executeJavaScript(expression),
    new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Desktop evaluation deadline: '+expression.slice(0,160))),timeout);})]);}
  finally{clearTimeout(timer);}
}
async function wait(window,predicate){
  const deadline=Date.now()+45000;
  while(Date.now()<deadline){
    if(await evaluate(window,predicate))return;
    await pause(150);
  }
  throw new Error('Desktop renderer did not become ready: '+predicate);
}
async function run({app,mainWindow,openPlugins,pluginWindow,guideWindow,environment,manager,output}){
  await mkdir(output,{recursive:true});
  const report={versions:process.versions,errors:[],transitionErrors:[]};
  let phase='initial';
  mainWindow.webContents.on('console-message',(_event,level,message)=>{
    if(level!==3)return;
    if(phase==='mutating'&&message==='[session-controller] control stream failed: RemoteError: network error')report.transitionErrors.push(message);
    else report.errors.push(message);
  });
  try{
    await wait(mainWindow,"Boolean(document.querySelector('#root')?.children.length && globalThis.__DSH_TRANSPORT__)");
    if(environment.limitedShell){
      await wait(mainWindow,"!!document.getElementById('dsh-win7-environment-notice')");
      const clickNotice=async selector=>{
        const point=await evaluate(mainWindow,`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}})()`);
        mainWindow.webContents.sendInputEvent({type:'mouseDown',...point,button:'left',clickCount:1});
        mainWindow.webContents.sendInputEvent({type:'mouseUp',...point,button:'left',clickCount:1});
      };
      await clickNotice('#dsh-win7-environment-notice button:first-of-type');
      const deadline=Date.now()+10000;
      while(!guideWindow()&&Date.now()<deadline)await pause(100);
      assert.ok(guideWindow());
      await wait(guideWindow(),"document.body.innerText.includes('upgrade-win7.bat')");
      report.environmentGuide=await evaluate(guideWindow(),"({url:location.href,node:typeof require,text:document.body.innerText})");
      assert.equal(report.environmentGuide.node,'undefined');
      guideWindow().close();
      await clickNotice('#dsh-win7-environment-notice button:last-of-type');
      await wait(mainWindow,"!document.getElementById('dsh-win7-environment-notice')&&localStorage.getItem('dsh-win7-environment-dismissed')==='1'");
      report.environmentNotice={limitedShell:true,guideOpened:true,dismissed:true};
    }
    report.main=await evaluate(mainWindow,`({
      url:location.href,node:typeof require,process:typeof process,ownsHost:globalThis.__DSH_TRANSPORT__.ownsHost,
      text:document.body.innerText.slice(0,1500),preload:globalThis.dshDesktop,
      workers:globalThis.__DSH_BROWSER_COMPAT__?.workers
    })`);
    assert.equal(report.main.node,'undefined');assert.equal(report.main.process,'undefined');assert.equal(report.main.ownsHost,true);
    report.settings=await evaluate(mainWindow,`fetch('/api/settings/describe',{
      method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:'desktop-smoke',
      method:'settings/describe',payload:{args:{}}})}).then(async response=>({status:response.status,body:await response.json()}))`);
    assert.equal(report.settings.status,200);assert.equal(report.settings.body.result.ok,true);
    assert.ok(report.settings.body.result.value.namespaces.length>0);
    report.stream=await evaluate(mainWindow,`(async()=>{
      const controller=new AbortController();
      const iterator=globalThis.__DSH_TRANSPORT__.openStream('workspace/follow',{args:{}},controller.signal);
      const first=await iterator.next();
      controller.abort();
      let cancelled=false;try{await iterator.next();}catch(error){cancelled=error.name==='AbortError';}
      return {first,cancelled};
    })()`);
    assert.equal(report.stream.first.done,false);assert.equal(report.stream.cancelled,true);
    openPlugins();const shell=pluginWindow();
    await wait(shell,"Boolean(document.querySelector('#title')?.textContent && !document.querySelector('#refresh').disabled)");
    report.shell=await evaluate(shell,`(async()=>({url:location.href,node:typeof require,process:typeof process,
      title:document.querySelector('#title').textContent,status:document.querySelector('#status').textContent,
      plugins:await globalThis.dshDesktop.plugins.list(),locale:await globalThis.dshDesktop.locale()}))()`);
    assert.equal(report.shell.node,'undefined');assert.equal(report.shell.process,'undefined');assert.equal(report.shell.status,'');
    const example=resolve(__dirname,'../../examples/python-echo');
    const source=join(output,'broken-upgrade');
    await cp(example,source,{recursive:true,filter:file=>!file.includes('__pycache__')});
    const manifest=JSON.parse(await readFile(join(source,'package.json'),'utf8'));
    manifest.version='0.2.0';
    await writeFile(join(source,'package.json'),JSON.stringify(manifest));
    await writeFile(join(source,'python/echo/plugin.py'),"raise RuntimeError('Desktop health rejection fixture')\n");
    phase='mutating';
    await evaluate(shell,'globalThis.dshDesktop.plugins.add('+JSON.stringify(example)+')',180000);
    report.installed=await manager.list();
    assert.equal(report.installed.find(row=>row.name==='@example/python-echo').version,'0.1.0');
    let rejected=false;
    try{await evaluate(shell,'globalThis.dshDesktop.plugins.update("@example/python-echo",'+JSON.stringify(source)+')',180000);}
    catch(error){rejected=true;report.upgradeFailure=error.message;}
    assert.equal(rejected,true,'Broken upgrade must fail readiness');
    report.afterRollback=await manager.list();
    assert.equal(report.afterRollback.find(row=>row.name==='@example/python-echo').version,'0.1.0');
    await evaluate(shell,'globalThis.dshDesktop.plugins.remove("@example/python-echo")',180000);
    assert.deepEqual(await manager.list(),[]);
    await wait(mainWindow,"Boolean(document.querySelector('#root')?.children.length && globalThis.__DSH_TRANSPORT__)");
    phase='settled';
    report.reconnected=await evaluate(mainWindow,`(async()=>{
      const controller=new AbortController();
      const iterator=globalThis.__DSH_TRANSPORT__.openStream('workspace/follow',{args:{}},controller.signal);
      const first=await iterator.next();controller.abort();try{await iterator.next();}catch{}
      return first;
    })()`);
    assert.equal(report.reconnected.value.type,'baseline');
    report.security={main:mainWindow.webContents.getLastWebPreferences(),shell:shell.webContents.getLastWebPreferences()};
    for(const prefs of Object.values(report.security)){
      assert.equal(prefs.nodeIntegration,false);assert.equal(prefs.contextIsolation,true);assert.equal(prefs.sandbox,true);assert.equal(prefs.webSecurity,true);
    }
    await writeFile(join(output,'main.png'),(await mainWindow.webContents.capturePage()).toPNG());
    await writeFile(join(output,'plugin-manager.png'),(await shell.webContents.capturePage()).toPNG());
    assert.deepEqual(report.errors,[]);
    report.status='qualified';
  }catch(error){report.status='rejected';report.failure=error.stack;throw error;}
  finally{
    report.hostLogs=manager.host.logs;
    await writeFile(join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
    app.quit();
  }
}
module.exports={run};

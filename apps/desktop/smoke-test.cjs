'use strict';
// Development-only integration entry, unavailable in packaged applications.
const {mkdir,writeFile,readFile,cp}=require('node:fs/promises');
const {join,resolve}=require('node:path');
const assert=require('node:assert/strict');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function wait(window,predicate){
  const deadline=Date.now()+45000;
  while(Date.now()<deadline){
    if(await window.webContents.executeJavaScript(predicate))return;
    await pause(150);
  }
  throw new Error('Desktop renderer did not become ready: '+predicate);
}
async function run({app,mainWindow,openPlugins,pluginWindow,manager,output}){
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
    report.main=await mainWindow.webContents.executeJavaScript(`({
      url:location.href,node:typeof require,process:typeof process,ownsHost:globalThis.__DSH_TRANSPORT__.ownsHost,
      text:document.body.innerText.slice(0,1500),preload:globalThis.dshDesktop,
      workers:globalThis.__DSH_BROWSER_COMPAT__?.workers
    })`);
    assert.equal(report.main.node,'undefined');assert.equal(report.main.process,'undefined');assert.equal(report.main.ownsHost,true);
    report.settings=await mainWindow.webContents.executeJavaScript(`fetch('/api/settings/describe',{
      method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:'desktop-smoke',
      method:'settings/describe',payload:{args:{}}})}).then(async response=>({status:response.status,body:await response.json()}))`);
    assert.equal(report.settings.status,200);assert.equal(report.settings.body.result.ok,true);
    assert.ok(report.settings.body.result.value.namespaces.length>0);
    report.stream=await mainWindow.webContents.executeJavaScript(`(async()=>{
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
    report.shell=await shell.webContents.executeJavaScript(`(async()=>({url:location.href,node:typeof require,process:typeof process,
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
    await shell.webContents.executeJavaScript('globalThis.dshDesktop.plugins.add('+JSON.stringify(example)+')');
    report.installed=await manager.list();
    assert.equal(report.installed.find(row=>row.name==='@example/python-echo').version,'0.1.0');
    let rejected=false;
    try{await shell.webContents.executeJavaScript('globalThis.dshDesktop.plugins.update("@example/python-echo",'+JSON.stringify(source)+')');}
    catch(error){rejected=true;report.upgradeFailure=error.message;}
    assert.equal(rejected,true,'Broken upgrade must fail readiness');
    report.afterRollback=await manager.list();
    assert.equal(report.afterRollback.find(row=>row.name==='@example/python-echo').version,'0.1.0');
    await shell.webContents.executeJavaScript('globalThis.dshDesktop.plugins.remove("@example/python-echo")');
    assert.deepEqual(await manager.list(),[]);
    await wait(mainWindow,"Boolean(document.querySelector('#root')?.children.length && globalThis.__DSH_TRANSPORT__)");
    phase='settled';
    report.reconnected=await mainWindow.webContents.executeJavaScript(`(async()=>{
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

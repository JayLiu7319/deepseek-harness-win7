import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {lstat,mkdir,readFile,rm,unlink,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {dirname,join,resolve} from 'node:path';
import {createInterface} from 'node:readline';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {closeOriginalBrowser,credentialFreeEnvironment,deferProviderOnboarding,isolatedBrowserArguments,navigateOriginalPage} from '../../browser_onboarding.mjs';
import {prepareDocuments,documentJourney} from './rc3_document_journey.mjs';
import {applicationJourney} from './rc3_application_journey.mjs';
import {browserCompatibilityInput} from '../../browser_compat_input.mjs';

const options=Object.fromEntries(process.argv.slice(2).reduce((pairs,value,index,args)=>{
  if(value.startsWith('--'))pairs.push([value.slice(2),args[index+1]]);
  return pairs;
},[]));
if(!options.browser||!options.output||!options['run-dir']||!['source','native'].includes(options.side)
    ||!['minimal','standard','cordis'].includes(options.preset))throw new Error('Explicit actual browser journey options required');
const output=resolve(options.output),stage=dirname(fileURLToPath(import.meta.url));
await mkdir(output);
const report={side:options.side,preset:options.preset,phases:[],errors:[],consoleErrors:[],consoleLogs:[],responses:[],clicks:[],wire:[],requests:[]};
report.invocation={executable:process.execPath,arguments:process.argv.slice(1),options};
if(options['compat-script']){
  assert.equal(options.side,'source','The native host owns its production compatibility injection');
  const path=resolve(options['compat-script']);
  const {script,...input}=await browserCompatibilityInput(dirname(path));
  report.sourceHostAdaptation={path,...input,
    scope:'Unchanged Source frontend with the product host capability adapter; distinct from unadapted Source'};
}
if(options['file-references']==='true')report.fileReferenceScope='Actual original composer and remote.mux; isolated paths, no file-body injection';
const delay=milliseconds=>new Promise(done=>setTimeout(done,milliseconds));

async function until(read,description,timeout=30000){
  const deadline=Date.now()+timeout;
  let last;
  while(Date.now()<deadline){last=await read();if(last)return last;await delay(100);}
  throw new Error('Timed out: '+description+'; last='+JSON.stringify(last));
}

class CDP{
  constructor(socket){
    this.socket=socket;this.next=1;this.pending=new Map();
    this.responses=new Map();this.jobs=new Set();
    socket.addEventListener('message',event=>{
      const message=JSON.parse(event.data);
      if(message.id){
        const owned=this.pending.get(message.id);
        if(owned){this.pending.delete(message.id);clearTimeout(owned.timer);message.error?owned.reject(new Error(JSON.stringify(message.error))):owned.resolve(message.result);}
      }else{
        if(message.method==='Runtime.exceptionThrown')report.errors.push(message.params.exceptionDetails);
        if(message.method==='Runtime.consoleAPICalled'&&message.params.type==='error')report.consoleErrors.push(message.params.args.map(value=>value.value??value.description));
        if(message.method==='Runtime.consoleAPICalled')report.consoleLogs.push(message.params);
        if(message.method==='Network.responseReceived'&&new URL(message.params.response.url).pathname.startsWith('/api/')){
          const response={...message.params};
          report.responses.push(response);this.responses.set(response.requestId,response);
        }
        if(message.method==='Network.loadingFinished'&&this.responses.has(message.params.requestId)){
          const response=this.responses.get(message.params.requestId);
          const job=this.call('Network.getResponseBody',{requestId:message.params.requestId})
            .then(value=>response.body=value).catch(error=>response.bodyError=String(error)).finally(()=>this.jobs.delete(job));
          this.jobs.add(job);
        }
        if(message.method.startsWith('Network.webSocket'))report.wire.push(message);
        if(message.method==='Network.requestWillBeSent')report.requests.push(message.params);
      }
    });
  }
  async call(method,params={}){
    const id=this.next++;
    return await new Promise((resolveCall,reject)=>{
      const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error('CDP timeout: '+method));},15000);
      this.pending.set(id,{resolve:resolveCall,reject,timer});
      this.socket.send(JSON.stringify({id,method,params}));
    });
  }
  async evaluate(expression){
    const result=await this.call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
}

async function click(cdp,selector,text){
  let previous,steady=0;
  const point=await until(async()=>{
    const current=await cdp.evaluate(`(()=>{
    const element=Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(value=>${JSON.stringify(text)}===undefined||value.textContent.trim().startsWith(${JSON.stringify(text)}));
    if(!element||element.disabled)return false;
    element.scrollIntoView({block:'center'});
    const rect=element.getBoundingClientRect(),x=rect.x+rect.width/2,y=rect.y+rect.height/2;
    return rect.width&&rect.height&&element.contains(document.elementFromPoint(x,y))&&{x,y};
  })()`);
    const identity=JSON.stringify(current);
    steady=current&&identity===previous?steady+1:0;previous=identity;
    return steady>=3&&current;
  },'settled visible original control '+selector);
  await cdp.evaluate(`(()=>{
    const element=Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(value=>${JSON.stringify(text)}===undefined||value.textContent.trim().startsWith(${JSON.stringify(text)})),events=[];
    const listener=event=>events.push({trusted:event.isTrusted,matched:element.contains(event.target)});
    document.addEventListener('click',listener,true);
    window.__journeyClick={events,detach:()=>document.removeEventListener('click',listener,true)};
  })()`);
  await cdp.call('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
  await cdp.call('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
  const events=await cdp.evaluate('(()=>{const owned=window.__journeyClick;owned.detach();delete window.__journeyClick;return owned.events;})()');
  report.clicks.push({selector,text,point,events});
  assert.deepEqual(events,[{trusted:true,matched:true}]);
}

async function phase(name){
  const receipt=join(output,name+'.host.json'),state={name,snapshots:[],hostLog:'',hostErrors:'',browserErrors:''};
  report.phases.push(state);
  const environment=credentialFreeEnvironment(process.env);
  let host,browser,cdp,nextHost=1;
  const pending=new Map();
  let readyResolve,readyReject;
  const ready=new Promise((resolveReady,reject)=>{readyResolve=resolveReady;readyReject=reject;});
  const common=['--run-dir',resolve(options['run-dir']),'--output',receipt,'--preset',options.preset,'--phase',name];
  if(report.sourceHostAdaptation)common.push('--compat-script',report.sourceHostAdaptation.path);
  if(!options.workspace||!options.clock||!options['approval-artifact'])throw new Error('Controlled workspace, clock and approval artifact required');
  if(options['long-history']==='true')common.push('--history-turns','140');
  common.push('--workspace',resolve(options.workspace),'--clock',options.clock,'--approval-artifact',resolve(options['approval-artifact']));
  if(options['rc3-documents']==='true'&&name==='fresh')await prepareDocuments(resolve(options.workspace));
  if(options['file-references']==='true'){
    await mkdir(join(resolve(options.workspace),'references space'),{recursive:true});
    await writeFile(join(resolve(options.workspace),'references space','中文 file.md'),'PRIVATE_REFERENCE_BODY_MUST_NOT_ENTER_MODEL_REQUEST\n','utf8');
  }
  if(options['source-receipt']){
    const sourceReport=JSON.parse(await readFile(join(resolve(options['source-receipt']),'report.json'),'utf8'));
    assert.equal(sourceReport.status,'qualified');
    assert.equal(sourceReport.preset,options.preset);
    common.push('--port',new URL(sourceReport.phases.find(value=>value.name===name).boot.url).port);
  }
  let executable,argumentsValue;
  if(options.side==='native'){
    if(!options.python||!options.root)throw new Error('Owned native root and interpreter required');
    executable=resolve(options.python);
    argumentsValue=['-I','-B','-u',join(stage,'web_journey_native_host.py'),'--root',resolve(options.root),...common];
  }else{
    if(!options['source-root'])throw new Error('Pinned actual Source root required');
    const source=resolve(options['source-root']);
    executable=process.execPath;
    environment.TSX_TSCONFIG_PATH=join(source,'tsconfig.json');
    argumentsValue=['--import',pathToFileURL(join(source,'node_modules/tsx/dist/esm/index.mjs')).href,
      join(stage,'web_journey_source_host.mts'),'--source-root',source,...common];
  }
  const command=async commandName=>await new Promise((resolveCommand,reject)=>{
    const id=nextHost++,timer=setTimeout(()=>{pending.delete(id);reject(new Error('Host timeout: '+commandName));},20000);
    pending.set(id,{resolve:resolveCommand,reject,timer});
    host.stdin.write(JSON.stringify({id,command:commandName})+'\n');
  });
  let lastSnapshot;
  const snapshot=async()=>{
    const value=await command('snapshot'),digest=createHash('sha256').update(JSON.stringify(value)).digest('hex');
    state.snapshotReads??=[];
    if(digest!==lastSnapshot){state.snapshots.push(value);lastSnapshot=digest;}
    state.snapshotReads.push({index:state.snapshots.length-1,at:Date.now(),sha256:digest});return value;
  };
  try{
    host=spawn(executable,argumentsValue,{windowsHide:true,env:environment,cwd:output});
    host.stderr.on('data',value=>state.hostErrors+=value);
    host.on('error',readyReject);
    host.on('exit',code=>{
      readyReject(new Error('Actual host exited '+code+'; '+state.hostErrors));
      for(const owned of pending.values()){clearTimeout(owned.timer);owned.reject(new Error('Actual host exited '+code));}
      pending.clear();
    });
    createInterface({input:host.stdout}).on('line',line=>{
      if(!line.startsWith('DSH_JOURNEY ')){state.hostLog+=line+'\n';return;}
      const value=JSON.parse(line.slice(12));
      if(value.ready)readyResolve(value);
      else{
        const owned=pending.get(value.id);
        if(owned){pending.delete(value.id);clearTimeout(owned.timer);value.ok?owned.resolve(value.value):owned.reject(new Error(JSON.stringify(value)));}
      }
    });
    let bootTimer;
    const boot=await Promise.race([ready,new Promise((_,reject)=>{
      bootTimer=setTimeout(()=>reject(new Error('Actual host boot timeout')),60000);
    })]).finally(()=>clearTimeout(bootTimer));
    state.boot=boot;
    const browserHome=join(output,'browser');
    if(name==='cold'){
      const previous=report.phases[report.phases.length-2];
      assert.equal(previous.passed,true);
      const marker=join(browserHome,'DevToolsActivePort');
      const homeStat=await lstat(browserHome),markerStat=await lstat(marker);
      assert.equal(homeStat.isSymbolicLink(),false);
      assert.equal(markerStat.isSymbolicLink(),false);
      assert.equal(markerStat.isFile(),true);
      const content=await readFile(marker,'utf8');
      assert.equal(content.split('\n')[0],previous.devToolsPort);
      await unlink(marker);
      state.expiredDevToolsMarker={path:marker,content,previousBrowserClosed:true};
    }
    browser=spawn(resolve(options.browser),isolatedBrowserArguments(browserHome),{windowsHide:true});
    browser.stderr.on('data',value=>state.browserErrors+=value);
    const port=await until(async()=>{try{return (await readFile(join(browserHome,'DevToolsActivePort'),'utf8')).split('\n')[0];}catch{return false;}},'actual browser DevTools port');
    state.devToolsPort=port;
    const target=(await (await fetch('http://127.0.0.1:'+port+'/json/list')).json()).find(value=>value.type==='page');
    const socket=new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolveSocket,reject)=>{socket.addEventListener('open',resolveSocket,{once:true});socket.addEventListener('error',reject,{once:true});});
    cdp=new CDP(socket);
    state.browserIdentity=await cdp.call('Browser.getVersion');
    state.browserBinarySha256=createHash('sha256').update(await readFile(resolve(options.browser))).digest('hex');
    if(options['expected-browser-major'])assert.equal(state.browserIdentity.product.match(/\/(\d+)\./)?.[1],options['expected-browser-major']);
    state.capabilitiesBefore=await cdp.evaluate('({any:typeof AbortSignal.any,withResolvers:typeof Promise.withResolvers,timeout:typeof AbortSignal.timeout})');
    state.browser=await cdp.call('Browser.getVersion');
    await cdp.call('Runtime.enable');await cdp.call('Network.enable');await cdp.call('Page.enable');
    await cdp.call('Emulation.setDeviceMetricsOverride',{width:1680,height:1000,deviceScaleFactor:1,mobile:false});
    await cdp.call('Emulation.setLocaleOverride',{locale:'en-US'});
    await cdp.call('Emulation.setUserAgentOverride',{userAgent:state.browserIdentity.userAgent,acceptLanguage:'en-US,en;q=0.9',platform:'Win32'});
    await navigateOriginalPage(cdp,until,boot.url);
    await until(()=>cdp.evaluate('document.getElementById("root")?.childElementCount>0'),'original frontend mounted');
    state.bootGraph=await cdp.evaluate('window.__DSH_BOOT__');
    state.resourceUrlCapability=await cdp.evaluate(`(()=>{try{const value=new URL('dsh-resource://file/session/s/x');return {hostname:value.hostname,protocol:value.protocol,href:value.href,languages:navigator.languages}}catch(error){return {error:String(error)}}})()`);
    state.capabilitiesAfter=await cdp.evaluate('({any:typeof AbortSignal.any,withResolvers:typeof Promise.withResolvers,timeout:typeof AbortSignal.timeout})');
    const notice='[role="dialog"][aria-label="Internal Testing Notice"]';
    if(name==='fresh'){
      await until(()=>cdp.evaluate('document.querySelector('+JSON.stringify(notice)+')!==null'),'original testing notice');
      await click(cdp,notice+' button');
    }
    state.providerOnboardingDeferred=await deferProviderOnboarding(cdp,until,false);
    const row='[role="treeitem"][class*="sessionRow"]';
    if(options['long-history']==='true'){
      await until(()=>cdp.evaluate('Array.from(document.querySelectorAll('+JSON.stringify(row)+')).some(value=>value.textContent.includes("HISTORY_PROMPT_001"))'),'controlled historical Session row');
      await click(cdp,row,'HISTORY_PROMPT_001');
    }else if(name==='cold'){
      await until(()=>cdp.evaluate('Array.from(document.querySelectorAll('+JSON.stringify(row)+')).filter(value=>value.textContent.trim().startsWith("Controlled browser journey")).length===1'),'one controlled original persisted Session row');
      await click(cdp,row,'Controlled browser journey');
    }else{
      await until(()=>cdp.evaluate('document.querySelectorAll('+JSON.stringify(row)+').length===1'),'one controlled original blank Session row');
      await click(cdp,row);
    }
    if(options['long-history']==='true'){
      const target='nav[aria-label="Turn navigation"] button[aria-label="Load and jump to turn 1"]';
      state.historyBefore=await until(()=>cdp.evaluate(`(()=>{
        const buttons=[...document.querySelectorAll('nav[aria-label="Turn navigation"] button')];
        const unloaded=buttons.find(b=>b.getAttribute('aria-label')==='Load and jump to turn 1');
        const tail=[...document.querySelectorAll('[data-chat-flow-kind]')].some(n=>n.textContent.includes('HISTORY_PROMPT_140'));
        return unloaded&&tail&&buttons.length>=140&&{count:buttons.length,unloaded:unloaded.getAttribute('aria-label'),tailLoaded:true};
      })()`),'whole-log turn rail with initially unloaded first turn');
      await cdp.evaluate(`document.querySelector(${JSON.stringify(target)}).scrollIntoView({block:'center'})`);
      // Marks are keyboard controls; the original rail owns pointer hit testing.
      await cdp.call('Page.bringToFront');
      await cdp.evaluate(`document.querySelector(${JSON.stringify(target)}).focus()`);
      await cdp.evaluate(`(()=>{window.__historyInput=[];for(const type of ['keydown','keyup','click'])document.addEventListener(type,event=>window.__historyInput.push({type,trusted:event.isTrusted,target:event.target.outerHTML,key:event.key}),true)})()`);
      await cdp.call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',unmodifiedText:'\r',windowsVirtualKeyCode:13});
      await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
      state.historyInput=await cdp.evaluate('({events:window.__historyInput,focused:document.hasFocus()})');
      state.historyJump=await until(()=>cdp.evaluate(`(()=>{
        const prompt=[...document.querySelectorAll('[data-chat-flow-kind]')].find(n=>n.textContent.includes('HISTORY_PROMPT_001'));
        const active=document.querySelector('nav[aria-label="Turn navigation"] button[aria-current="true"]');
        const loaded=document.querySelector('nav[aria-label="Turn navigation"] button[aria-label="Jump to turn 1"]');
        if(!prompt||!loaded)return false;
        const rect=prompt.getBoundingClientRect();
        return rect.top>=0&&rect.top<innerHeight&&{prompt:prompt.textContent,loaded:loaded.getAttribute('aria-label'),active:active?.getAttribute('aria-label')??null,top:rect.top,viewportHeight:innerHeight};
      })()`),'actual loadThrough jump to oldest prompt in viewport',60000);
      const screenshot=await cdp.call('Page.captureScreenshot');
      await writeFile(join(output,name+'.history-jump.png'),Buffer.from(screenshot.data,'base64'));
    }
    if(options['file-references']==='true'){
      const before=await until(async()=>{const value=await snapshot();return value.attached&&value.agentStatus==='idle'&&value;},'selected session attached before reference input');
      await click(cdp,'[data-composer-input][contenteditable="true"]');
      await cdp.call('Input.insertText',{text:'@"references space/'});
      state.fileReferenceCandidates=await until(()=>cdp.evaluate(`(()=>{
        const rows=[...document.querySelectorAll('[role="listbox"] [role="option"]')].map(row=>row.textContent);
        return rows.some(text=>text.includes('中文 file.md'))&&rows;
      })()`),'actual original @file menu from the workspace');
      await cdp.call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
      await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
      state.fileReferenceSelection=await until(()=>cdp.evaluate(`(()=>{
        const composer=document.querySelector('[data-composer-input]');
        const chip=composer?.querySelector('[data-composer-chip]');
        return chip?.textContent.includes('中文 file.md')&&{text:composer.textContent,html:composer.innerHTML};
      })()`),'actual file mention selection in original composer');
      assert.ok(!state.fileReferenceSelection.html.includes('PRIVATE_REFERENCE_BODY'));
      const referenceScreenshot=await cdp.call('Page.captureScreenshot');
      await writeFile(join(output,name+'.file-reference.png'),Buffer.from(referenceScreenshot.data,'base64'));
      const after=await snapshot();
      assert.equal(createHash('sha256').update(JSON.stringify(after.events)).digest('hex'),
        createHash('sha256').update(JSON.stringify(before.events)).digest('hex'),'file selection must not change durable history');
      assert.deepEqual(after.requests,before.requests);
      await cdp.call('Input.dispatchKeyEvent',{type:'keyDown',key:'a',code:'KeyA',windowsVirtualKeyCode:65,modifiers:2});
      await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',key:'a',code:'KeyA',windowsVirtualKeyCode:65,modifiers:2});
      await cdp.call('Input.dispatchKeyEvent',{type:'keyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
      await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8});
      await until(()=>cdp.evaluate('!document.querySelector("[data-composer-input]")?.textContent'),'reference draft cleared by actual keys');
      // Lexical applies its selection update after the DOM deletion. Let that
      // owned update finish before the next, distinct user gesture.
      await cdp.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
    }
    const submissions=new Map();
    const submit=async scenario=>{
      // A cold row click hydrates asynchronously. Freeze a real attached idle
      // baseline before sending, so an older matching answer cannot satisfy it.
      await until(async()=>{const value=await snapshot();return value.attached&&value.agentStatus==='idle';},
        'selected session attached and idle before '+scenario);
      await click(cdp,'[data-composer-input][contenteditable="true"]');
      await cdp.call('Input.dispatchKeyEvent',{type:'keyDown',key:'End',code:'End',windowsVirtualKeyCode:35});
      await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',key:'End',code:'End',windowsVirtualKeyCode:35});
      await cdp.call('Input.insertText',{text:scenario});
      state.submittedInputs??=[];
      state.submittedInputs.push(await cdp.evaluate(`({scenario:${JSON.stringify(scenario)},
        text:document.querySelector('[data-composer-input]')?.textContent,
        active:document.activeElement?.outerHTML,buttons:[...document.querySelectorAll('[data-composer-card] button')]
          .map(button=>({label:button.getAttribute('aria-label'),disabled:button.disabled}))})`));
      const before=await snapshot();
      submissions.set(scenario,before.events.at(-1)?.seq??-1);
      await click(cdp,'[data-composer-card] button[aria-label="Send message"], [data-composer-card] button[aria-label="发送消息"]');
    };
    const complete=async scenario=>await until(async()=>{
      const value=await snapshot();
      assert.ok(submissions.has(scenario));
      return value.agentStatus==='idle'&&value.events.some(event=>event.seq>submissions.get(scenario)&&event.type==='assistant/message'
        &&JSON.stringify(event.data).includes(scenario+'_FINAL'))&&value;
    },'actual model/tool next request '+scenario,60000);
    const scenarios=name==='cold'?['WEB_REOPEN']:options.preset==='minimal'?['WEB_TOOL','WEB_CANCEL']:
      ['WEB_TOOL','WEB_QUESTION','WEB_APPROVAL','WEB_PLAN','WEB_CANCEL',...(options.preset==='cordis'?['WEB_CORDIS']:[])];
    state.scenarios=scenarios;
    for(const scenario of scenarios){
      if(scenario==='WEB_PLAN'){
        await submit('/plan');
        await until(async()=>{const value=await snapshot();return value.events.some(event=>event.type==='plan/mode'&&event.data.active===true);},'logged plan-mode entry');
      }
      await submit(scenario);
      if(scenario==='WEB_PLAN'){
        state.planReviewPanel=await until(()=>cdp.evaluate(`(()=>{
          const panel=document.querySelector('[data-plan-review-key]');
          if(!panel)return false;
          const button=panel.querySelector('button:last-child');
          if(!button||button.disabled)return false;
          return {text:panel.textContent,approveLabel:button.textContent};
        })()`),'original plan review panel');
        await click(cdp,'[data-plan-review-key] button:last-child');
      }else if(scenario==='WEB_QUESTION'){
        await click(cdp,'[data-question-key] button[role="radio"][aria-label="Proceed"]');
        await click(cdp,'[data-question-key] footer > div:last-child button:last-child');
      }else if(scenario==='WEB_APPROVAL'){
        await click(cdp,'[data-approval-key] button:last-child');
      }else if(scenario==='WEB_CANCEL'){
        await until(async()=>{const value=await snapshot();return value.cancellation.some(item=>item.attached===1&&!item.detached);},'actual model stream awaiting cancellation');
        await click(cdp,'[data-composer-card] button[aria-label="Stop generating"], [data-composer-card] button[aria-label="停止生成"]');
        await until(async()=>{const value=await snapshot();return value.agentStatus==='idle'&&value.cancellation.some(item=>item.finallyAborted&&item.detached===1);},'real browser cancellation disposed model listener');
        continue;
      }
      await complete(scenario);
    }
    if(options['rc3-reconnect']==='true'){
      const before=await snapshot(),start=report.wire.length;
      const prior=report.wire.filter(row=>row.method==='Network.webSocketHandshakeResponseReceived'
        &&row.params.response.status===101).map(row=>row.params.requestId);
      assert.ok(prior.length,'The actual browser must have an established WebSocket');
      state.reconnect={fault:await command('disconnect'),prior};
      state.reconnect.newConnection=await until(()=>{
        const wire=report.wire.slice(start);
        const closed=wire.filter(row=>row.method==='Network.webSocketClosed'&&prior.includes(row.params.requestId));
        const opened=wire.find(row=>row.method==='Network.webSocketHandshakeResponseReceived'
          &&row.params.response.status===101&&!prior.includes(row.params.requestId));
        return closed.length&&opened&&{closed:closed.map(row=>row.params.requestId),opened:opened.params.requestId};
      },'original client reconnects after physical socket loss');
      const recovered=await snapshot();
      assert.deepEqual(recovered.header,before.header,'Reconnect retains the selected session');
      assert.deepEqual(recovered.events,before.events,'Transport recovery does not mutate durable history');
      await submit('WEB_REOPEN');
      const resumed=await complete('WEB_REOPEN');
      state.reconnect.resumedSeq=resumed.events.at(-1).seq;
      state.reconnect.previousSeq=before.events.at(-1).seq;
      assert.ok(state.reconnect.resumedSeq>state.reconnect.previousSeq);
      await until(()=>cdp.evaluate('document.body.innerText.includes("WEB_REOPEN_FINAL")'),'reconnected original UI receives model/tool completion');
    }
    if(options['rc3-documents']==='true')await documentJourney({cdp,click,until,state,output,phase:name});
    if(options['rc3-deliveries']==='true'){
      assert.notEqual(options.preset,'minimal','The original Minimal preset does not expose present');
      const filename='rc3-delivery-'+name+'.md',path=join(resolve(options.workspace),filename);
      await writeFile(path,'# RC3 delivery original '+name+'\n','utf8');
      const scenario='WEB_DELIVER_'+name.toUpperCase();
      await submit(scenario);const delivered=await complete(scenario);
      const presented=delivered.events.findLast(event=>event.type==='deliverables/presented'&&event.data.files.some(file=>file.path===filename));
      assert.ok(presented,'The actual present tool must append a durable delivery');
      state.delivery={presented};
      await writeFile(path,'# RC3 delivery refreshed '+name+'\n','utf8');
      await click(cdp,'[data-presented-file] button[title$="'+filename+'"]');
      const heading='[data-document-preview][data-textpreview-url$="/'+filename+'"] [data-document-markdown] h1';
      state.delivery.heading=await until(()=>cdp.evaluate(`document.querySelector(${JSON.stringify(heading)})?.textContent===${JSON.stringify('RC3 delivery refreshed '+name)}&&document.querySelector(${JSON.stringify(heading)}).textContent`),'presented file reads current source bytes');
      state.delivery.card=await cdp.evaluate(`Array.from(document.querySelectorAll('[data-presented-file]')).find(n=>n.textContent.includes(${JSON.stringify(filename)}))?.textContent`);
      assert.ok(state.delivery.card.includes('Controlled current source delivery'));
    }
    if(options['rc3-application']==='true')await applicationJourney({cdp,click,until,state,phase:name,snapshot,submit,complete,workspace:resolve(options.workspace),runDir:resolve(options['run-dir'])});
    state.cssMixAdapter=await cdp.evaluate("JSON.parse(JSON.stringify(window[Symbol.for('deepseek-win7.host.color-mix')]?.current?.facts??null))");
    state.cssMixPalette=await cdp.evaluate(String.raw`(()=>{const n=document.querySelector('[class*=trajectory]')??document.querySelector('[class*=Trajectory]')??document.body;const s=getComputedStyle(n);return Object.fromEntries([...new Set([...document.querySelectorAll('style')].flatMap(t=>[...t.textContent.matchAll(/var\((--[^,)]+)/g)].map(m=>m[1])))].filter(k=>k.startsWith('--dsw-')||k.startsWith('--trajectory-')).map(k=>[k,s.getPropertyValue(k).trim()]));})()`);
    state.cssMixDynamic=await cdp.evaluate(`(async()=>{
      const wait=async()=>{for(let i=0;i<4;i++)await new Promise(resolve=>requestAnimationFrame(resolve));};
      const tag=document.createElement('style');const original='.dsh-probe-paint{background-color:color-mix(in srgb,var(--dsh-probe-color) 25%,transparent)}';tag.textContent=original;document.head.append(tag);
      const outer=document.createElement('div');outer.style.setProperty('--dsh-probe-color','rgb(80,120,160)');
      const inner=document.createElement('div');inner.style.setProperty('--dsh-probe-color','rgb(160,80,40)');outer.append(inner);
      const a=document.createElement('div'),b=document.createElement('div');a.className=b.className='dsh-probe-paint';outer.append(a);inner.append(b);document.body.append(outer);await wait();
      const values=[];const read=phase=>values.push({phase,a:getComputedStyle(a).backgroundColor,b:getComputedStyle(b).backgroundColor});read('initial');
      outer.style.setProperty('--dsh-probe-color','rgb(40,60,80)');await wait();read('ancestor-change');
      inner.style.removeProperty('--dsh-probe-color');await wait();read('local-removal');
      const immutable=tag.textContent===original;
      const generatedName=tag.nextSibling?.textContent?.match(/--dsh-host-mix-[0-9]+/)?.[0]??null;const beforeRemoval=generatedName?outer.style.getPropertyValue(generatedName):null;
      tag.textContent='.dsh-probe-paint{background-color:rgb(11,22,33)}';await wait();read('style-replaced-without-mix');
      tag.textContent=original;await wait();read('style-mix-restored');
      tag.remove();await wait();read('style-unmounted');const afterRemoval=generatedName?outer.style.getPropertyValue(generatedName):null;const remainingOwnProperties=Array.from(outer.style).filter(name=>name.startsWith('--dsh-host-mix-'));outer.remove();await wait();
      const originalDark=document.body.hasAttribute('data-ds-dark-theme');document.body.toggleAttribute('data-ds-dark-theme',false);await wait();
      const themeStyle=document.createElement('style');themeStyle.textContent='.dsh-probe-theme{background-color:color-mix(in srgb,var(--dsw-alias-bg-base) 60%,transparent)}';document.head.append(themeStyle);
      const theme=document.createElement('div');theme.className='dsh-probe-theme';document.body.append(theme);await wait();
      const dark=document.body.hasAttribute('data-ds-dark-theme');const themes=[];
      const readTheme=phase=>themes.push({phase,dark:document.body.hasAttribute('data-ds-dark-theme'),base:getComputedStyle(theme).getPropertyValue('--dsw-alias-bg-base').trim(),paint:getComputedStyle(theme).backgroundColor});readTheme('initial');
      document.body.toggleAttribute('data-ds-dark-theme',!dark);await wait();readTheme('theme-toggled');
      document.body.toggleAttribute('data-ds-dark-theme',dark);await wait();readTheme('theme-restored');
      themeStyle.remove();theme.remove();document.body.toggleAttribute('data-ds-dark-theme',originalDark);await wait();
      return {values,themes,immutable,ownedProperty:{generatedName,beforeRemoval,afterRemoval,remainingOwnProperties},adapter:window[Symbol.for('deepseek-win7.host.color-mix')]?.current?.facts??null};
    })()`);

    state.cssLifecycle=await cdp.evaluate(`(async()=>{
      const key=Symbol.for('deepseek-win7.host.color-mix'),managerPresent=window[key]!==undefined,manager=window[key]??{current:{active:false},install(){return this.current;},dispose(){}};
      const wait=async()=>{for(let i=0;i<5;i++)await new Promise(done=>requestAnimationFrame(done));};
      const tag=document.createElement('style'), original='.dsh-lifecycle-paint{background-color:color-mix(in srgb,var(--dsh-lifecycle-color) 25%,transparent)}';
      tag.textContent=original;document.head.append(tag);
      const node=document.createElement('div');node.className='dsh-lifecycle-paint';node.style.setProperty('--dsh-lifecycle-color','rgb(80,120,160)');document.body.append(node);await wait();
      const rows=[],read=phase=>rows.push({phase,paint:getComputedStyle(node).backgroundColor});read('active');
      tag.media='not all';await wait();read('media-disabled');tag.media='all';await wait();read('media-restored');
      tag.sheet.disabled=true;await wait();read('sheet-disabled');tag.sheet.disabled=false;await wait();read('sheet-restored');
      const previous=manager.current,clonesBefore=[...document.querySelectorAll('style')].filter(style=>style.textContent.includes('--dsh-host-mix-')).length;
      manager.dispose();await wait();read('disposed');
      const removed={symbolAbsent:window[key]===undefined,clones:[...document.querySelectorAll('style')].filter(style=>style.textContent.includes('--dsh-host-mix-')).length,
        inline:[...document.querySelectorAll('[style]')].flatMap(element=>[...element.style].filter(name=>name.startsWith('--dsh-host-mix-'))),facts:previous.facts??null};
      const beforeMutation=previous.facts?.refreshes;node.classList.add('changed-after-dispose');await wait();const afterMutation=previous.facts?.refreshes;
      const savedStyle=document.documentElement.getAttribute('style');document.documentElement.style.setProperty('--dsh-host-mix-0','original-owner-value','important');
      const once=manager.install();await wait();read('reinstalled');const twice=manager.install();await wait();read('reinstalled-twice');
      const clonesAfter=[...document.querySelectorAll('style')].filter(style=>style.textContent.includes('--dsh-host-mix-')).length;
      manager.dispose();await wait();const preserved={value:document.documentElement.style.getPropertyValue('--dsh-host-mix-0'),priority:document.documentElement.style.getPropertyPriority('--dsh-host-mix-0')};
      if(savedStyle===null)document.documentElement.removeAttribute('style');else document.documentElement.setAttribute('style',savedStyle);
      manager.install();await wait();tag.remove();node.remove();await wait();
      return {managerPresent,rows,originalImmutable:tag.textContent===original,active:previous.active,clonesBefore,clonesAfter,removed,beforeMutation,afterMutation,
        replacedOwnerDisposed:once.facts?.disposed??null,preserved,final:manager.current.facts??null};
    })()`);
    state.cssInvalidValue=await cdp.evaluate(`(async()=>{
      const wait=async()=>{for(let i=0;i<5;i++)await new Promise(done=>requestAnimationFrame(done));};
      const style=document.createElement('style');style.textContent='.dsh-fallback-paint{background-color:color-mix(in srgb,var(--dsh-unset-color,rgb(80,120,160)) 25%,transparent)}.dsh-invalid-paint{background-color:color-mix(in srgb,var(--dsh-cyclic-color) 25%,transparent)}';document.head.append(style);
      const outer=document.createElement('div');outer.style.setProperty('--dsh-cyclic-color','rgb(40,60,80)');
      const fallback=document.createElement('div');fallback.className='dsh-fallback-paint';
      const cyclic=document.createElement('div');cyclic.className='dsh-invalid-paint';cyclic.style.setProperty('--dsh-cyclic-color','var(--dsh-cyclic-color)');
      const valid=document.createElement('div');valid.className='dsh-invalid-paint';outer.append(fallback,cyclic,valid);document.body.append(outer);await wait();
      const observed={fallback:getComputedStyle(fallback).backgroundColor,cyclic:getComputedStyle(cyclic).backgroundColor,inherited:getComputedStyle(valid).backgroundColor,
        original:style.textContent,errors:window[Symbol.for('deepseek-win7.host.color-mix')]?.current?.facts?.errors??[],facts:window[Symbol.for('deepseek-win7.host.color-mix')]?.current?.facts??null};
      style.remove();outer.remove();await wait();return observed;
    })()`);
    async function listenerCounts(){
      const values={};
      for(const target of ['window','document']){
        const evaluated=await cdp.call('Runtime.evaluate',{expression:target,returnByValue:false});
        const result=await cdp.call('DOMDebugger.getEventListeners',{objectId:evaluated.result.objectId});
        values[target]={};
        for(const listener of result.listeners)values[target][listener.type]=(values[target][listener.type]??0)+1;
        await cdp.call('Runtime.releaseObject',{objectId:evaluated.result.objectId});
      }
      return values;
    }
    const before=await listenerCounts();
    const active=await cdp.evaluate(`(async()=>{const key=Symbol.for('deepseek-win7.host.color-mix');window.__dshResearchManager=window[key];const active=window[key]!==undefined;window[key]?.dispose();for(let i=0;i<5;i++)await new Promise(done=>requestAnimationFrame(done));return active;})()`);
    const removed=await listenerCounts();
    await cdp.evaluate(`(async()=>{window.__dshResearchManager?.install();delete window.__dshResearchManager;for(let i=0;i<5;i++)await new Promise(done=>requestAnimationFrame(done));})()`);
    const restored=await listenerCounts();
    state.cssListenerOwnership={active,before,removed,restored};
    await cdp.evaluate(`(async()=>{const style=document.createElement('style');style.id='dsh-controlled-media-style';style.textContent='.dsh-controlled-media{--dsh-media-color:rgb(80,120,160);background-color:color-mix(in srgb,var(--dsh-media-color) 25%,transparent)}@media print{.dsh-controlled-media{--dsh-media-color:rgb(40,60,80)}}';const node=document.createElement('div');node.id='dsh-controlled-media-node';node.className='dsh-controlled-media';document.head.append(style);document.body.append(node);for(let i=0;i<5;i++)await new Promise(done=>requestAnimationFrame(done));})()`);
    const media=[];
    for(const value of ['screen','print','screen']){
      await cdp.call('Emulation.setEmulatedMedia',{media:value});
      media.push(await cdp.evaluate(`(async()=>{for(let i=0;i<5;i++)await new Promise(done=>requestAnimationFrame(done));const node=document.getElementById('dsh-controlled-media-node');return {media:${JSON.stringify(value)},paint:getComputedStyle(node).backgroundColor,variable:getComputedStyle(node).getPropertyValue('--dsh-media-color').trim()};})()`));
    }
    await cdp.evaluate(`(async()=>{document.getElementById('dsh-controlled-media-style').remove();document.getElementById('dsh-controlled-media-node').remove();for(let i=0;i<5;i++)await new Promise(done=>requestAnimationFrame(done));})()`);
    state.cssMediaConditions=media;
    state.final=await snapshot();
    state.finalText=await cdp.evaluate('document.body.innerText');
    await Promise.allSettled([...cdp.jobs]);
    const selectedPreset=state.final.events.findLast(event=>event.type==='agent-preset/selected');
    assert.equal(selectedPreset?.data.agentPreset??state.final.header.agentPreset,options.preset);
    if(options.preset==='minimal'){
      state.toolRegistrationOrder=state.final.tools;
      const expected=options.side==='source'?['pwsh']:['pwsh','str_replace_editor'];
      assert.deepEqual([...state.final.tools].sort(),expected);
      state.minimalProductAdaptation=options.side==='native'?'Retained editor alongside the rc.3 shell-only Source preset':null;
    }
    assert.deepEqual(report.errors,[]);assert.deepEqual(report.consoleErrors,[]);
    await closeOriginalBrowser(cdp,browser,until);
    await command('shutdown');
    await until(()=>host.exitCode!==null||host.signalCode!==null,'actual host naturally exited',15000);
    assert.equal(host.exitCode,0);
    assert.equal(state.hostErrors,'');
    state.hostReceipt=JSON.parse(await readFile(receipt,'utf8'));
    state.passed=true;
  }catch(error){
    state.failure=String(error);
    if(cdp)state.documentFailure=await cdp.evaluate(`(()=>{
      const rows=[];const element=document.querySelector('[data-document-preview] [role="alert"]')??document.querySelector('[data-textpreview-state]');
      const errorValue=(e,depth=0)=>e&&depth<3?{name:e.name,message:e.message,stack:e.stack,type:e.type,
        cause:errorValue(e.cause,depth+1)}:null;
      let fiber=element&&element[Object.keys(element).find(key=>key.startsWith('__reactFiber$'))];
      for(let i=0;fiber&&i<16;i++,fiber=fiber.return){
        const props=fiber.memoizedProps;
        const failures=[];let hook=fiber.memoizedState;
        for(let j=0;hook&&j<30;j++,hook=hook.next)if(hook.memoizedState?.error)failures.push(errorValue(hook.memoizedState.error));
        rows.push({name:fiber.type?.name??null,keys:props&&Object.keys(props),tab:props?.tab,contentId:props?.contentId,
          state:props?.state,info:props?.info,failures});
      }
      return {rows,html:element?.outerHTML.slice(0,16000),facadeKeys:Object.keys(window.__ModuleLoader__??{}),
        workerFacts:globalThis[Symbol.for('deepseek-win7.host.workers')]?.facts??null};
    })()`);
    if(cdp)state.historyFailure=await cdp.evaluate(`(()=>({active:[...document.querySelectorAll('nav[aria-label="Turn navigation"] button[aria-current]')].map(n=>n.outerHTML),
      prompts:[...document.querySelectorAll('[data-chat-flow-kind]')].filter(n=>n.textContent.includes('HISTORY_PROMPT_001')).map(n=>({text:n.textContent,top:n.getBoundingClientRect().top})),
      focus:document.activeElement?.outerHTML}))()`);
    throw error;
  }finally{
    if(cdp?.socket.readyState===1){
      try{
        state.finalText??=await cdp.evaluate('document.body.innerText');
        await Promise.allSettled([...cdp.jobs]);
        const screenshot=await cdp.call('Page.captureScreenshot');
        await writeFile(join(output,name+'.png'),Buffer.from(screenshot.data,'base64'));
        await closeOriginalBrowser(cdp,browser,until);
      }catch(error){
        state.browserCleanupFailure=String(error);
        if(!state.failure)throw error;
      }
    }
    if(host?.exitCode===null&&host.signalCode===null){
      try{await command('shutdown');await until(()=>host.exitCode!==null||host.signalCode!==null,'failed host owned shutdown',15000);}
      catch(error){state.shutdownFailure=String(error);host.kill();}
    }
  }
}

try{
  if(options.side==='native')report.compatibilitySha256=(await browserCompatibilityInput(join(resolve(options.root),'dsh/host/browser_compat'))).sha256;
  if(options.archive)report.archiveSha256=createHash('sha256').update(await readFile(resolve(options.archive))).digest('hex');
  await assert.rejects(lstat(resolve(options['approval-artifact'])),error=>error.code==='ENOENT');
  await phase('fresh');
  await phase('cold');
  report.status='qualified';
}catch(error){report.status='rejected';report.failure=String(error);process.exitCode=1;}
finally{
  if(report.status==='qualified'){
    const profile=join(output,'browser');
    assert.equal((await lstat(profile)).isSymbolicLink(),false);
    assert.equal(resolve(dirname(profile)),output);
    await rm(profile,{recursive:true,maxRetries:5,retryDelay:100});
    report.cleanup={browserProfile:'removed after both physical browser/Host exits'};
  }
  const safe=JSON.stringify(report,null,2).replace(/([?&]token=)[^&"\s]*/g,'$1[redacted]');
  await writeFile(join(output,'report.json'),safe+'\n',{flag:'wx',encoding:'utf8'});
}

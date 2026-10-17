/** External CDP observer: run the actual packaged executable with its own Python. */
import assert from 'node:assert/strict';
import {spawn,execFile} from 'node:child_process';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {credentialFreeEnvironment,deferProviderOnboarding} from '../browser_onboarding.mjs';

const options=Object.fromEntries(process.argv.slice(2).reduce((rows,value,index,args)=>{
  if(value.startsWith('--'))rows.push([value.slice(2),args[index+1]]);return rows;
},[]));
assert.ok(options.executable&&options.output,'Explicit packaged executable and fresh output required');
const output=resolve(options.output),executable=resolve(options.executable);
const development=Boolean(options['development-root']);
assert.equal(Boolean(options['development-python']),development,'Development root and interpreter must be explicit together');
await mkdir(output);
const report={status:'running',mode:development?'development':'packaged',checks:[],errors:[],consoleErrors:[],stderr:'',timeline:[]};
let phase='startup';
function enter(value){phase=value;report.timeline.push({phase,time:new Date().toISOString()});}
function observation(value){return {phase,time:new Date().toISOString(),value};}
const env={...credentialFreeEnvironment(process.env),DSH_HOME:join(output,'home'),PYTHONDONTWRITEBYTECODE:'1'};
const launchArgs=development?[join(resolve(options['development-root']),'apps/desktop'),'--root',resolve(options['development-root']),
  '--python',resolve(options['development-python']),'--home',env.DSH_HOME]:[];
const child=spawn(executable,[...launchArgs,'--remote-debugging-port=0'],{windowsHide:true,env,stdio:['ignore','pipe','pipe']});
child.once('exit',(code,signal)=>{report.processExit={time:new Date().toISOString(),phase,code,signal};});
child.stdout.on('data',data=>{report.stdout=(report.stdout??'')+data.toString();});
let address;
child.stderr.on('data',data=>{report.stderr+=data.toString();address??=report.stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/)?.[1];});
const delay=ms=>new Promise(done=>setTimeout(done,ms));
async function until(read,description,timeout=60000){
  const end=Date.now()+timeout;let value;
  while(Date.now()<end){value=await read();if(value)return value;await delay(100);}
  throw new Error('Timed out: '+description+'; last='+JSON.stringify(value));
}
class CDP{
  constructor(socket){this.socket=socket;this.pending=new Map();this.next=1;
    socket.addEventListener('close',()=>{for(const owned of this.pending.values()){
      clearTimeout(owned.timer);owned.reject(new Error('CDP connection closed'));}this.pending.clear();});
    socket.addEventListener('message',event=>{
      const message=JSON.parse(event.data);
      if(message.id){const owned=this.pending.get(message.id);if(owned){clearTimeout(owned.timer);this.pending.delete(message.id);message.error?owned.reject(new Error(JSON.stringify(message.error))):owned.resolve(message.result);}}
      else if(message.method==='Runtime.exceptionThrown')report.errors.push(observation(message.params));
      else if(message.method==='Runtime.consoleAPICalled'&&message.params.type==='error')report.consoleErrors.push(observation(message.params.args.map(arg=>arg.value??arg.description)));
    });
  }
  call(method,params={}){const id=this.next++;return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error('CDP deadline: '+method));},15000);
    this.pending.set(id,{resolve,reject,timer});this.socket.send(JSON.stringify({id,method,params}));
  });}
  async evaluate(expression){const result=await this.call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;}
}
let cdp;
try{
  await until(()=>address,'packaged Electron debugger');
  const base='http://'+new URL(address).host;
  report.browser=await(await fetch(base+'/json/version',{signal:AbortSignal.timeout(5000)})).json();
  assert.match(report.browser.Browser,/Chrome\/108\./);
  const page=await until(async()=>{const rows=await(await fetch(base+'/json/list',{signal:AbortSignal.timeout(5000)})).json();return rows.find(row=>row.type==='page'&&row.url.startsWith('dsh-app://app/'));},'packaged application target');
  const socket=new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((done,reject)=>{socket.addEventListener('open',done,{once:true});socket.addEventListener('error',reject,{once:true});});
  cdp=new CDP(socket);
  await cdp.call('Runtime.enable');await cdp.call('Page.enable');
  await until(()=>cdp.evaluate(`document.readyState==='complete'&&!!document.querySelector('#root')?.children.length&&!!globalThis.__DSH_TRANSPORT__`),'original packaged application');
  enter('onboarding');await deferProviderOnboarding(cdp,until,false);
  report.renderer=await cdp.evaluate(`({url:location.href,node:typeof process,require:typeof require,transport:window.__DSH_TRANSPORT__?.ownsHost,text:document.body.innerText.slice(0,4000)})`);
  assert.equal(report.renderer.node,'undefined');assert.equal(report.renderer.require,'undefined');
  assert.equal(report.renderer.transport,true);report.checks.push('original-packaged-renderer-without-node');
  enter('settings');report.settings=await cdp.evaluate(`(async()=>{const response=await fetch('/api/settings/describe',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:'packaged',method:'settings/describe',payload:{args:{}}})});return response.json()})()`);
  assert.equal(report.settings.result.ok,true);assert.ok(report.settings.result.value.namespaces.length);report.checks.push('packaged-python-settings-rpc');
  enter('stream');report.baseline=await cdp.evaluate(`(async()=>{const abort=new AbortController();const response=await fetch('/.dsh/remote-stream',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({endpoint:'workspace/follow',payload:{args:{}}}),signal:abort.signal});const reader=response.body.getReader();let text='';while(!text.includes('\\n')){const next=await reader.read();if(next.done)throw new Error('premature workspace EOF');text+=new TextDecoder().decode(next.value)}abort.abort();return JSON.parse(text.split('\\n')[0])})()`);
  assert.equal(report.baseline.type,'baseline');report.checks.push('packaged-stream-baseline-and-cancellation');
  enter('single-instance');const second=spawn(executable,launchArgs,{windowsHide:true,env,stdio:['ignore','pipe','pipe']});
  second.stdout.resume();second.stderr.resume();
  await until(()=>second.exitCode!==null,'second packaged instance exited',15000);
  assert.equal(second.exitCode,0);assert.equal(child.exitCode,null);report.checks.push('actual-single-instance-ownership');
  enter('stable');await delay(2000);
  assert.deepEqual(report.errors,[]);assert.deepEqual(report.consoleErrors,[]);
  const screenshot=await cdp.call('Page.captureScreenshot');await writeFile(join(output,'main.png'),Buffer.from(screenshot.data,'base64'));
  enter('closing');try{await cdp.call('Browser.close');}catch(error){if(socket.readyState!==3)throw error;}
  await until(()=>child.exitCode!==null,'packaged application graceful quit',20000);
  assert.equal(child.exitCode,0);report.checks.push('packaged-graceful-shutdown');
  enter('closed');assert.deepEqual(report.errors,[]);assert.deepEqual(report.consoleErrors,[]);
  report.checks.push('complete-observed-lifecycle-without-renderer-errors');
  if(development)report.checks=report.checks.map(value=>value.replace('packaged','development'));
  report.status=development?'development-checks-passed':'qualified';
}catch(error){report.status='rejected';report.failure=error.stack;process.exitCode=1;}
finally{
  if(child.exitCode===null){
    await new Promise(done=>execFile(join(process.env.SystemRoot||'C:\\Windows','System32/taskkill.exe'),['/PID',String(child.pid),'/T','/F'],{windowsHide:true},()=>done()));
    await until(()=>child.exitCode!==null,'owned packaged tree terminated',15000).catch(error=>{report.cleanupFailure=String(error);});
  }
  cdp?.socket.close();
  await writeFile(join(output,'report.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({status:report.status,checks:report.checks,failure:report.failure}));
}

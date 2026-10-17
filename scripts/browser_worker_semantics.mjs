/** Ownership tests for the host adapter; actual Chromium rendering is separate. */
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {browserCompatibilityInput} from './browser_compat_input.mjs';
const {script}=await browserCompatibilityInput(fileURLToPath(new URL('../dsh/host/browser_compat/',import.meta.url)));
const urls=new Map(),revoked=[],instances=[],brands=new WeakSet();let sequence=0,checks=0;
const check=(actual,expected)=>{assert.deepEqual(actual,expected);checks++;};
class HostURL extends URL {
  static createObjectURL(blob){if(!(blob instanceof Blob))throw new TypeError('Blob required');const url='blob:owned/'+(++sequence);urls.set(url,blob);return url;}
  static revokeObjectURL(value){if(!arguments.length)throw new TypeError('URL required');const url=String(value);revoked.push(url);urls.delete(url);}
}
class NativeWorker extends EventTarget {
  constructor(url,options){super();if(options?.fail)throw new Error('constructor failure');brands.add(this);this.url=url;this.options=options;this.blob=urls.get(url);this.stops=0;instances.push(this);}
  terminate(){if(!brands.has(this))throw new TypeError('Worker required');this.stops++;}
}
const create=HostURL.createObjectURL,revoke=HostURL.revokeObjectURL,terminate=NativeWorker.prototype.terminate;
const realm=vm.createContext({URL:HostURL,URLSearchParams,Worker:NativeWorker,Blob,AbortSignal,AbortController,EventTarget,Event});
vm.runInContext('delete globalThis.Iterator;',realm);
vm.runInContext(script,realm);
const facade=realm.Worker,manager=vm.runInContext("globalThis[Symbol.for('deepseek-win7.host.workers')]",realm);
check(!!manager?.active,true);check(facade.prototype===NativeWorker.prototype,true);
const original=new Blob(['postMessage("original bytes");'],{type:'text/javascript'});
const originalUrl=realm.URL.createObjectURL(original);
const options={name:'dsh-file-upload',credentials:'omit'};
const worker=new facade(originalUrl,options);
realm.URL.revokeObjectURL(originalUrl);
check(urls.has(originalUrl),false);check(worker instanceof NativeWorker,true);check(worker instanceof facade,true);
check(worker.options===options,true);check((await worker.blob.text()).endsWith('\n'+await original.text()),true);
check((await worker.blob.text()).includes('Promise.withResolvers'),true);
check(manager.facts.activeUrls,1);worker.dispatchEvent(new Event('message'));
check(manager.facts.activeUrls,0);check(manager.facts.activeWorkers,1);
worker.terminate();worker.terminate();check(manager.facts.terminated,1);check(worker.stops,2);
assert.throws(()=>NativeWorker.prototype.terminate.call({}),TypeError);checks++;
const failureUrl=realm.URL.createObjectURL(original);
assert.throws(()=>new facade(failureUrl,{name:'dsh-pdf',fail:true}),/constructor failure/);checks++;
check(manager.facts.activeUrls,0);
class Child extends facade {}
const child=new Child(failureUrl,{name:'dsh-pdf'});check(child instanceof Child,true);
const failure=new Event('error');Object.defineProperty(failure,'message',{value:'real worker error'});child.dispatchEvent(failure);
check(Array.from(manager.facts.errors,row=>({...row})),[{name:'dsh-pdf',message:'real worker error',filename:null,line:null,column:null}]);check(manager.facts.activeUrls,0);child.terminate();
const unknown=new facade(failureUrl,{name:'unrecognized'});check(unknown.url,failureUrl);
let coercions=0;const objectUrl={toString(){coercions++;return failureUrl;}};
new facade(objectUrl,{name:'dsh-pdf'});check(coercions,0); // Forward unknown arguments to the native constructor unchanged.
realm.URL.revokeObjectURL(objectUrl);check(coercions,1);
assert.throws(()=>realm.URL.revokeObjectURL(),TypeError);checks++;
const pendingUrl=realm.URL.createObjectURL(original);
const first=new facade(pendingUrl,{name:'dsh-pdf'}),second=new facade(pendingUrl,{name:'dsh-file-upload'});
vm.runInContext(script,realm);check(realm.Worker===facade,true);check(manager.facts.activeWorkers,2);
const foreignCreate=()=>{};realm.URL.createObjectURL=foreignCreate;
manager.dispose();manager.dispose();check(first.stops,1);check(second.stops,1);
check(manager.facts.activeUrls,0);check(manager.facts.activeWorkers,0);check(manager.active,false);
check(realm.Worker===NativeWorker,true);check(realm.URL.createObjectURL===foreignCreate,true);
check(realm.URL.revokeObjectURL===revoke,true);check(NativeWorker.prototype.terminate===terminate,true);
check(realm[Symbol.for('deepseek-win7.host.workers')],undefined);
HostURL.createObjectURL=create;
// A compliant document must keep the original constructor and URL functions.
const modern=vm.createContext({URL:HostURL,URLSearchParams,Worker:NativeWorker,Blob,AbortSignal,AbortController,EventTarget,Event});
vm.runInContext('globalThis.Iterator=function Iterator(){};Promise.withResolvers=function withResolvers(){};Promise.try=function(){};Math.sumPrecise=function(){};Uint8Array.fromBase64=function(){};Uint8Array.prototype.toHex=function(){};',modern);
vm.runInContext('Uint8Array.prototype.toBase64=function(){};Map.prototype.getOrInsertComputed=function(){};Set.prototype.intersection=function(){};',modern);
vm.runInContext('Map.prototype.getOrInsert=function(){};ArrayBuffer.prototype.transferToFixedLength=function(){};',modern);
vm.runInContext(script,modern);
check(modern.Worker===NativeWorker,true);check(HostURL.createObjectURL===create,true);check(HostURL.revokeObjectURL===revoke,true);
console.log(JSON.stringify({passed:true,observations:checks,scope:'isolated ownership/teardown and unchanged compliant APIs; not actual Worker execution'}));

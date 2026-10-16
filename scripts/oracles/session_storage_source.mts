/** Actual rc.3 storage helpers and handle, driven through an observable adapter. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function storageCase(source:string,test:any,decode:(v:any)=>any) {
 const encode=(v:any):any=>v===undefined?{$scalar:'undefined'}:typeof v==='number'&&!Number.isFinite(v)?{$scalar:String(v)}:Object.is(v,-0)?{$scalar:'-0'}:Array.isArray(v)?v.map(encode):v&&typeof v==='object'?Object.fromEntries(Object.entries(v).map(([k,x])=>[k,encode(x)])):v
 return encode(await execute(source,test,decode))
}
async function execute(source:string,test:any,decode:(v:any)=>any) {
 const contract=await import(pathToFileURL(join(source,'packages/session/session-persistence/src/index.ts')).href)
 const error=(e:any):any=>({name:e.name,message:e.message,...(e.cause===undefined?{}:{cause:e.cause.message}),...(e.location===undefined?{}:{location:e.location}),...(e.errors?{errors:e.errors.map(error)}:{})})
 const result=async(run:()=>any)=>{try{return {outcome:'value',value:(await run())??null}}catch(e){return {outcome:'error',...error(e)}}}
 if(test.kind==='storage-contract') {
  const args=decode(test.args)
  const value=await result(()=>contract[test.method](...args))
  return {result:value,args}
 }
 const {JsonlSessionHandle,JsonlBackendTracker}=await import(pathToFileURL(join(source,'packages/session/session-persistence-jsonl/src/storage.ts')).href)
 const calls:any[]=[],counts:any={},results:any[]=[],background:any[]=[]
 const tracker=new JsonlBackendTracker('paired')
 const header={version:3,id:'paired-session',createdAt:1,isSeeded:false}
 const state=structuredClone(test.state??{cursor:0,materialized:false,inheritedEventCount:0})
 let path=test.path??null, stored=structuredClone(test.stored??{eventState:'shared-frozen',events:[]})
 const invoke=(name:string,...args:any[])=>{calls.push({method:name,args});counts[name]=(counts[name]??0)+1;if(test.fail?.[name]?.includes(counts[name]))throw new Error(`${name} failure ${counts[name]}`)}
 const lease={async release(){invoke('release')}}
 const storage={
  async persistBatch(h:any,events:any,materialized:any,cut:any){invoke('persistBatch',h,events,materialized,cut);stored.events.push(...events);path='/current';tracker.materialized(h.id)},
  async persistHeader(h:any,cut:any){invoke('persistHeader',h,cut);path='/current';tracker.materialized(h.id)},
  async truncateTornTail(h:any,offset:any){invoke('truncateTornTail',h,offset)},
  async resolveCurrentLog(id:any){invoke('resolveCurrentLog',id);return path??undefined},
  async readStoredLog(p:any,id:any){invoke('readStoredLog',p,id);return stored},
  hasPendingSession(id:any){return tracker.hasPending(id)},
  async acquireWriteLease(h:any){invoke('acquireWriteLease',h);return lease},
  releaseHandle(h:any,materialized:any){invoke('releaseHandle',h.id,materialized);tracker.release(h,materialized)},
 }
 if(test.created!==false)tracker.registerCreated(header,state.inheritedEventCount)
 const handle=tracker.adopt(new JsonlSessionHandle(storage,header.id,header,test.access??'write',state,test.lease?lease:undefined))
 for(const action of test.actions){
  results.push(await result(async()=>{
   if(action.method==='live'){handle.enqueueLive(decode(action.event),(e:any)=>background.push(error(e)));return}
   if(action.method==='stored'){stored=decode(action.value);path=action.path??path;return}
   if(action.method==='claim'){return tracker.claimWrite(action.id??header.id)}
   if(action.method==='create'){return tracker.registerCreated(header,0)}
   if(action.method==='flushAll')return tracker.flushAll()
   if(action.method==='dispose')return Promise.all([...tracker.openHandles].map((h:any)=>h.close())).then(()=>undefined)
   if(action.method==='append-close'){
    const pending=handle.append(decode(action.events));const closing=handle.close();const both=await Promise.all([result(()=>pending),result(()=>closing)]);return both
   }
   const args=decode(action.args??[])
   const pending=(handle as any)[action.method](...args)
   if(action.mutate)args[0][0].data.turn=99
   return pending
  }))
 }
 // Settle and release every case; include teardown failures in observations.
 const close=await result(()=>handle.close())
 return {results,calls,state:JSON.parse(JSON.stringify(state)),stored,background,close,pending:[...tracker.pendingEntries()],open:tracker.openHandles.size}
}

/** Actual unchanged rc.3 asynchronous image provider and compression limiter. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
import {tmpdir} from 'node:os'
import {mkdtemp,rm} from 'node:fs/promises'
import {createHash} from 'node:crypto'

export async function attachmentImagesCase(source:string,test:any){
 const load=(path:string)=>import(pathToFileURL(join(source,path)).href)
 const {LocalAttachmentStore}=await load('packages/attachment/attachment-local/src/index.ts')
 const failure=(error:any)=>({message:error.message,...(error.code===undefined?{}:{code:error.code}),...('cause'in error?{cause:error.cause}:{})})
 const outcome=async(p:Promise<any>)=>{try{return {value:await p}}catch(error){return {error:failure(error)}}}
 const deferred=()=>{let resolve:any;const promise=new Promise<void>(r=>resolve=r);return {promise,resolve}}
 if(test.operation==='limiter'){
  const {CompressionLimiter}=await load('packages/attachment/attachment-local/src/compression-limiter.ts')
  const limiter=new CompressionLimiter(2),order:number[]=[],gate=deferred(),entered=deferred();let active=0,peak=0
  const work=async(index:number)=>{active++;peak=Math.max(peak,active);order.push(index);if(order.length===2)entered.resolve();try{await gate.promise;if(index===1)throw 'binding failed';return index}finally{active--}}
  const tasks=Array.from({length:5},(_,index)=>outcome(limiter.run(()=>work(index))))
  await entered.promise;const before=[...order];gate.resolve()
  const values=await Promise.all(tasks);return {before,order,peak,values}
 }
 const {Context}=await load('vendor/cordis/src/index.ts')
 const directory=await mkdtemp(join(tmpdir(),'rc3-img-')),ctx=new Context()
 try{
  let store:any;try{store=new LocalAttachmentStore(ctx,{dshHome:directory,...test.config})}catch(error){return {error:failure(error)}}
  const ref=await store.saveImage({data:Buffer.from(test.data,'base64'),mediaType:'image/png'})
  const policy=test.policy??{maxPixels:1000,maxBytes:10000}
  if(test.operation==='read'){
   const read=async()=>{const result=await store.readImageRequest(ref,policy);return {result:Object.fromEntries(['attachment','mediaType','bytes','width','height','depth','space','hasAlpha'].map(key=>[key,result[key]])),digest:createHash('sha256').update(result.data).digest('hex')}}
   try{const first=await read(),second=await read();return {...first,repeatEqual:JSON.stringify(first)===JSON.stringify(second)}}catch(error){return {error:failure(error)}}
  }
  let started=0;const gates:any[]=[],signals:any[]=[],entries:any[]=[];let entered=deferred()
  const original=store.readImage.bind(store)
  store.readImage=async(ref:any,signal:any)=>{const index=started++,gate=deferred();gates.push(gate);signals.push(signal);entries.push(index);entered.resolve();await gate.promise;signal.throwIfAborted();return original(ref,signal)}
  const waitEntered=async()=>{if(!entries.length)await entered.promise;entries.shift();entered=deferred()}
  const first=new AbortController(),second=new AbortController()
  const request=async(signal:any)=>{const result=await store.readImageRequest(ref,policy,signal);return {bytes:result.bytes,width:result.width,height:result.height}}
  const one=outcome(request(first.signal));await waitEntered()
  const two=outcome(request(second.signal))
  first.abort(test.nonError?'stop one':new Error('stop one'));const observed=await one
  if(test.operation==='shared'){const masterAborted=signals[0].aborted;gates[0].resolve();return {started,first:observed,second:await two,masterAborted}}
  second.abort(new Error('stop two'));const other=await two
  const replacement=outcome(request(undefined));await waitEntered()
  gates[0].resolve();await new Promise(resolve=>setImmediate(resolve))
  const third=outcome(request(undefined));gates[1].resolve()
  return {first:observed,second:other,replacement:await replacement,third:await third,started,oldAborted:signals[0].aborted}
 }finally{await ctx.fiber.dispose();await rm(directory,{recursive:true,force:true})}
}

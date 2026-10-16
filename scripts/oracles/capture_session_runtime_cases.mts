/** Observe JSON-representable detached Session APIs while original assertions run. */
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs'
import {resolve,join} from 'node:path'
const [sourceArg,outputArg]=process.argv.slice(2)
const source=resolve(sourceArg).replaceAll('\\','/'),output=resolve(outputArg).replaceAll('\\','/')
if(!output.startsWith(source+'/.cache/'))throw new Error('Owned fresh Source cache required')
mkdirSync(output,{recursive:false})
const base=source+'/packages/core/session'
writeFileSync(join(output,'api.mts'),`
export * from ${JSON.stringify(base+'/src/index.ts')}
export {default} from ${JSON.stringify(base+'/src/index.ts')}
import * as original from ${JSON.stringify(base+'/src/index.ts')}
import {appendFileSync} from 'node:fs'
import {createHash} from 'node:crypto'
const target=${JSON.stringify(output+'/observations.jsonl')}
function encode(value:any,seen=new Set<any>()):any {
 if(value===undefined)return {$scalar:'undefined'}
 if(typeof value==='number'&&(!Number.isFinite(value)||Object.is(value,-0)))return {$scalar:Object.is(value,-0)?'-0':String(value)}
 if(value===null||['string','number','boolean'].includes(typeof value))return value
 if(typeof value!=='object'||seen.has(value))throw new Error('non-JSON capture input')
 if(!Array.isArray(value)&&Object.getPrototypeOf(value)!==Object.prototype&&Object.getPrototypeOf(value)!==null)throw new Error('exotic capture input')
 seen.add(value)
 const descriptors=Object.getOwnPropertyDescriptors(value)
 if(Object.values(descriptors).some((v:any)=>v.get||v.set))throw new Error('accessor capture input')
 const result=Array.isArray(value)?Array.from({length:value.length},(_,i)=>{
  if(!Object.hasOwn(value,i))throw new Error('sparse capture input');return encode(descriptors[i].value,seen)
 }):Object.fromEntries(Object.entries(descriptors).map(([k,d]:any)=>[k,encode(d.value,seen)]))
 seen.delete(value);return result
}
function safe(value:any){try{const result=encode(value);if(JSON.stringify(result).length>200000)throw new Error('oversized capture input');return result}catch{return undefined}}
function outcome(run:()=>any){try{return {outcome:'value',value:run()??null}}catch(e:any){return {outcome:'error',name:e.name,message:e.message,...(e.cause?{cause:e.cause.message}:{})}}}
function record(input:any,expected:any){const data=safe(input);if(data===undefined)return;const name=input.operation+'/'+createHash('sha256').update(JSON.stringify(data)).digest('hex').slice(0,20);appendFileSync(target,JSON.stringify({case:name,kind:'session-runtime',...data,expected})+'\\n','utf8')}
const sessions=new WeakMap<any,any>();let storeDepth=0
const snapshot=original.Session.prototype.snapshotEvents
function state(session:any){return {header:session.header,firstLiveSeq:session.firstLiveSeq,inheritedEventCount:session.inheritedEventCount,seq:session.seq,events:snapshot.call(session)}}
function timed(run:()=>any){const clock:number[]=[];const now=Date.now;Date.now=()=>{const value=now();clock.push(value);return value};try{return {result:outcome(run),clock}}finally{Date.now=now}}
for(const method of ['create','fromRestore'] as const){
 const call=original.Session[method]
 ;(original.Session as any)[method]=function(...args:any[]){
  if(storeDepth)return call.apply(this,args)
  const borrowed=safe(args)
  let session:any,thrown:any
  const {result,clock}=timed(()=>{try{session=call.apply(this,args);return null}catch(e){thrown=e;throw e}})
  if(borrowed!==undefined){
   const input={operation:'session',constructor:{method,args:borrowed,clock},actions:[]}
   if(session)sessions.set(session,input)
   record(input,{last:result,...(session?{state:state(session)}:{})})
  }
  if(thrown)throw thrown
  return session
 }
}
for(const method of ['append','snapshotEvents','eventAt','ownEvents','isOwnSeq','deriveMessages','deriveEventMessage','requestHeader','requestContext']){
 const call=(original.Session.prototype as any)[method]
 ;(original.Session.prototype as any)[method]=function(...args:any[]){
  const input=sessions.get(this)
  if(!input)return call.apply(this,args)
  const borrowed=safe(args)
  if(borrowed===undefined){sessions.delete(this);return call.apply(this,args)}
  let thrown:any,returned:any
  const {result,clock}=timed(()=>{try{return returned=call.apply(this,args)}catch(e){thrown=e;throw e}})
  input.actions.push({method,args:borrowed,clock})
  record(input,{last:result,state:state(this)})
  if(thrown)throw thrown
  return returned
 }
}
// Registry-owned publication is verified separately; these captures are detached APIs.
const prepare=original.default.prototype.prepare,enter=original.default.prototype.enter
original.default.prototype.prepare=function(...args:any[]){storeDepth++;try{return prepare.apply(this,args)}finally{storeDepth--}}
original.default.prototype.enter=function(session:any){sessions.delete(session);return enter.call(this,session)}
export const Session=original.Session
${['adoptSessionEvent','snapshotSessionEvent','foldSurface','canonicalHeader','headerEquals','foldRequestHeader','deriveEventMessage','isSurfaceEligibleType','isSurfaceEvent','isAppendSurfaceEvent','isReplacementSurfaceEvent'].map(name=>`
export const ${name}=(...args:any[])=>{const borrowed=safe(args);let thrown:any;let returned:any;const result=outcome(()=>{try{return returned=original.${name}(...args)}catch(e){thrown=e;throw e}});if(borrowed!==undefined)record({operation:'function',name:'${name}',args:borrowed},result);if(thrown)throw thrown;return returned}
`).join('\n')}
`,{encoding:'utf8',flag:'wx'})
for(const name of ['session','surface','derived-cache','canonical-envelopes','request-header','fork']){
 let text=readFileSync(join(base,'tests',name+'.spec.ts'),'utf8')
 text=text.replaceAll("'@deepseek-ai/dsh-session'","'./api.mts'")
 text=text.replaceAll("'../src/request-header.ts'","'./api.mts'")
 text=text.replace(/(['"])(\.\.?\/[^'"]+)\1/g,(_all,q,p)=>p==='./api.mts'?q+p+q:q+resolve(base,'tests',p).replaceAll('\\','/')+q)
 writeFileSync(join(output,name+'.spec.ts'),text,{encoding:'utf8',flag:'wx'})
}
writeFileSync(join(output,'vitest.config.mts'),`
import {defineConfig} from 'vitest/config'
import tsconfigPaths from 'vite-tsconfig-paths'
import {standardDecoratorPlugin,vitestExecArgv} from ${JSON.stringify(source+'/vitest.shared.ts')}
export default defineConfig({plugins:[standardDecoratorPlugin(),tsconfigPaths({projects:[${JSON.stringify(source+'/tsconfig.base.json')}]})],test:{include:[${JSON.stringify(output+'/*.spec.ts')}],fileParallelism:false,maxWorkers:1,execArgv:vitestExecArgv}})
`,{encoding:'utf8',flag:'wx'})

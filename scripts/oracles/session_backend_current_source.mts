/** Real rc.3 JSONL service, native files, kernel leases and migration workers. */
import {mkdtemp,mkdir,writeFile,appendFile,readFile,readdir,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join,dirname,relative} from 'node:path'
import {pathToFileURL} from 'node:url'
import {createHash} from 'node:crypto'

export async function backendCase(source:string,test:any,decode:(v:any)=>any) {
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {default:Backend}=await load('packages/session/session-persistence-jsonl/src/index.ts')
 const zstd=await load('packages/session/session-persistence-jsonl/src/zstd.ts')
 const root=await mkdtemp(join(tmpdir(),'dsh-backend-pair-'))
 const instances:any[]=[],handles=new Map<string,any>(),results:any[]=[],revisions=new Map<string,string>()
 const error=(e:any):any=>({name:e.name,message:e.message,...(e.cause===undefined?{}:{cause:e.cause.message??String(e.cause)}),...(e.location===undefined?{}:{location:e.location}),...(e.errors?{errors:e.errors.map(error)}:{})})
 const outcome=async(run:()=>any)=>{try{return {outcome:'value',value:(await run())??null}}catch(e){return {outcome:'error',...error(e)}}}
 const mount=async()=>{const ctx=new Context();const fiber=await ctx.plugin(Backend,{root,compression:test.compression});instances.push({ctx,fiber,p:ctx.sessionPersistence})}
 const encode=async(raw:string)=>test.compression==='none'?Buffer.from(raw):await zstd.compressZstdFrame(Buffer.from(raw))
 const write=async(file:any,append=false)=>{
  const path=join(root,file.path);await mkdir(dirname(path),{recursive:true})
  let data:Buffer
  if(file.frames)data=Buffer.concat(await Promise.all(file.frames.map(async(raw:string)=>encode(raw))))
  else if(test.compression==='zstd'&&!file.literal){const i=file.raw.indexOf('\n')+1;data=Buffer.concat([await encode(file.raw.slice(0,i)),...(file.raw.slice(i)?[await encode(file.raw.slice(i))]:[])])}
  else data=Buffer.from(file.raw)
  if(file.truncate!==undefined)data=data.subarray(0,data.length-file.truncate)
  await (append?appendFile:writeFile)(path,data)
 }
 const snapshot=(v:any):any=>{
  if(Array.isArray(v))return v.map(snapshot)
  if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>{
   if(k==='revision'){const raw=String(x);if(!revisions.has(raw))revisions.set(raw,`revision:${revisions.size+1}`);return [k,revisions.get(raw)]}
   return [k,snapshot(x)]
  }))
  return v
 }
 try{
  for(const file of test.files??[])await write(file)
  await mount()
  for(const action of test.actions){
   results.push(snapshot(await outcome(async()=>{
    const p=instances[action.backend??0].p
    if(action.method==='other'){await mount();return}
    if(action.method==='physical'){return write(action.file,action.append)}
    if(action.method==='dispose'){return instances[action.backend??0].fiber.dispose()}
    if(action.method==='create'||action.method==='open'){
     const h=await p[action.method](...decode(action.args));handles.set(action.handle??'h',h);return {id:h.id,header:h.header,access:h.access}
    }
    if(action.method==='stat'||action.method==='list'||action.method==='flush')return p[action.method](...decode(action.args??[]))
    return handles.get(action.handle??'h')[action.method](...decode(action.args??[]))
   })))
  }
  const teardown=[]
  for(const instance of instances)teardown.push(await outcome(()=>instance.fiber.dispose()))
  const files:any[]=[]
  async function visit(dir:string){for(const entry of await readdir(dir,{withFileTypes:true})){const path=join(dir,entry.name);if(entry.isDirectory())await visit(path);else{const bytes=await readFile(path);files.push({path:relative(root,path).replaceAll('\\','/'),bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')})}}}
  await visit(root);files.sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0)
  console.log(JSON.stringify({case:test.case,rawRevisions:[...revisions]}))
  const normalize=(v:any):any=>typeof v==='string'?v.split(root.replaceAll('\\','\\\\')).join('<root>').split(root).join('<root>'):Array.isArray(v)?v.map(normalize):v&&typeof v==='object'?Object.fromEntries(Object.entries(v).map(([k,x])=>[k,normalize(x)])):v
  return normalize({results,teardown,files})
 }finally{for(const instance of instances)await Promise.resolve(instance.fiber.dispose()).catch(()=>{});await rm(root,{recursive:true,force:true})}
}

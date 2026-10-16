/** Actual rc.3 query/SQLite service consuming actual JSONL handles. */
import {mkdtemp,mkdir,writeFile,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join,dirname} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function queryCurrentCase(source:string,test:any,decode:(v:any)=>any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {default:Sessions}=await load('packages/core/session/src/index.ts')
 const {default:Backend}=await load('packages/session/session-persistence-jsonl/src/index.ts')
 const {default:Query}=await load('packages/session-query/session-query-sqlite/src/index.ts')
 const root=await mkdtemp(join(tmpdir(),'dsh-query-pair-'));const ctx=new Context()
 const oldNow=Date.now;Date.now=()=>1000
 const leases=new Map<string,any>(),revisions=new Map<string,string>(),results:any[]=[]
 const normalize=(v:any,key=''):any=>{
  if(v instanceof Error)return {name:v.name,message:v.message,...((v as any).code?{code:(v as any).code}:{}),...((v as any).cause===undefined?{}:{cause:normalize((v as any).cause)})}
  if(key==='nextCursor'){const cursor=JSON.parse(Buffer.from(v,'base64url').toString());cursor.instance='<instance>';return cursor}
  if(key==='revision'){if(!revisions.has(v))revisions.set(v,`revision:${revisions.size+1}`);return revisions.get(v)}
  if(Array.isArray(v))return v.map(x=>normalize(x))
  if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,normalize(x,k)]))
  return v
 }
 const view=(lease:any)=>({source:lease.source,header:lease.header,inheritedEventCount:lease.inheritedEventCount,
  events:lease.events,cursor:lease.cursor,...(lease.revision===undefined?{}:{revision:lease.revision})})
 try{
  await ctx.plugin(Sessions);await ctx.plugin(Backend,{root,compression:'none'})
  for(const entry of test.stored??[]){const h=await ctx.sessionPersistence.create(entry.header,entry.options);try{await h.append(entry.events);await h.flush()}finally{await h.close()}}
  for(const file of test.files??[]){const path=join(root,file.path);await mkdir(dirname(path),{recursive:true});await writeFile(path,file.raw)}
  await ctx.plugin(Query,{path:':memory:',openAt:'first-search',...test.config})
  for(const action of test.actions){
   try{
    let value:any;const args=decode(action.args??[])
    if(action.method==='live'){
     const session=ctx.sessions.create(action.id,{meta:action.meta});
     for(const event of action.events??[])session.append(event.type,event.data,...(event.surfaceOp?[{surfaceOp:event.surfaceOp,...(event.sourceEventSeqs?{sourceEventSeqs:event.sourceEventSeqs}:{})}]:[]))
    }else if(action.method==='appendStored'){
     const h=await ctx.sessionPersistence.open(action.id,'write');try{await h.append(action.events)}finally{await h.close()}
    }else if(action.method==='observe'){
     const lease=await ctx.sessionQuery.observeSession(...args);leases.set(action.lease??'o',lease);value=view(lease)
    }else if(action.method==='retain'){const lease=leases.get(action.from??'o').retain();leases.set(action.lease,lease);value=view(lease)
    }else if(action.method==='release')leases.get(action.lease??'o')[Symbol.dispose]()
    else if(action.method==='view')value=view(leases.get(action.lease??'o'))
    else value=await ctx.sessionQuery[action.method](...args)
    results.push({outcome:'value',value:normalize(value??null)})
   }catch(e:any){results.push({outcome:'error',name:e.name,message:e.message,...(e.code?{code:e.code}:{}),...(e.cause===undefined?{}:{cause:e.cause.message??e.cause})})}
  }
  console.log(JSON.stringify({case:test.case,rawRevisions:[...revisions]}))
  return results
 }finally{for(const lease of leases.values())lease[Symbol.dispose]();await ctx.fiber.dispose();Date.now=oldNow;await rm(root,{recursive:true,force:true})}
}

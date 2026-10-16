/** Actual current list/search/cache contracts, synchronous controlled cache medium. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function sessionListCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts'),{default:Sessions}=await load('packages/core/session/src/index.ts'),{default:Projections}=await load('packages/session/session-projection/src/index.ts')
 const {ApiSessionList}=await load('packages/api/session-controller/src/list.ts'),{default:Cache}=await load('packages/session/session-projection-cache/src/index.ts'),{SessionQueryError}=await load('packages/session-query/session-query/src/index.ts')
 const ctx=new Context(),controller=new AbortController(),headers=new Map(),sessions=new Map(),calls:any[]=[],results:any[]=[],writes:any[]=[],records=structuredClone(test.records??{})
 const normalize=(value:any):any=>value===undefined?null:Array.isArray(value)?value.map(normalize):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([key,item])=>[key,normalize(item)])):value
 const oldNow=Date.now;Date.now=()=>1000
 try{
  await ctx.plugin(Sessions);await ctx.plugin(Projections)
  const registry=ctx.sessionProjections,titleSchema={parse:(value:any)=>{if(value!==null&&typeof value!=='string')throw new Error('invalid title');return value}}
  registry.register({key:'title',stateVersion:1,stateSchema:titleSchema,init:()=>null,apply:(state:any,event:any)=>event.type==='session/title'?event.data.title:state,wire:{viewSchema:titleSchema,view:(value:any)=>value}})
  const cache=new Cache(ctx,{writeEveryEvents:100,writeIntervalMs:60000});cache.table={get:(sid:string)=>records[sid],put:async(sid:string,record:any)=>{writes.push(structuredClone(record));records[sid]=record}}
  ctx.provide('agents',{get:(sid:string)=>(test.running??[]).includes(sid)?{status:'running'}:undefined})
  for(const record of test.headers??[{id:'one',cwd:'/project'}])headers.set(record.id,{version:3,createdAt:100,isSeeded:false,...record})
  if(!test.noProvider)ctx.provide('sessionQuery',{
   listSessions:async()=>{if(test.listError)throw new Error('list failed');return [...headers.values()].map(header=>({header}))},
   searchSessions:async(request:any,options:any)=>{calls.push(structuredClone(request));if(options.signal!==controller.signal)throw new Error('signal identity lost');const pages=test.pages??[{}],page=pages[Math.min(calls.length-1,pages.length-1)];if(page.abort)controller.abort(new Error('cancelled'));if(page.error)throw new SessionQueryError(page.message??'provider refused',page.error);return {items:(page.items??[]).map((item:any)=>({header:headers.get(item.id)??{id:item.id},bestMatch:{sessionId:item.matchId??item.id,surface:item.surface??'current',type:item.type??'user/message',snippet:item.snippet??'match'}})),...('nextCursor'in page?{nextCursor:page.nextCursor}:{})}}
  })
  const listing=new ApiSessionList(ctx)
  for(const sid of test.live??[])sessions.set(sid,ctx.sessions.create(sid,{meta:headers.get(sid)}))
  for(const action of test.actions){try{const sid=action.id??'one';let value:any
   if(action.op==='list')value=await listing.list(controller.signal)
   else if(action.op==='search')value=await listing.search(action.query,controller.signal)
   else if(action.op==='append'){for(const event of action.events)sessions.get(sid).append(event.type,event.data);value=true}
   else if(action.op==='snapshot')value=registry.snapshot(sessions.get(sid))
   else if(action.op==='cached')value=cache.cachedSnapshot(headers.get(sid),action.cut??0)
   else if(action.op==='predecessor')value=cache.cachedPredecessorTitle(headers.get(sid),action.cut??0)
   else if(action.op==='cold'){value=cache.coldSnapshot(headers.get(sid),action.cut??0,action.events??[]);await Promise.resolve()}
   else if(action.op==='write'){await cache.write(sessions.get(sid));value=true}
   else throw new Error('unknown list action')
   results.push({outcome:'value',value:normalize(value)})
  }catch(error:any){results.push({outcome:'error',error:{name:error.name,message:error.message,...('details'in error?{code:error.code,details:error.details}:{})}})}}
  return {results,calls,writes}
 }finally{await ctx.fiber.dispose();Date.now=oldNow}
}

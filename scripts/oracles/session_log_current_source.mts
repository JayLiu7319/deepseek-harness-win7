import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function sessionLogCase(source:string,test:any,decode:(value:any)=>any){
 const load=(path:string)=>import(pathToFileURL(join(source,path)).href)
 const api=await load('packages/session/session-log-deepseek/src/index.ts')
 if(test.operation==='fold'){
  const events=decode(test.events),session={id:'upload',header:{version:test.version??3},seq:events.length,eventAt:(i:number)=>events[i]??undefined}
  try{return {value:api.acceptedThrough(session)}}catch(error:any){return {error:error.message}}
 }
 const {Context}=await load('vendor/cordis/src/index.ts'),{default:Sessions}=await load('packages/core/session/src/index.ts'),{default:Extensions}=await load('packages/llm/deepseek-llm-api-extensions/src/index.ts')
 const original=Date.now;Date.now=()=>1000;const ctx=new Context(),results:any[]=[],prepared:any[]=[]
 try{
 await ctx.plugin(Sessions);await ctx.plugin(Extensions);const fiber=await ctx.plugin(api,{enabled:test.enabled??true})
 const session=ctx.sessions.create('upload',{meta:test.meta??{},...('seed'in test?{seed:test.seed}:{}),...('cut'in test?{inheritedEventCount:test.cut}:{})})
 for(const action of test.actions){
  if(action.op==='append')session.append(action.type,action.data,{...('surfaceOp'in action?{surfaceOp:action.surfaceOp}:{}),...('sourceEventSeqs'in action?{sourceEventSeqs:action.sourceEventSeqs}:{})})
  else if(action.op==='prepare'){const result=await ctx.deepseekLlmApiExtensions.prepare({body:{messages:[{role:'user',content:'hello'}]},signal:new AbortController().signal,...(action.direct?{}:{sessionId:action.sessionId??session.id})});prepared.push(result);results.push(structuredClone(result.fields))}
  else if(action.op==='accept')await prepared[action.index??prepared.length-1].accept()
  else if(action.op==='unload')await fiber.dispose()
 }
 return {results,events:session.snapshotEvents()}
 }finally{await ctx.fiber.dispose();Date.now=original}
}

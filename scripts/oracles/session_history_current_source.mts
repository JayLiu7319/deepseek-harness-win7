/** Real current history/control with controlled observations and real Session/Inbox. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function sessionHistoryCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {SessionAssistantStreamAccumulator}=await load('packages/api/session-controller/src/assistant-stream.ts')
 const normalize=(value:any):any=>value===undefined?null:Array.isArray(value)?value.map(normalize):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([key,item])=>[key,normalize(item)])):value
 if(test.mode==='accumulator'){const accumulator=new SessionAssistantStreamAccumulator(),results:any[]=[];let previous:any;for(const action of test.actions){if(action.op==='frame')accumulator.accept(action.frame,action.cursor??-1);else{const value=accumulator.snapshot();results.push({value:normalize(value),same:previous===value});previous=value}}return {results}}
 const {Context}=await load('vendor/cordis/src/index.ts'),{default:Sessions}=await load('packages/core/session/src/index.ts'),{default:Projections}=await load('packages/session/session-projection/src/index.ts'),{ReactLoopInbox}=await load('packages/core/agent-loop/src/inbox.ts'),{SessionQueryError}=await load('packages/session-query/session-query/src/index.ts')
 const {SessionHistoryController}=await load('packages/api/session-controller/src/history.ts'),{SessionControlController}=await load('packages/api/session-controller/src/control.ts')
 const ctx=new Context(),controller=new AbortController(),live=new Map(),results:any[]=[],calls:any[]=[],iterators=new Map(),counts={disposed:0,retained:0,promoted:0},oldNow=Date.now;Date.now=()=>1000
 try{
  await ctx.plugin(Sessions);await ctx.plugin(Projections);ctx.provide('agents',{get:(sid:string)=>live.get(sid)})
  const meta={createdAt:100,cwd:'/workspace',...test.meta};if(meta.cwd===null)delete meta.cwd
  const session=ctx.sessions.create('one',{meta}),agent:any={id:'one',session,ctx};live.set('one',agent);agent.inbox=new ReactLoopInbox(ctx.sessionProjections,session,{emit:()=>{}})
  const apply=(events:any[])=>{for(const event of events)session.append(event.type,event.data,{...('surfaceOp'in event?{surfaceOp:event.surfaceOp}:{}),...('sourceEventSeqs'in event?{sourceEventSeqs:event.sourceEventSeqs}:{})})};apply(test.events??[])
  const dispose=()=>{counts.disposed++},retain=()=>{counts.retained++;return {[Symbol.dispose]:dispose}}
  ctx.provide('sessionQuery',{observeSession:async(sid:string,options:any)=>{calls.push({sessionId:sid,projectionMode:options.projectionMode,signal:options.signal===controller.signal});if(test.missing)throw new SessionQueryError('missing','SESSION_QUERY_SESSION_NOT_FOUND');for(const frame of test.openingFrames??[])ctx.emit('agent/assistant-stream',{agent,frame});return {header:session.header,events:session.snapshotEvents(),cursor:session.seq-1,inheritedEventCount:test.cut??0,projections:{asOfSeq:session.seq-1,values:test.projections??{}},source:test.source??'attached',[Symbol.dispose]:dispose,retain}}})
  const history=new SessionHistoryController(ctx,(observed:any)=>{counts.promoted++;observed[Symbol.dispose]();if(test.promotionError)throw new Error('promotion rejected')}),control=new SessionControlController(ctx),jobs=new Map(),callbacks=new Set()
  ctx.provide('jobs',{list:(owner:any)=>jobs.get(owner?.id??'*')??[],onJobsChanged:(callback:any)=>{callbacks.add(callback);return ()=>callbacks.delete(callback)}})
  const address=test.address??{kind:'session',sessionId:'one'}
  const nextValue=async(iterator:any)=>{let timer:any;try{const result:any=await Promise.race([iterator.next(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('actor next timed out')),2000)})]);return result.done?{done:true}:{done:false,value:normalize(result.value)}}finally{clearTimeout(timer)}}
  for(const action of test.actions){try{let value:any
   if(action.op==='page')value=await history.page({address,...action.request},controller.signal)
   else if(action.op==='follow'){const iterator=history.follow({address,...action.request},controller.signal)[Symbol.asyncIterator]();iterators.set('history',iterator);value=await nextValue(iterator)}
   else if(action.op==='control'){const iterator=control.control(controller.signal)[Symbol.asyncIterator]();iterators.set('control',iterator);value=await nextValue(iterator)}
   else if(action.op==='next')value=await nextValue(iterators.get(action.stream??'history'))
   else if(action.op==='append'){apply(action.events);value=true}
   else if(action.op==='frame'){ctx.emit('agent/assistant-stream',{agent,frame:action.frame});value=true}
   else if(action.op==='disposed'){ctx.emit('agent/disposed',{agent});value=true}
   else if(action.op==='inbox'){agent.inbox.append(action.target??'next-turn',action.message);value=true}
   else if(action.op==='remove'){agent.inbox.remove(action.id);value=true}
   else if(action.op==='jobs'){jobs.set(agent.id,action.jobs);for(const callback of callbacks as Set<any>)callback(action.all?undefined:agent);value=true}
   else if(action.op==='close'){for(const close of history.closeFollowers)close();history.closeFollowers.clear();for(const stream of control.streams)stream.end();control.streams.clear();value=true}
   else if(action.op==='abort'){controller.abort();value=true}
   else throw new Error('unknown history operation')
   results.push({outcome:'value',value:normalize(value)})
  }catch(error:any){results.push({outcome:'error',error:{name:error.name,message:error.message,...('details'in error?{code:error.code,details:error.details}:{})}})}}
  for(const iterator of iterators.values())await iterator.return?.()
  return {results,calls,counts}
 }finally{await ctx.fiber.dispose();Date.now=oldNow}
}

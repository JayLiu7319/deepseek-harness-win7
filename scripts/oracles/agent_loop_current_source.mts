/** Actual rc.3 loop-owned projections, framing, and prompt registry. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function loopCurrentCase(source:string,test:any,decode:(v:any)=>any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {default:Sessions}=await load('packages/core/session/src/index.ts')
 const {default:Projections}=await load('packages/session/session-projection/src/index.ts')
 const {ReactLoopInbox}=await load('packages/core/agent-loop/src/inbox.ts')
 const {SystemPromptProjection,RuntimeContextProjection}=await load('packages/core/agent-loop/src/runtime-context.ts')
 const {AssistantStreamAttempt}=await load('packages/core/agent-loop/src/assistant-stream.ts')
 const prompt=await load('packages/core/system-prompt/src/index.ts')
 const ctx=new Context(),ids=new Map<string,string>(),results:any[]=[],notifications:any[]=[],observations:any[]=[]
 const normalize=(v:any):any=>{
  if(v===undefined)return null
  if(typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(v)){
   if(!ids.has(v))ids.set(v,`generated:${ids.size+1}`);return ids.get(v)
  }
  if(Array.isArray(v))return v.map(normalize)
  if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).filter(([,x])=>x!==undefined).map(([k,x])=>[k,normalize(x)]))
  return v
 }
 const oldNow=Date.now;Date.now=()=>1000
 try{
  if(test.operation==='goal-units'){
   const {run}=await import('./goal_units_current_source.mts')
   return await run(source,test)
  }
  if(test.operation==='meter-units'){
   const {run}=await import('./token_meter_units_current_source.mts')
   return await run(source,test)
  }
  if(['catalog','continuation-messages','subagent-inbox'].includes(test.operation)){
   const {subagentUnits}=await import('./subagent_units_current_source.mts')
   return await subagentUnits(source,test,normalize)
  }
  if(test.operation==='prompt-service'){
   await ctx.plugin(prompt.default,test.config??{})
   for(const section of test.sections??[])ctx.systemPrompt.section({...section,order:typeof section.order==='string'?ctx.systemPrompt.getSectionOrder(section.order):section.order})
   const assembly=await ctx.systemPrompt.assemble({})
   const orders=Object.fromEntries(['HARNESS_IDENTITY','DEPLOYMENT_PERSONA_PREFIX','TOOL_BASH','HARNESS_SOURCE','WEB_SURFACE','DEPLOYMENT_PERSONA_SUFFIX'].map(key=>[key,ctx.systemPrompt.getSectionOrder(key)]))
   return normalize({orders,assembly,rendered:prompt.renderPrompt(assembly)})
  }
  if(test.operation==='stream'){
   let revision=0
   const live=new AssistantStreamAttempt('loop-pair',1,()=>++revision,1,2,(frame:any)=>notifications.push(normalize(frame)))
   for(const action of test.actions){
    try{
     let value:any
     if(action.method==='settle')live.settle(action.eventType??'assistant/message',()=>{if(action.fail)throw new Error('append rejected');observations.push('durable');return 7})
     else if(action.method==='snapshot')value={stream:live.stream,blocks:live.blocks(),interruptedBlocks:live.interruptedBlocks(),finish:live.finish,usage:live.usage,replayState:live.replayState,ended:live.ended}
     else value=(live as any)[action.method](...decode(action.args??[]))
     results.push({outcome:'value',value:normalize(value)})
    }catch(error:any){results.push({outcome:'error',name:error.name,message:error.message,...(error.cause?{cause:error.cause.message}:{})})}
   }
   return {results,notifications,observations}
  }
  await ctx.plugin(Sessions);await ctx.plugin(Projections)
  const session=ctx.sessions.create('loop-pair',decode(test.options??{}))
  for(const event of test.initial??[])session.append(event.type,event.data,event.intent)
  if(test.operation==='compaction'){
   const {run}=await import('./compaction_current_source.mts')
   return await run(source,session,test,normalize)
  }
  let target:any
  const state=()=>({nextTurn:inbox.nextTurn,nextStep:inbox.nextStep,hasPending:inbox.hasPending})
  let inbox:any
  if(test.operation==='inbox'){
   inbox=new ReactLoopInbox(ctx.sessionProjections,session,{emit:(name:string,payload:any)=>notifications.push(normalize({name,payload,state:state()}))})
   target=inbox
   ctx.on('session/event',(subject:any,event:any)=>{if(subject===session)observations.push(normalize({event,state:state()}))})
  }else target=test.operation==='system-prompt'?new SystemPromptProjection(session):new RuntimeContextProjection(ctx,session)
  for(const action of test.actions){
   try{
    let value:any
    if(action.method==='appendEvent')value=session.append(action.event.type,action.event.data,action.event.intent)
    else if(action.method==='reconstruct')target=test.operation==='system-prompt'?new SystemPromptProjection(session):new RuntimeContextProjection(ctx,session)
    else if(action.method==='project'){
     value=target.project(...decode(action.args))
     const snapshot=normalize(value)
     if(action.commit){
      if(test.operation==='system-prompt')for(const decision of value)session.append('system/message',{turn:1,step:1,message:decision.message},decision.intent)
      else if(value!==undefined)session.append('user/message',value,{surfaceOp:'append'})
     }
     value=snapshot
    }else if(action.method==='state')value=state()
    else if(action.method==='wire')value=ctx.sessionProjections.snapshot(session)
    else value=target[action.method](...decode(action.args??[]))
    results.push({outcome:'value',value:normalize(value)})
   }catch(error:any){results.push({outcome:'error',name:error.name,message:error.message,...(error.cause?{cause:error.cause.message}:{})})}
  }
  return normalize({results,notifications,observations,events:session.snapshotEvents(),surface:session.surface.nodes,messages:session.deriveMessages()})
 }finally{await ctx.fiber.dispose();Date.now=oldNow}
}

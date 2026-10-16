/** Complete actual rc.3 Agent machine journeys, including handle-backed resume. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
import {mkdtemp,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'

export async function machineCurrentCase(source:string,test:any,decode:(v:any)=>any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {default:Sessions}=await load('packages/core/session/src/index.ts')
 const {default:Projections}=await load('packages/session/session-projection/src/index.ts')
 const {default:Prompt}=await load('packages/core/system-prompt/src/index.ts')
 const {default:Tools}=await load('packages/core/tools/src/index.ts')
 const {default:Agents}=await load('packages/core/agent/src/index.ts')
 const {default:Loop}=await load('packages/core/agent-loop/src/index.ts')
 const {default:Llm}=await load('packages/llm/llm/src/index.ts')
 const {default:Backend}=await load('packages/session/session-persistence-jsonl/src/index.ts')
 const {MockAdapter}=await load('packages/core/agent-loop/tests/mock-adapter.ts')
 const ctx=new Context(),root=await mkdtemp(join(tmpdir(),'dsh-machine-pair-')),ids=new Map<string,string>()
 let handle:any,agent:any,prompt=test.prompt??'prompt one',route=test.options??{provider:'script',model:'model'},preStep=test.preStep??{},retry=0,stopped=0,chunks=0
 const requests:any[]=[],notifications:any[]=[],results:any[]=[],errors:any[]=[]
 const normalize=(v:any,key=''):any=>{
  if(v===undefined)return null
  if(key==='signal')return '<signal>'
  if(key==='agent')return normalize(v.id)
  if(v instanceof Error)return {name:v.name,message:v.message,...((v as any).code===undefined?{}:{code:(v as any).code}),...((v as any).cause===undefined?{}:{cause:normalize((v as any).cause)})}
  if(typeof v==='string')return v.replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/ig,id=>{if(!ids.has(id))ids.set(id,`generated:${ids.size+1}`);return ids.get(id)!})
  if(Array.isArray(v))return v.map(x=>normalize(x))
  if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).filter(([,x])=>x!==undefined).map(([k,x])=>[k,normalize(x,k)]))
  return v
 }
 const view=()=>normalize({status:agent.status,events:agent.session.snapshotEvents(),messages:agent.session.deriveMessages(),inbox:ctx.sessionProjections.snapshot(agent.session).values.inbox})
 const oldNow=Date.now;Date.now=()=>1000
 try{
  for(const plugin of [Llm,Sessions,Projections,Prompt,Tools,Agents])await ctx.plugin(plugin,plugin===Prompt?test.promptConfig:undefined)
  if(test.persistence)await ctx.plugin(Backend,{root,compression:test.compression??'none'})
  if(test.subagents){
   const {default:Query}=await load('packages/session-query/session-query-sqlite/src/index.ts')
   const {default:Subagents}=await load('packages/subagent/subagent/src/index.ts')
   const spawn=await load('packages/subagent/subagent-spawn-in-process/src/index.ts')
   const fork=await load('packages/subagent/subagent-fork-in-process/src/index.ts')
   await ctx.plugin(Query,{path:':memory:',openAt:'never'});await ctx.plugin(Subagents);await ctx.plugin(spawn);await ctx.plugin(fork)
   for(const name of ['subagent/start','subagent/end'])ctx.on(name,(payload:any)=>notifications.push(normalize({name,payload})))
  }
  await ctx.plugin(Loop,{agents:[]})
  const adapter=new MockAdapter(test.script??[] ,test.reasoning,test.defaultMaxTokens)
  adapter.systemPromptUpdate=test.systemPromptUpdate
  ctx.llm.registerAdapter(['script'],adapter)
  if(!test.realPrompt)ctx.on('system-prompt/assemble',async (assembly:any,context:any,next:any)=>({...await next(),sections:[{name:'test',text:prompt}],contexts:test.context?[{name:'policy',text:test.context}]:[]}))
  ctx.on('agent/request',async (_payload:any,next:any)=>({...await next(),...route}))
  ctx.on('agent/pre-step',async (payload:any,next:any)=>{
   if(preStep.kind==='reject')return {kind:'reject'}
   const decision=await next()
   return {...decision,...(preStep.empty?{messages:[]}:{}),...(preStep.startsRequestSeries?{startsRequestSeries:true}:{})}
  })
  ctx.on('agent/request-error',async (_payload:any,next:any)=>retry++<(test.retries??0)?{kind:'retry'}:next())
  ctx.on('agent/turn-stopping',({agent:subject}:any)=>{if(stopped++<(test.stopping??[]).length)subject.inject(test.stopping[stopped-1])})
  ctx.on('llm/stream',(request:any,next:any)=>{requests.push(normalize(request));return next()})
  for(const name of ['agent/created','agent/disposed','agent/session-start','agent/status','agent/assistant-stream','agent/inbox/inserted','agent/inbox/discarded','agent/inbox/claimed']){
   if(test.throwNotification===name)ctx.on(name,()=>{throw new Error('observer failure')})
   ctx.on(name,(payload:any)=>{
    notifications.push(normalize({name,payload}))
    if(name==='agent/assistant-stream'&&payload.frame.type==='chunk'&&test.cancelAfter&&++chunks===test.cancelAfter)payload.agent.cancel({kind:'user'})
    if(name==='agent/session-start'&&test.startMessage)payload.agent.followup(test.startMessage)
   })
  }
  ctx.on('agent/error',({error}:any)=>errors.push(normalize(error)))
  handle=await ctx.agents.create({sessionId:'machine',agentOptions:test.options??{provider:'script',model:'model'},meta:{createdAt:1000}});agent=handle.agent
  for(const action of test.actions){
   try{
    let value:any
    if(action.method==='prompt')prompt=action.text
    else if(action.method==='persona'){
     const persona=await load('packages/preset/persona/src/index.ts')
     await agent.ctx.plugin(persona,action.config)
    }else if(action.method==='child'){
     const {startInProcessRun}=await load('packages/subagent/subagent-in-process-driver/src/index.ts')
     const events=agent.session.snapshotEvents(),lastEnd=events.findLast((event:any)=>event.type==='turn/end')
     const seed=action.fork&&lastEnd!==undefined?events.slice(0,lastEnd.seq+1):undefined
     const run=await startInProcessRun({...action.request,parent:agent,signal:new AbortController().signal},seed?.length?{seed}:{})
     const result=await run.result
     value=normalize({id:run.id,result,header:run.localAgent.session.header,events:run.localAgent.session.snapshotEvents(),owned:ctx.agents.isOwnedBy(run.id,agent)})
     await run.dispose()
    }
    else if(action.method==='background')value=await ctx.subagents.startContinuable({...action.spec,signal:new AbortController().signal,request:{...action.spec.request,parent:agent}})
    else if(action.method==='childIdle'){
     const deadline=performance.now()+3000
     while(ctx.agents.get(action.id)!==undefined){if(performance.now()>deadline)throw new Error('Child settlement deadline');await new Promise(resolve=>setTimeout(resolve,1))}
     await agent.whenIdle()
    }
    else if(action.method==='childObserve'){
     const observed=await ctx.sessionQuery.observeSession(action.id)
     try{value={header:observed.header,events:observed.events,inheritedEventCount:observed.inheritedEventCount}}finally{observed[Symbol.dispose]()}
    }
    else if(action.method==='childEntered'){
     const deadline=performance.now()+3000
     while(!notifications.some(n=>n.name==='agent/assistant-stream'&&n.payload.agent===action.id&&n.payload.frame.type==='chunk'&&n.payload.frame.chunk.type==='text-delta')){
      if(performance.now()>deadline)throw new Error('Child stream deadline');await new Promise(resolve=>setTimeout(resolve,1))
     }
    }
    else if(action.method==='childQuiescent'){
     const child=ctx.agents.get(action.id);await child.whenIdle()
     value={status:child.status,events:child.session.snapshotEvents(),inbox:ctx.sessionProjections.snapshot(child.session,['inbox']).values.inbox}
    }
    else if(action.method==='interruptChild')ctx.subagents.interrupt(action.id,action.ancestor?{kind:'ancestor',agent}:{kind:'user',parentSessionId:action.parentId??agent.id})
    else if(action.method==='queueChild'){
     const {deliverSubagentPrompt}=await load('packages/subagent/subagent/src/internal.ts')
     value=await ctx.subagents[deliverSubagentPrompt](agent,action.id,action.content,action.source??{kind:'user'},new AbortController().signal,'queue')
    }
    else if(action.method==='sendChild')value=await ctx.subagents.sendMessage(agent,action.id,action.content,{signal:new AbortController().signal})
    else if(action.method==='serviceChild'){
     const run=await ctx.subagents.start(action.provider,{...action.request,parent:agent,signal:new AbortController().signal})
     try{value={id:run.id,result:await run.result,header:run.localAgent.session.header,events:run.localAgent.session.snapshotEvents()}}finally{await run.dispose()}
    }
    else if(action.method==='route')route=action.config
    else if(action.method==='preStep')preStep=action.value
    else if(action.method==='idle')await agent.whenIdle()
    else if(action.method==='view')value=view()
    else if(action.method==='resume'){
     await handle.dispose();handle=undefined
     handle=await ctx.agents.resume({resumeSessionId:'machine',agentOptions:action.options??{provider:'script',model:'model'}});agent=handle.agent
    }else if(action.method==='dispose'){await handle.dispose();handle=undefined}
    else value=agent[action.method](...decode(action.args??[]))
    results.push({outcome:'value',value:normalize(value)})
   }catch(error:any){results.push({outcome:'error',error:normalize(error)})}
  }
  await agent.whenIdle()
  const final=view()
  if(handle){await handle.dispose();handle=undefined}
  return {results,final,requests,notifications,errors}
 }finally{if(handle)await handle.dispose();await ctx.fiber.dispose();Date.now=oldNow;await rm(root,{recursive:true,force:true})}
}

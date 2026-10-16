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
  if(key==='agent')return v.id
  if(v instanceof Error)return {name:v.name,message:v.message,...((v as any).code===undefined?{}:{code:(v as any).code}),...((v as any).cause===undefined?{}:{cause:normalize((v as any).cause)})}
  if(typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(v)){if(!ids.has(v))ids.set(v,`generated:${ids.size+1}`);return ids.get(v)}
  if(Array.isArray(v))return v.map(x=>normalize(x))
  if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).filter(([,x])=>x!==undefined).map(([k,x])=>[k,normalize(x,k)]))
  return v
 }
 const view=()=>normalize({status:agent.status,events:agent.session.snapshotEvents(),messages:agent.session.deriveMessages(),inbox:ctx.sessionProjections.snapshot(agent.session).values.inbox})
 const oldNow=Date.now;Date.now=()=>1000
 try{
  for(const plugin of [Llm,Sessions,Projections,Prompt,Tools,Agents])await ctx.plugin(plugin)
  if(test.persistence)await ctx.plugin(Backend,{root,compression:test.compression??'none'})
  await ctx.plugin(Loop,{agents:[]})
  const adapter=new MockAdapter(test.script??[] ,test.reasoning,test.defaultMaxTokens)
  adapter.systemPromptUpdate=test.systemPromptUpdate
  ctx.llm.registerAdapter(['script'],adapter)
  ctx.on('system-prompt/assemble',async (assembly:any,context:any,next:any)=>({...await next(),sections:[{name:'test',text:prompt}],contexts:test.context?[{name:'policy',text:test.context}]:[]}))
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
  handle=await ctx.agents.create({sessionId:'machine',options:test.options??{provider:'script',model:'model'},meta:{createdAt:1000}});agent=handle.agent
  for(const action of test.actions){
   try{
    let value:any
    if(action.method==='prompt')prompt=action.text
    else if(action.method==='route')route=action.config
    else if(action.method==='preStep')preStep=action.value
    else if(action.method==='idle')await agent.whenIdle()
    else if(action.method==='view')value=view()
    else if(action.method==='resume'){
     await handle.dispose();handle=undefined
     handle=await ctx.agents.resume({resumeSessionId:'machine',options:action.options??{provider:'script',model:'model'}});agent=handle.agent
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

/** API Agent policy with real unchanged Sessions/projections and controlled factories. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
import {mkdtemp,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'

export async function sessionAgentsCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {default:Sessions}=await load('packages/core/session/src/index.ts')
 const {createScope}=await load('packages/core/scope/src/index.ts')
 const {default:Projections}=await load('packages/session/session-projection/src/index.ts')
 const {default:Typert}=await load('packages/typert/registry/src/index.ts')
 const {SessionQueryError}=await load('packages/session-query/session-query/src/index.ts')
 const {ApiSessionAgentController,inspectApiSession}=await load('packages/api/session-controller/src/agent.ts')
 const {installModelSelectionProjection}=await load('packages/api/session-controller/src/model-selection-projection.ts')
 const ctx=new Context(),cwd=await mkdtemp(join(tmpdir(),'rc3-activation-')),live=new Map(),counts={create:0,resume:0,observe:0,disposed:0,setup:0},results:any[]=[],cold=test.cold,ids=new Map(),created:any[]=[],attached:any[]=[],saved:any[]=[]
 const normalize=(value:any):any=>value===undefined?null:typeof value==='string'?value.replaceAll(cwd,'<cwd>').replace(/session-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g,raw=>{if(!ids.has(raw))ids.set(raw,'opaque:'+(ids.size+1));return ids.get(raw)}):Array.isArray(value)?value.map(normalize):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([key,item])=>[key,normalize(item)])):value
 const header=(sid:string,meta:any={})=>({version:3,id:sid,createdAt:1,isSeeded:false,cwd,...meta})
 const make=(sid:string,meta:any={},request:any={})=>{const agent:any={id:sid,status:'idle',session:ctx.sessions.create(sid,{meta:header(sid,meta),...Object.fromEntries(['seed','inheritedEventCount'].filter(key=>key in request).map(key=>[key,request[key]]))})};agent.ctx=createScope(ctx,agent).ctx;live.set(sid,agent);return agent}
 const observation=(sid:string)=>{const meta=header(sid,cold);if(cold?.cwd===null)delete meta.cwd;return {header:meta,inheritedEventCount:0,events:test.events??[],projections:test.unprojected?undefined:{values:{agentPreset:meta.agentPreset}},[Symbol.dispose]:()=>{counts.disposed++}}}
 const factory=async(request:any,kind:'create'|'resume')=>{counts[kind]++;await Promise.resolve();if(test.factoryError)throw new Error('factory failed');const sid=request.sessionId??request.resumeSessionId,agent=make(sid,request.meta??cold??{},request);if(test.commands)created.push(Object.fromEntries(['sessionId','resumeSessionId','seed','inheritedEventCount','meta','agentOptions'].filter(key=>key in request).map(key=>[key,request[key]])));if(test.race){if(test.race==='child')Object.defineProperty(agent.session,'header',{value:header(sid,{...agent.session.header,origin:'subagent'})});throw new Error('raced publication')};if(test.returnedCwd)Object.defineProperty(agent.session,'header',{value:header(sid,{cwd:'/other'})});await request.setup(agent.ctx,agent);counts.setup++;return {agent}}
 try{
  await ctx.plugin(Sessions);await ctx.plugin(Projections);await ctx.plugin(Typert)
  ctx.sessionProjections.register({key:'agentPreset',stateVersion:1,stateSchema:{parse:(value:any)=>value},init:(header:any)=>header.agentPreset,apply:(state:any)=>state})
  installModelSelectionProjection(ctx)
  ctx.provide('agentDefaultModel',{currentSelection:()=>({provider:'fixture',model:'model',reasoningEffort:'default'})})
  ctx.provide('agents',{get:(sid:string)=>live.get(sid),isOwnedBy:()=>false,create:(r:any)=>factory(r,'create'),resume:(r:any)=>factory(r,'resume')})
  ctx.provide('sessionQuery',{observeSession:async(sid:string)=>{counts.observe++;if(cold===undefined)throw new SessionQueryError('missing','SESSION_QUERY_SESSION_NOT_FOUND');return observation(sid)}})
  const api=new ApiSessionAgentController(ctx)
  let controller:any
  if(test.commands){
   const {SessionCommandController}=await load('packages/api/session-controller/src/commands.ts'),{default:Titles}=await load('packages/session/session-title/src/index.ts'),{RemoteError}=await load('packages/typert/protocol/src/index.ts')
   if(!test.noTitle)await ctx.plugin(Titles,{fallbackMaxWords:5,fallbackMaxBytes:40,maxTitleBytes:80})
   ctx.agentDefaultModel.saveSelection=async(value:any)=>{saved.push(value);if(test.saveError)throw new Error('defaults write failed')}
   ctx.provide('llm',{resolveCallConfig:async(value:any)=>{if(test.modelError){if(test.modelError==='remote')throw new RemoteError('gateway/bad-request','bad route',{});throw new Error('model refused')}return {...value,model:value.model.trim()}}})
   const workspace={id:'workspace',path:cwd,sessionIds:test.workspaceSessions??[],attachSession:async(sid:string)=>{attached.push(sid);if(test.attachError)throw new Error('workspace write failed')}}
   ctx.provide('workspaceRegistry',{get:(wid:string)=>wid==='workspace'?workspace:undefined,list:()=>test.workspace?[workspace]:[]})
   ctx.sessionQuery.traceSession=async()=>{if(test.traceError)throw new Error('lineage unavailable');return {ancestors:(test.ancestors??[]).map((id:string)=>({header:{id}}))}}
   controller=new SessionCommandController(ctx,api,cwd)
  }
  if(test.live!==undefined)make('one',test.live)
  for(const action of test.actions){try{let value:any
   if(action.op==='command'){const request={...action.request};if(action.name!=='create')request.sessionId??='one';value=await controller[action.name](request)}
   else if(action.op==='ensure'){const values=await Promise.allSettled(Array.from({length:action.count??1},()=>api.ensureSession('one',cwd,action.persisted??false,action.preset)));value=values.map(item=>{if(item.status==='rejected')throw item.reason;return {id:item.value.id,cwd:item.value.session.header.cwd,preset:api.presetForSession(item.value.session)}})}
   else if(action.op==='resolve'||action.op==='observed'){const found=await (action.op==='resolve'?api.resolveAgent('one'):api.resolveObservedAgent(observation('one')));if(found.error)throw found.error;value={id:found.agent.id}}
   else if(action.op==='inspect'){const item=await inspectApiSession(ctx,'one');value={id:item.meta.id,events:item.events,inheritedEventCount:item.inheritedEventCount}}
   else if(action.op==='select'){api.selectForNextRequest(live.get('one'),action.value);value=true}
   else if(action.op==='header'){live.get('one').session.append('request/header',{reason:'initial',header:action.value});value=true}
   else if(action.op==='selection')value=api.selectionFor(live.get('one')).current
   else if(action.op==='consume')value=api.consumeSelection(live.get('one'),action.value.provider,action.value.model,action.value.reasoningEffort)
   else if(action.op==='projection')value=ctx.sessionProjections.stateOf(live.get('one').session,'modelSelection')
   else if(action.op==='serial'){const order:string[]=[];const settled=await Promise.allSettled([0,1,2].map(index=>api.serializeImageAdmission(live.get('one'),async()=>{order.push('enter'+index);await Promise.resolve();order.push('exit'+index);if(index===0)throw new Error('first failed');return index})));value={order,settled:settled.map(item=>item.status==='rejected'?item.reason.message:item.value)}}
   else throw new Error('unknown action '+action.op)
   results.push({outcome:'value',value:normalize(value)})
  }catch(error:any){results.push({outcome:'error',error:normalize({name:'details'in error?'RemoteError':'Error',message:error.message,...('details'in error?{code:error.code,details:error.details}:{})})})}}
  return {results,counts,...test.commands?{created:normalize(created),attached:normalize(attached),saved}:{} }
 }finally{await ctx.fiber.dispose();await rm(cwd,{recursive:true,force:true})}
}

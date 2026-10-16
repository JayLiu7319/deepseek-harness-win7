import {pathToFileURL} from 'node:url'
export async function sessionFacadeCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(`${source}/${p}`).href)
 const {Context}=await load('vendor/cordis/src/index.ts'),{default:Sessions}=await load('packages/core/session/src/index.ts'),{default:Projections}=await load('packages/session/session-projection/src/index.ts'),{default:Typert}=await load('packages/typert/registry/src/index.ts'),{SessionController}=await load('packages/api/session-controller/src/index.ts'),{SessionQueryError}=await load('packages/session-query/session-query/src/index.ts'),{ReactLoopInbox}=await load('packages/core/agent-loop/src/inbox.ts')
 const ctx=new Context(),controller=new AbortController(),calls:any[]=[],results:any[]=[],live=new Map(),resolver:any[]=[],disposed:string[]=[],standing={}
 const fail=(value:any)=>{throw value&&typeof value==='object'&&'throw'in value?value.throw:new Error(String(value))}
 const observe=async(sessionId:string,options?:any)=>{calls.push({op:'observe',sessionId,...options?.projectionMode?{projectionMode:options.projectionMode}:{}});if(test.queryError){if(test.queryError==='missing')throw new SessionQueryError('missing','SESSION_QUERY_SESSION_NOT_FOUND');fail(test.queryError)};return {header:{version:3,id:sessionId,createdAt:1,isSeeded:false,...test.header??{cwd:'/workspace'}},inheritedEventCount:0,events:[],cursor:-1,source:'live',projections:test.unprojected?undefined:{asOfSeq:-1,values:{agentPreset:test.preset}},[Symbol.dispose]:()=>disposed.push(sessionId)}}
 const native=async(path:string,signal:AbortSignal,action:string)=>{calls.push({op:action,path,signal:signal===controller.signal});if(test.nativeAbort)controller.abort(new Error('caller cancelled'));if('nativeError'in test)fail(test.nativeError)}
 const skills=async(options:any,scoped=false)=>{calls.push({op:'skills',cwd:options.cwd,scope:options.scope!==undefined&&options.scope===live.get('one')?'agent':options.scope===standing?'standing':null,scoped});if('skillError'in test)fail(test.skillError);return test.skills??[]}
 const clock=Date.now;Date.now=()=>1000
 try{
  await ctx.plugin(Sessions);await ctx.plugin(Projections);await ctx.plugin(Typert)
  ctx.provide('agentDefaultModel',{currentSelection:()=>({provider:'fixture',model:'model'})});ctx.provide('agents',{get:(id:string)=>live.get(id),isOwnedBy:()=>false});ctx.provide('sessionQuery',{observeSession:observe})
  ctx.provide('attachments',{imageLimits:{maxImageBytes:100,maxImagesPerMessage:2,maxMessageImageBytes:200,maxImagePixels:100,maxImageDimension:10,mediaTypes:['image/png']}})
  ctx.provide('fileUploads',{registerAgentResolver:(resolve:any)=>{resolver.push(resolve);return()=>resolver.splice(resolver.indexOf(resolve),1)}});ctx.provide('workspaceRegistry',{list:()=>[]})
  ctx.provide('llm',{listProviders:()=>(test.providers??[]).map(({id,name}:any)=>({id,name})),listModels:async(id:string)=>{const row=test.providers.find((r:any)=>r.id===id);if('error'in row)fail(row.error);return row.models??[]},resolveModelInfo:async(id:string,model:string)=>{const row=test.providers.find((r:any)=>r.id===id).models.find((r:any)=>r.id===model);if('resolveError'in row)fail(row.resolveError);return row}})
  if(!test.noSkills)ctx.provide('skills',{list:skills})
  if(test.presets)ctx.provide('agentPresets',{standingKeyFor:async(preset:any)=>{calls.push({op:'standing',preset:preset??null});if(test.standingError)fail('unknown preset');return standing},serviceFor:(agent:any,service:string)=>{calls.push({op:'serviceFor',agent:agent===live.get('one'),service});return test.scopedSkills?{list:(options:any)=>skills(options,true)}:undefined}})
  const api=new SessionController(ctx,test.config??{}, {openPath:(p:string,s:AbortSignal)=>native(p,s,'open'),revealPath:(p:string,s:AbortSignal)=>native(p,s,'reveal')})
  await Promise.resolve()
  if(test.live){const agent:any={id:'one',status:'idle',ctx,session:ctx.sessions.create('one',{meta:{createdAt:1,cwd:'/workspace'}})};agent.inbox=new ReactLoopInbox(ctx.sessionProjections,agent.session,{emit:()=>{}});live.set('one',agent)}
  if(test.aborted)controller.abort(new Error('caller cancelled'))
  for(const action of test.actions){try{let value:any
   if(action.op==='catalog')value=await api.modelCatalog()
   else if(action.op==='skills')value=await ctx.sessionSkillCatalog.list({sessionId:'one'},controller.signal)
   else if(action.op==='available')value=api.canOpenWorkspacePath()
   else if(action.op==='open')value=await api.openWorkspacePath(action.request,controller.signal)
   else if(action.op==='inspect')value=await api.inspect('one',controller.signal)
   else if(action.op==='resolver'){const found=await resolver[0]('one');value={id:found.id,exact:found===live.get('one')}}
   else if(action.op==='prompt')value=await api.prompt({sessionId:'one',input:{text:'should not admit'}},controller.signal)
   else throw new Error('unknown operation '+action.op)
   results.push({outcome:'value',value})
  }catch(error:any){results.push({outcome:'error',error:{message:error.message,...error.isDSHRemoteError?{code:error.code,details:error.details}:{}}})}}
  return JSON.parse(JSON.stringify({results,calls,disposed}))
 }finally{await ctx.fiber.dispose();Date.now=clock;if(resolver.length)throw new Error('resolver leaked')}
}

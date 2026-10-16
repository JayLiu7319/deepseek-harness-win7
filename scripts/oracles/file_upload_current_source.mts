/** Actual unchanged FileUploads and mixed command receipt authority. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
import {mkdtemp,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'

export async function fileUploadCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {default:Sessions}=await load('packages/core/session/src/index.ts')
 const {createScope}=await load('packages/core/scope/src/index.ts')
 const {LocalAttachmentStore}=await load('packages/attachment/attachment-local/src/index.ts')
 const {HostConnectionService}=await load('packages/client/connection/src/rpc-host.ts')
 const {default:Commands}=await load('packages/interaction/commands/src/index.ts')
 const {default:Uploads}=await load('packages/client/file-upload/src/index.ts')
 const root=await mkdtemp(join(tmpdir(),'rc3-upload-')),ctx=new Context(),live=new Map(),agents=new Map(),receipts:any[]=[],bindings=new Map(),results:any[]=[],invocations:any[]=[],ids=new Map()
 const normalize=(value:any):any=>{
  if(value===undefined)return null
  if(typeof value==='string')return value.replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|cmd-[0-9a-f]{8}-[1-9][0-9]*/g,raw=>{if(!ids.has(raw))ids.set(raw,'opaque:'+(ids.size+1));return ids.get(raw)})
  if(Array.isArray(value))return value.map(normalize)
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,normalize(item)]))
  return value
 }
 const oldNow=Date.now;Date.now=()=>1000
 try{
  await ctx.plugin(Sessions);ctx.provide('agents',{get:(sid:string)=>live.get(sid)})
  new LocalAttachmentStore(ctx,{dshHome:root})
  const connection=new HostConnectionService(ctx,[],{isAuthenticated:()=>true})
  await ctx.plugin(Commands);await ctx.plugin(Uploads)
  const uploads=ctx.fileUploads,commands=ctx.commands
  for(const sid of ['one','two','child']){
   const agent:any={id:sid,session:ctx.sessions.create(sid,{meta:{createdAt:1000,...(sid==='child'?{origin:'subagent'}:{})}})}
   agent.ctx=createScope(ctx,agent).ctx;live.set(sid,agent);agents.set(sid,agent)
  }
  const receipt=(index:any)=>typeof index==='number'?receipts[index].receiptId:index
  for(const action of test.actions){
   try{
    const agent=agents.get(action.agent??'one');let value:any
    if(action.op==='upload'){
     value=await uploads.upload(agent,{data:action.data??'YQ==',name:action.name??'a.txt'},new AbortController().signal);receipts.push(value)
    }else if(action.op==='resolve')value=uploads.resolve(agent,receipt(action.receipt??0))
    else if(action.op==='bind'){
     const binding=uploads.bindPrompt(agent,action.receipts.map(receipt),action.requestId);bindings.set(action.binding??'binding',binding);if(action.commit)binding.commit();value=true
    }else if(action.op==='rollback'){bindings.get(action.binding??'binding')[Symbol.dispose]();value=true}
    else if(action.op==='retire'){uploads.retirePrompt(agent,action.requestId);value=true}
    else if(action.op==='observe'){
     agent.session.append('user/message',{id:'observed-'+agent.session.seq,role:'user',content:[{type:'text',text:'accepted'}],source:{kind:action.kind??'user',rpcId:action.requestId}},{surfaceOp:'append'});value=true
    }else if(action.op==='drop'){live.delete(agent.id);ctx.emit('session/disposed',agent.session);value=true}
    else if(action.op==='resolver'){bindings.set('resolver',uploads.registerAgentResolver(async(sid:string)=>{const found=agents.get(action.target??'two');live.set(sid,found);return found}));value=true}
    else if(action.op==='http'){
     const shared=connection.createSharedFetchHandler('/api'),url=new URL('http://host'+(action.path??'/api/session/uploadFileBinary')),method=action.verb??'POST'
     const body=new ReadableStream({start(controller){for(const chunk of action.chunks??[])controller.enqueue(Buffer.from(chunk,'hex'));controller.close()}})
     const request=new Request(url,{method,headers:{'content-type':action.contentType??'application/octet-stream'},...(['GET','HEAD'].includes(method)?{}:{body,duplex:'half'})})
     const response=await shared.fetch(request);let result:any=await response.text()
     if(response.headers.get('content-type')?.startsWith('application/json')){result=JSON.parse(result);if(result.ok)receipts.push(result.value)}
     value={mode:shared.requestBodyMode({method,url}),status:response.status,body:result}
    }else if(action.op==='register'){
     commands.register({name:'files',description:'file command',handler:(invocation:any)=>{invocations.push({rawInput:invocation.rawInput,attachments:invocation.attachments});return {kind:'success',text:'command accepted'}},...('input'in action?{input:action.input}:{})});value=commands.list(agent)
    }else if(action.op==='execute'){
     value=await commands.execute(agent,'/files note',(action.attachments??[]).map((index:any)=>typeof index==='object'?index:{type:'file',receiptId:receipt(index)}),new AbortController().signal)
    }else throw new Error('Unknown upload action: '+action.op)
    results.push({outcome:'value',value:normalize(value)})
   }catch(error:any){results.push({outcome:'error',error:normalize({name:error.name,message:error.message,...('details'in error?{code:error.code,details:error.details}:{})})})}
  }
  return {results,invocations:normalize(invocations)}
 }finally{await ctx.fiber.dispose();Date.now=oldNow;await rm(root,{recursive:true,force:true})}
}

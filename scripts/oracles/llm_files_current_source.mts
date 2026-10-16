/** Actual unchanged file content helpers and LlmRuntime. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function llmFilesCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const api=await load('packages/llm/llm/src/index.ts')
 if(test.operation==='pure'){
  const messages=test.messages,projected=api.projectFilesToText(messages,()=>test.path)
  return {messages:projected,same:messages===projected,rows:messages.map((message:any,index:number)=>({message:message===projected[index],content:message.content===projected[index].content}))}
 }
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {deepFreeze}=await load('packages/util/values/src/index.ts')
 const ctx=new Context(),requests:any[]=[],mappings:any[]=[],hooks:any[]=[],handles:any[]=[],chunks:any[]=[]
 let current:any={},original:any
 try{
  if(test.attachments!==false)ctx.provide('attachments',{fileHostPath:()=>{if(current.hostError)throw new Error('invalid ref');return current.hostPath}})
  if(test.fs!==false)ctx.provide('fs',{processPathFromHostPath:(path:string)=>{mappings.push(path);if(current.mapError)throw new Error('mapping failed');return current.path}})
  await ctx.plugin(api.default)
  class Adapter extends api.LlmAdapter{
   async resolveModel(provider:string,model:string){return {provider,id:model,name:model,...(test.modalities===undefined?{}:{inputModalities:test.modalities})}}
   async *stream(request:any){requests.push({messages:request.messages,sameOptions:request===original,sameMessages:request.messages===original.messages,frozen:Object.isFrozen(request)});yield {type:'text',text:'accepted'}}
  }
  ctx.llm.registerAdapter(['test'],new Adapter())
  ctx.on('llm/stream',(options:any,next:any)=>{hooks.push(options.messages);return test.shortCircuit?(async function*(){yield {type:'text',text:'short'}})():next()})
  for(const step of test.steps??[{}]){
   current=step;original={provider:'test',model:'model',messages:structuredClone(test.messages)}
   if(test.frozen)original=deepFreeze(original)
   try{handles.push({outcome:'value',value:ctx.llm.fileRequestText(test.ref)})}catch(error:any){handles.push({outcome:'error',message:error.message})}
   const stream=test.prepared?(await ctx.llm.prepareCall({provider:'test',model:'model'})).stream(original):ctx.llm.stream(original)
   const observed=[];for await(const chunk of stream)observed.push(chunk);chunks.push(observed)
  }
  return {handles,requests,mappings,hooks,chunks}
 }finally{await ctx.fiber.dispose()}
}

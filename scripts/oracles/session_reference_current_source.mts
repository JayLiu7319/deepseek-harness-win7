import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function sessionReferenceCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts'),api=await load('packages/context/session-reference/src/index.ts'),{LlmError}=await load('packages/llm/llm/src/index.ts')
 const ctx=new Context(),saves:any[]=[],lookups:any[]=[],reads:string[]=[],controller=new AbortController(),snapshots=new Map<string,any>()
 for(const item of test.sources??[{id:'source',texts:['hello','answer']}]){
  const events=(item.texts??[]).map((value:any,index:number)=>{const text=typeof value==='string'?value:value.text.repeat(value.repeat??1),content=[{type:'text',text}];return index%2===0?{type:'user/message',data:{source:{kind:'user'},content}}:{type:'assistant/message',data:{message:{content}}}})
  snapshots.set(item.id,{session:{id:item.id,cwd:item.cwd,version:item.version??3},capturedThroughSeq:events.length?events.length-1:null,events})
 }
 ctx.provide('sessionQuery',{async readSurface(sid:string){reads.push(sid);if(test.readError)throw new Error('read failed');return structuredClone(snapshots.get(sid))}})
 if(!test.noLlm)ctx.provide('llm',{async resolveModelInfo(provider:string,model:string){lookups.push({provider,model});if(test.modelError){if(test.modelError==='ordinary')throw new Error('metadata failed');throw new LlmError('metadata failed',test.modelError)}return structuredClone(test.modelInfo??{})}})
 if(test.spill)ctx.provide('spillStore',{async saveText(request:any){saves.push(structuredClone(request));if(test.spillError)throw new Error('disk full');if(test.abortOnSave)controller.abort('cancelled');return {locator:'spill://snapshot',bytes:Buffer.byteLength(request.content),retrievalHint:'Read snapshot'}}})
 const agent={id:'target',session:{id:'target'},options:test.options??{provider:'provider',model:'model'}}
 const normalize=(value:any):any=>Array.isArray(value)?value.map(normalize):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).filter(([key])=>key!=='id').map(([key,item])=>[key,normalize(item)])):value
 try{
  await ctx.plugin(api.SessionReferenceResolver,test.config??{})
  if('assembled' in test){const assembly={variables:test.assembled};await ctx.waterfall('system-prompt/assemble',assembly,{agent},()=>assembly)}
  if(test.abortBefore)controller.abort('cancelled')
  let result:any
  try{result={result:normalize(await ctx.get('sessionReferenceResolver').prepare(agent,[{type:'text',text:'accepted'}],test.references??[...snapshots.keys()].map(sessionId=>({sessionId})),controller.signal))}}
  catch(error:any){result={error:{message:error.message,...error.code?{code:error.code}:{}}}}
  return {...result,saves,lookups,reads}
 }finally{await ctx.fiber.dispose()}
}

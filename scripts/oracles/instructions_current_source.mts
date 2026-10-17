import {join,resolve,relative} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function instructionsCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts'), api=await load('packages/context/agent-instructions/src/index.ts')
 const ctx=new Context(),root=resolve('C:/instruction-probe'),path=(name:string)=>join(root,name),trace:string[]=[],results:any[]=[],controller=new AbortController()
 const files=new Map<string,any>(Object.entries(test.files??{}).map(([name,value])=>[path(name),structuredClone(value)]))
 const fs={async resolve(name:string){controller.signal.throwIfAborted();const value=files.get(name);if(value?.resolveError)throw Object.assign(new Error(value.resolveError),{code:value.code??'FS_DENIED'});return name},async stat(target:string,signal:AbortSignal){signal.throwIfAborted();const value=files.get(target);if(!value)return undefined;if(value.statError)throw Object.assign(new Error(value.statError),{code:value.code??'FS_DENIED'});return {type:value.type??'file',version:value.version??value.content??'',...value.content!==undefined&&!value.omitSize?{size:Buffer.byteLength(value.content)}:{}}},async *streamText(target:string,signal:AbortSignal){trace.push(relative(root,target));const value=files.get(target)??{};if(value.readError)throw new Error(value.readError);for(const chunk of value.chunks??[value.content??'']){signal.throwIfAborted();yield chunk}}}
 const session={header:{cwd:path(test.cwd??'project')},surface:{nodes:[] as number[]},events:[] as any[],eventAt(seq:number){return this.events[seq]}}
 const inbox={nextStep:[] as any[],remove(id:string){this.nextStep=this.nextStep.filter(item=>item.id!==id)},prepend(_:any,message:any){this.nextStep.unshift(message)},replace(id:string,message:any){this.nextStep=this.nextStep.map(item=>item.id===id?message:item)}}
 const agent={session,inbox},boundary:any={openTurnStartSeq:null,lastStepBoundary:null}
 ctx.provide('fs',fs);ctx.provide('sessionProjections',{stateOf:()=>boundary})
 const normalize=(value:any):any=>Array.isArray(value)?value.map(normalize):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).filter(([key])=>key!=='id').map(([key,item])=>[key,normalize(item)])):value
 const fiber=ctx.plugin(api,{maxBytes:65536,dshHome:path('home'),...test.config});await fiber
 try{
  for(const action of test.actions??[{op:'step'}]){
   if(action.op==='files'){for(const [name,value] of Object.entries(action.values)){if(value===null)files.delete(path(name));else files.set(path(name),structuredClone(value))}}
   else if(action.op==='touch')ctx.emit('tools/result',{token:action.token??'exec',parent:action.parent,agent,signal:controller.signal,name:action.name??'read',arguments:{file_path:path(action.path??'project/sub/file.txt')}},{isError:action.error??false})
   else if(action.op==='step-open')Object.assign(boundary,{openTurnStartSeq:0,lastStepBoundary:{kind:'start',seq:1}})
   else if(action.op==='step-end'){boundary.lastStepBoundary={kind:'end',seq:2};ctx.emit('session/event',session,{type:'step/end'})}
   else if(action.op==='dispose')await fiber.dispose()
   else{
    const claimed=action.empty?[]:[{id:'input',role:'user',source:{kind:'user'},content:[{type:'text',text:'task'}]}]
    try{const decision=await ctx.waterfall('agent/pre-step',{agent,messages:claimed,step:action.step??1,signal:controller.signal},()=>({kind:action.reject?'reject':'proceed',messages:claimed}));if(action.commit!==false&&decision.kind!=='reject')for(const message of decision.messages){session.surface.nodes.push(session.events.length);session.events.push({type:'user/message',data:message})}results.push({decision:normalize(decision),pending:normalize(inbox.nextStep),reads:[...trace]})}
    catch(error){results.push({error:(error as Error).message,pending:normalize(inbox.nextStep),reads:[...trace]})}
   }
  }
  return results
 }finally{await ctx.fiber.dispose()}
}

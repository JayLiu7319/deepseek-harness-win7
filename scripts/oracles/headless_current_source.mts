import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function headlessCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts'),api=await load('packages/bundle/headless/src/index.ts')
 const ctx=new Context(),order:string[]=[],options:any[]=[],events:any[]=[]
 let out='',err='';const original={...api.internals},done=Promise.withResolvers<number>()
 const session={id:'owned',events,seq:0,eventAt:(i:number)=>i===test.missing?undefined:events[i]}
 const agent={session,whenIdle:async()=>{},followup(message:any){if(!message.id||message.role!=='user')throw new Error('unidentified prompt');order.push('prompt');for(const entry of test.frames)ctx.emit('agent/assistant-stream',{agent:entry.foreign?{}:agent,frame:entry.frame});for(const event of test.events){events.push({...structuredClone(event),seq:session.seq++})}}}
 ctx.provide('agentDefaultModel',{currentSelection:()=>({provider:'mock',model:'model',reasoningEffort:'high'})})
 ctx.provide('agents',{async create(request:any){options.push(request.agentOptions);return {agent}}})
 ctx.provide('sessions',{async flush(subject:any){if(subject!==session)throw new Error('wrong Session');order.push('flush')}})
 ctx.provide('appExit',(code:number)=>{order.push('exit');done.resolve(code)})
 api.internals.stdout={write:(s:string)=>{out+=s}};api.internals.stderr={write:(s:string)=>{err+=s}}
 try{await ctx.plugin(api,{task:test.task??'task'});const code=await done.promise;return {code,out,err,order,options}}
 finally{await ctx.fiber.dispose();Object.assign(api.internals,original)}
}

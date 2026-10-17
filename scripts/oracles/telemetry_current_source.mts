import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function telemetryCase(source:string,test:any){
 const {Context}=await import(pathToFileURL(join(source,'vendor/cordis/src/index.ts')).href)
 const {SessionTelemetryCoordinator}=await import(pathToFileURL(join(source,'packages/session/session-telemetry/src/coordinator.ts')).href)
 const ctx=new Context(),events=structuredClone(test.events),records:any[]=[],calls:string[]=[]
 const session={id:'telemetry',seq:events.length,events,header:{version:3,cwd:'/workspace',...(test.seeded?{parentSession:'parent'}:{}),isSeeded:test.seeded??false},inheritedEventCount:test.cut??0,firstLiveSeq:test.firstLive??0,snapshotEvents:(offset=0)=>events.slice(offset)}
 ctx.provide('sessions',{list:()=>[session]})
 const backend={emit(record:any){if('rejectSeq'in test&&record.attributes['event.seq']===test.rejectSeq)throw new Error('sink rejected');records.push(structuredClone(record));calls.push('emit')},flush(){calls.push('flush')},async shutdown(){calls.push('shutdown')}}
 ctx.on('session-telemetry/record',(record:any,next:any)=>{if('redactRejectSeq'in test&&record.attributes['event.seq']===test.redactRejectSeq)throw new Error('policy rejected');if(test.redact)record.body={redacted:true};return next()})
 const original=Date.now;Date.now=()=>1000
 try{
 const mount=async()=>{if(test.rootScope)return new SessionTelemetryCoordinator(ctx,backend,test.options);let coordinator:any;await ctx.plugin((child:any)=>{coordinator=new SessionTelemetryCoordinator(child,backend,test.options)});return coordinator}
 let coordinator=await mount()
 for(const action of test.actions){
  if(action==='capture')coordinator.captureSession(session,test.through)
  else if(action==='reload')coordinator=await mount()
  else if(action==='flush')ctx.emit('session/flush',session)
  else if(action==='disposed')ctx.emit('session/disposed',session)
  else if(action==='notify')for(const event of events)ctx.emit('session/event',session,event)
 }
 await ctx.fiber.dispose()
 return {records,calls,events}
 }finally{Date.now=original}
}

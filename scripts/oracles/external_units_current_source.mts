import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
import {PassThrough} from 'node:stream'
import {mkdtemp,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
const failure=(error:any):any=>({name:error.name,message:error.message,...(error.errors?{errors:error.errors.map(failure)}:{}),...(error.cause?{cause:failure(error.cause)}:{})})
export async function run(source:string,test:any){
 const {disposeAcpChild,startAcpRun}=await import(pathToFileURL(join(source,'packages/subagent/subagent-acp/src/run.ts')).href)
 if(test.mode==='peer'){
  const {spawnSubprocess}=await import(pathToFileURL(join(source,'packages/subprocess/subprocess-local/src/spawn.ts')).href)
  const directory=await mkdtemp(join(tmpdir(),'rc3-acp-peer-')),errors:any[]=[];let child:any
  try{
   const controller=new AbortController(),signal=controller.signal,listeners=new Set<any>()
   const add=signal.addEventListener.bind(signal),remove=signal.removeEventListener.bind(signal)
   signal.addEventListener=((...args:any[])=>{if(args[0]==='abort')listeners.add(args[1]);return add(...args)}) as any
   signal.removeEventListener=((...args:any[])=>{if(args[0]==='abort')listeners.delete(args[1]);return remove(...args)}) as any
   const handle=await startAcpRun({parent:{session:{header:{cwd:directory}}},signal,prompt:[{type:'image',source:{type:'url',url:'private-parent'}},{type:'text',text:'explicit child task'}]},
    {command:join(process.cwd(),'.venv/Scripts/python.exe'),args:[join(process.cwd(),'scripts/oracles/subagent_acp_peer.py')],cwd:directory,env:test.env??{},permission:test.permission??'reject',disposeEofGraceMs:150,disposeGraceMs:100,
     spawn:(spec:any)=>(child=spawnSubprocess(spec)),onError:(error:any)=>errors.push(failure(error))})
   const result=await handle.result;await handle.dispose();await handle.dispose()
   return {result,errors,reaped:await child.waitForExit(),exitCode:(await child.done).exitCode,detached:listeners.size===0}
  }finally{await rm(directory,{recursive:true,force:true})}
 }
 const trace:any[]=[],errors:any[]=[],waits=[...(test.waits??[true])],stdin=new PassThrough(),stdout=new PassThrough()
 const end=stdin.end.bind(stdin);stdin.end=(...args:any[])=>{trace.push('eof');stdout.end();return end(...args)}
 const done=test.reject?Promise.reject(new Error('direct result rejected')):Promise.resolve(undefined);void done.catch(()=>{})
 const child:any={pid:test.pid??1,stdin,stdout,done,terminate(){trace.push('terminate');if(test.terminateError)throw new Error('termination failed')},async waitForExit(signal:any){trace.push(signal?'bounded':'unbounded');const value=waits.shift();if(typeof value==='string')throw new Error(value);return value}}
 let result:any
 try{
  if(test.mode==='dispose'){await disposeAcpChild(child,5);result={outcome:'value'}}
  else{await startAcpRun({parent:{},signal:new AbortController().signal,prompt:[]},{command:'test',args:[],cwd:process.cwd(),env:{},permission:'reject',disposeEofGraceMs:5,disposeGraceMs:5,spawn:()=>child,onError:(error:any)=>errors.push(failure(error))});throw new Error('rejected child published')}
 }catch(error){result={outcome:'error',error:failure(error)}}
 return {result,trace,errors}
}

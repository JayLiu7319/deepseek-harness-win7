/** Original native-open route and real Connection registry over controlled seams. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
export async function presentOpenCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {default:Prompt}=await load('packages/core/system-prompt/src/index.ts')
 const Deliverables=await load('packages/client/ui-deliverables/src/index.ts')
 const {HostConnectionService}=await load('packages/client/connection/src/index.ts')
 const {FsError}=await load('packages/fs/fs/src/index.ts')
 const {RemoteError}=await load('packages/typert/protocol/src/index.ts')
 const ctx=new Context(),controller=new AbortController(),calls:any[]=[]
 const desktop={name:'serving host',available:!test.unavailable,fileManager:'explorer'}
 const fail=(stage:string)=>{if(test.failureStage!==stage)return;if(test.remoteCode)throw new RemoteError(test.remoteCode,'/private/host/path',{});throw new FsError('/private/host/path',test.code??'UNEXPECTED')}
 try{
  await ctx.plugin(Prompt)
  ctx.provide('sessionQuery',{readEvent:async(request:any)=>{calls.push({op:'read',request});fail('read');return{session:test.header??{cwd:'/child'},target:{type:test.eventType??'deliverables/presented',data:'data'in test?test.data:{turn:1,callId:'call',files:[{path:'报告.docx'}]}}}}})
  ctx.provide('workspaceFiles',{stat:async(scope:any,path:string)=>{calls.push({op:'stat',scope,path});fail('stat');if(test.abortDuring)controller.abort(new Error('cancelled'));return{absolutePath:'/host/current.docx'}}})
  ctx.provide('sandboxPolicy',{workspaceRoot:'/fallback'})
  ctx.provide('fs',{resolve:async(path:string)=>{calls.push({op:'resolve',path});fail('resolve');return{}},processPathFromHostPath:(path:string)=>{calls.push({op:'mapping',path});return test.unmapped?undefined:'/process/current.docx'},processPath:()=>test.wrongMapping?'/host/wrong':'/host/current.docx'})
  ctx.provide('sessionController',{workspaceDesktop:()=>desktop,openWorkspacePath:async(request:any)=>{calls.push({op:'open',request});fail('open')}})
  const connection=new HostConnectionService(ctx,[],{} as any),fiber=await ctx.plugin(Deliverables)
  if(test.aborted)controller.abort(new Error('cancelled'))
  const route=test.path??'/api/present.open',query=test.query??'?sessionId=child&seq=7&index=0';let response:any
  try{
   const result=await connection.createSharedFetchHandler('/api').fetch(new Request('http://localhost'+route+query,{method:test.method??'POST',signal:controller.signal}))
   response={status:result.status,headers:Object.fromEntries(result.headers),body:result.status===204?null:route==='/api/present.host'&&result.status===200?await result.json():await result.text()}
  }catch(error:any){response={error:error.message}}
  await fiber.dispose()
  const after=await connection.createSharedFetchHandler('/api').fetch(new Request('http://localhost/api/present.host'))
  return{response,calls,withdrawn:after.status===404}
 }finally{await ctx.fiber.dispose()}
}

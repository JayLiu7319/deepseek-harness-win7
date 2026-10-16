/** Actual unchanged rc.3 present and Tools pipeline with opaque FS. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
export async function presentCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {default:Sessions}=await load('packages/core/session/src/index.ts')
 const {default:Projections}=await load('packages/session/session-projection/src/index.ts')
 const {default:Prompt}=await load('packages/core/system-prompt/src/index.ts')
 const {default:Tools,defineTool}=await load('packages/core/tools/src/index.ts')
 const {createScope}=await load('packages/core/scope/src/index.ts')
 const {turnBoundaryProjectionDefinition}=await load('packages/core/agent-loop/src/index.ts')
 const {FsError}=await load('packages/fs/fs/src/index.ts')
 const Present=await load('packages/fs/tool-present/src/index.ts')
 const ctx=new Context(),calls:any[]=[],results:any[]=[],controller=new AbortController()
 try{
  for(const plugin of [Sessions,Projections,Prompt,Tools])await ctx.plugin(plugin)
  if(!test.noBoundary)ctx.sessionProjections.register(turnBoundaryProjectionDefinition)
  ctx.provide('fs',{
   lstat:async(path:string,options:any,signal:any)=>{calls.push({op:'lstat',path,cwd:options.cwd,signal:signal===controller.signal});if(test.fsError)throw new FsError('filesystem refused',test.fsError);return test.lstatMissing?undefined:{type:test.entryKind??'file'}},
   resolve:async(path:string,options:any)=>{calls.push({op:'resolve',path,cwd:options.cwd,signal:options.signal===controller.signal});return{displayPath:'opaque:'+path}},
   stat:async(target:any,signal:any)=>{calls.push({op:'stat',path:target.displayPath,signal:signal===controller.signal});if(test.abortDuring)controller.abort(new Error('caller cancelled'));return test.missing?undefined:{type:test.statKind??'file'}}
  })
  const fiber=await ctx.plugin(Present,{maxFiles:8,...test.config}),owner:any={id:'one',options:{},session:ctx.sessions.create('one',{meta:test.noWorkspace?{}:{cwd:'/project'}})}
  await ctx.plugin(Object.assign((inner:any)=>{owner.ctx=createScope(inner,owner).ctx},{inject:['tools']}))
  await Promise.resolve()
  if(!test.closed)owner.session.append('turn/start',{turn:3})
  if(test.nested)await owner.ctx.plugin(Present,{maxFiles:8,...test.config})
  if(test.override)owner.ctx.tools.register(defineTool({name:'present',description:'Scoped replacement.',parameters:{files:{type:'array',required:true,items:{type:'string'}}},output:{schema:{type:'object',additionalProperties:false,properties:{turn:{type:'integer',required:true},files:{type:'array',required:true,items:{type:'string'}}}},render:()=>[]},execute:()=>({turn:3,files:[]})}))
  if(test.block)ctx.on('tools/post-execute',async(_exec:any,_result:any,next:any)=>{await next();return{kind:'block',feedback:[{type:'text',text:'blocked'}]}})
  if(test.aborted)controller.abort(new Error('caller cancelled'))
  for(const [index,files] of (test.calls??[[{path:'report.docx'}]]).entries()){
   const result=await ctx.tools.execute({callId:'call-'+index,name:'present',arguments:{files},agent:test.detached?undefined:owner,signal:controller.signal})
   results.push({isError:result.isError,content:result.content,...result.isError?{}:{value:result.value}})
  }
  const deliveries=owner.session.snapshotEvents().filter((event:any)=>event.type==='deliverables/presented').map((event:any)=>event.data)
  await fiber.dispose()
  return JSON.parse(JSON.stringify({results,calls,deliveries,registered:ctx.tools.get('present',owner)!==undefined}))
 }finally{await ctx.fiber.dispose()}
}

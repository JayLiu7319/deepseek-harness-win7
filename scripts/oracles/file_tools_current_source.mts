/** Original file tool prompt visibility and controlled mutation/search providers. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
export async function fileToolsCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {default:Prompt}=await load('packages/core/system-prompt/src/index.ts')
 const {default:Tools}=await load('packages/core/tools/src/index.ts')
 const {createScope}=await load('packages/core/scope/src/index.ts')
 const {FsError}=await load('packages/fs/fs/src/index.ts')
 const Fs=await load('packages/fs/tool-fs/src/index.ts'),Search=await load('packages/fs/tool-fs-search/src/index.ts')
 const ctx=new Context(),saved:any[]=[]
 try{
  await ctx.plugin(Prompt);await ctx.plugin(Tools)
  const mutation=async()=>{throw new FsError(test.reason??'edit-specific provider reason',test.code??'FS_NOT_OBSERVED')}
  ctx.provide('fs',{resolve:async(path:string)=>({displayPath:'/project/'+path,targetKey:'opaque'}),writeText:mutation,editText:mutation,stat:async()=>({type:'file',size:4,version:'v1'}),readBytes:async()=>Buffer.from('PNG!')})
  if(test.operation==='read_image'){
   ctx.provide('attachments',{imageLimits:{mediaTypes:['image/png'],maxImageBytes:100,maxMessageImageBytes:100},saveImage:async()=>({attachmentId:'sha256:'+'a'.repeat(64),mediaType:'image/png',bytes:4,width:1,height:1})})
   ctx.provide('llm',{resolveModelInfo:async()=>({inputModalities:['image']})})
  }
  ctx.provide('subprocess',{spawn:()=>{
   if(test.failure==='launch')throw new Error('private launch error')
   const stdout=(test.operation??'glob')==='glob'?'a.txt\nb.txt\n':[1,2].map(i=>JSON.stringify({type:'match',data:{path:{text:'a.txt'},lines:{text:'line\n'},line_number:i}})).join('\n')
   return{done:test.failure==='provider'?Promise.reject(new Error('private provider error')):Promise.resolve({exitCode:0,signal:null}),collected:{stdout:{readFrom:()=>({text:stdout,lossy:false})},stderr:{readFrom:()=>({text:'',lossy:false})}}}
  }})
  ctx.provide('spillStore',{saveText:async(value:any)=>{saved.push(value);return{locator:'/spill/result',retrievalHint:'read spill'}}})
  await ctx.plugin(Fs,{readLimit:2000,readMaxLineLength:2000,readMaxBytes:51200,readStreamMinSize:10485760})
  await ctx.plugin(Search,{sampleOverCapGlobResults:false,globMaxResults:1,grepMaxMatches:1,grepMaxLineBytes:2000,searchMetaMaxBytes:51200,rawOutputMaxBytes:16777216,graceMs:1000,timeoutMs:30000,stderrMaxBytes:65536})
  const owner:any={id:'one',options:{provider:'fixture',model:'model'},session:{header:{cwd:'/project',id:'one'},requestHeader:()=>undefined}}
  await Promise.resolve();await Promise.resolve()
  await ctx.plugin(Object.assign((inner:any)=>{owner.ctx=createScope(inner,owner).ctx},{inject:['tools']}))
  if('allow'in test)owner.ctx.tools.restrict({allow:test.allow})
  if(test.replaceImage)ctx.on('tools/post-execute',async(_exec:any,_result:any,next:any)=>{await next();return{kind:'accept',content:[{type:'text',text:'replacement'}]}})
  if(test.operation==='prompt'){
   const prompt=await ctx.systemPrompt.assemble({scope:owner})
   return{sections:prompt.sections.filter((row:any)=>row.name.startsWith('tool:'))}
  }
  const op=test.operation??'glob',args=op==='write'?{file_path:'output',content:'new'}:op==='edit'?{file_path:'output',old_string:'old',new_string:'new'}:op==='read_image'?{file_path:'image.png'}:{pattern:'x'}
  const result=await ctx.tools.execute({callId:'call',name:op,arguments:args,agent:owner,signal:new AbortController().signal})
  return JSON.parse(JSON.stringify({isError:result.isError,content:result.content,...result.isError?{}:{value:result.value},saved,...op==='read_image'&&result.meta!==undefined?{meta:result.meta}:{}}))
 }finally{await ctx.fiber.dispose()}
}

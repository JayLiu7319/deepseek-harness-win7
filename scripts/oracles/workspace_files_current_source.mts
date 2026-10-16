import {posix,win32} from 'node:path'
import {pathToFileURL} from 'node:url'
export async function workspaceFilesCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(`${source}/${p}`).href)
 const {Context}=await load('vendor/cordis/src/index.ts'),{default:Sessions}=await load('packages/core/session/src/index.ts'),{default:Typert}=await load('packages/typert/registry/src/index.ts'),{default:WorkspaceFiles}=await load('packages/api/workspace-files/src/index.ts'),{FsError}=await load('packages/fs/fs/src/index.ts')
 const ctx=new Context(),controller=new AbortController(),calls:any[]=[],results:any[]=[],streams=new Map(),root=test.root??'/project',paths=root.startsWith('/')?posix:win32
 let closed=0
 const absolute=(path:string,cwd?:string)=>paths.resolve(cwd??root,path),target=(key:string)=>({key,displayPath:key}),info=(type='file')=>({type,version:'v1',...test.unknownSize?{}:{size:test.size??Buffer.from(test.data??'Ynl0ZXM=','base64').length}})
 const next=async(name:string)=>{let timer:any;try{const result:any=await Promise.race([streams.get(name).next(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('actor next timed out')),2000)})]);return result.done?{done:true}:{done:false,value:result.value}}finally{clearTimeout(timer)}}
 try{
  await ctx.plugin(Sessions);await ctx.plugin(Typert)
  ctx.provide('fs',{
   resolve:async(path:string,options:any={})=>{calls.push({op:'resolve',path,...'cwd'in options?{cwd:options.cwd}:{},signal:options.signal===controller.signal});if(path===root)for(const row of test.openingObservations??[])ctx.emit('fs/observed',target(absolute(row.path)),row.observation);if(test.resolveError)throw new FsError('resolve refused',test.resolveError);options.signal?.throwIfAborted();return target(absolute(path,options.cwd))},
   lstat:async(path:string,options:any,signal:any)=>{calls.push({op:'lstat',path,cwd:options.cwd,signal:signal===controller.signal});return test.missing?undefined:info(test.entryKind??'file')},
   stat:async(item:any,signal:any)=>{calls.push({op:'stat',target:item.key,signal:signal===controller.signal});return test.vanished?undefined:info(test.statKind??'file')},
   streamText:async(item:any,signal:any)=>{calls.push({op:'stream',target:item.key,signal:signal===controller.signal});return(async function*(){try{for(const text of test.chunks??['one\ntwo\nthree']){calls.push({op:'chunk',text});yield text};if(test.textError)throw new FsError('backend rejected text',test.textError)}finally{closed++}})()},
   readByteRange:async(item:any,range:any,signal:any)=>{calls.push({op:'bytes',target:item.key,range,signal:signal===controller.signal});return Buffer.from(test.data??'Ynl0ZXM=','base64').subarray(range.offset,range.offset+range.length)},
   listDir:async(item:any,signal:any)=>{calls.push({op:'list',target:item.key,signal:signal===controller.signal});return(test.entries??[]).map((row:any)=>({...row,target:target('/opaque/'+row.name)}))},
   contains:(parent:any,child:any)=>{const relative=paths.relative(parent.key,child.key);return relative===''||(relative!=='..'&&!relative.startsWith('..'+paths.sep)&&!paths.isAbsolute(relative))},processPath:(item:any)=>item.key,fileUrl:(item:any)=>'file:///'+item.key.replaceAll('\\','/').replace(/^\/+/, '').split('/').map(encodeURIComponent).join('/').replaceAll('%3A',':')
  })
  ctx.provide('sandboxPolicy',{workspaceRoot:'/fallback'});ctx.provide('sessionPersistence',{stat:async(sessionId:string)=>{calls.push({op:'persisted-stat',sessionId});return test.noHeader?undefined:{header:test.header??{cwd:root}}}})
  if(test.liveHeader!==undefined)ctx.sessions.create('one',{meta:test.liveHeader})
  const fiber=await ctx.plugin(WorkspaceFiles,{maxBytes:2097152,maxFileBytes:33554432,maxLines:5000,maxEntries:2000,...test.config}),api=ctx.workspaceFiles,scope={sessionId:'one',workspaceRoot:root}
  for(const action of test.actions){try{let value:any
   if(action.op==='lookup')value=await ctx.typert.lookups.get('workspaceFileScope')!.resolve('one')??null
   else if(action.op==='change'){streams.set(action.name??'feed',api.changes(scope,controller.signal)[Symbol.asyncIterator]());value=await next(action.name??'feed')}
   else if(action.op==='next')value=await next(action.name??'feed')
   else if(action.op==='observed'){ctx.emit('fs/observed',target(absolute(action.path)),action.observation);value=true}
   else if(action.op==='abort'){controller.abort(new Error('caller cancelled'));value=true}
   else if(action.op==='close'){await fiber.dispose();value={lookup:ctx.typert.lookups.get('workspaceFileScope')!==undefined}}
   else{const args:any[]=[scope,action.path??'file.txt'];if(action.op==='read'||action.op==='readBytes')args.push(action.range??{});if(action.op==='readRelated')args.push(action.relative);value=await (api as any)[action.op](...args,controller.signal)}
   results.push({outcome:'value',value})
  }catch(error:any){results.push({outcome:'error',error:{message:error.message,...'code'in error?{code:error.code}:{},...'details'in error?{details:error.details}:{}}})}}
  return JSON.parse(JSON.stringify({results,calls,closed}))
 }finally{controller.abort();for(const iterator of streams.values())await iterator.return?.();await ctx.fiber.dispose()}
}

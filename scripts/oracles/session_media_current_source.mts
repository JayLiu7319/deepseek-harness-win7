/** Unchanged rc.3 media contribution over the real exact Fetch registry. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function sessionMediaCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {FsError}=await load('packages/fs/fs/src/index.ts')
 const {SessionMediaReferences}=await load('packages/api/session-controller/src/media-references.ts')
 const {HostConnectionService}=await load('packages/client/connection/src/rpc-host.ts')
 const ctx=new Context(),controller=new AbortController(),calls:any[]=[]
 let requestSignal:any
 const target={targetKey:'opaque',displayPath:test.displayPath??'C:/remote/photo.png'}
 ctx.provide('fs',{
  async resolve(path:string,options:any){calls.push({method:'resolve',path,signal:options.signal===requestSignal});if(test.error){if(test.error==='unexpected')throw new Error('unexpected provider failure');throw new FsError('provider failure',test.error)}return target},
  async stat(received:any,signal:any){calls.push({method:'stat',sameTarget:received===target,signal:signal===requestSignal});return 'info'in test?test.info??undefined:{type:'file',size:4}},
  async readBytes(received:any,signal:any,maxBytes:number){calls.push({method:'read',sameTarget:received===target,signal:signal===requestSignal,maxBytes});return new Uint8Array([0,1,2,255])}
 })
 ctx.provide('attachments',{imageLimits:{maxImageBytes:test.limit??4}})
 const connection=new HostConnectionService(ctx,[],{isAuthenticated:()=>true})
 try{
  const fiber=ctx.plugin(SessionMediaReferences);await fiber
  const url=new URL('http://dsh.internal/api/file');if('path'in test)url.searchParams.set('path',test.path)
  let response:any
  try{const request=new Request(url,{method:test.method??'GET',headers:test.headers,signal:controller.signal});requestSignal=request.signal;const value=await connection.createSharedFetchHandler('/api').fetch(request);response={status:value.status,headers:Object.fromEntries(value.headers),hex:Buffer.from(await value.arrayBuffer()).toString('hex')}}catch(error:any){response={error:error.message}}
  await fiber.dispose()
  const gone=await connection.createSharedFetchHandler('/api').fetch(new Request(url))
  return {response,calls,withdrawn:gone.status===404}
 }finally{await ctx.fiber.dispose()}
}

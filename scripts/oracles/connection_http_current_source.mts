/** Original rc.3 registry and HTTP bridge through an actual TCP request. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
import {createServer,request as httpRequest} from 'node:http'

export async function connectionHttpCurrent(source:string,action:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {HostConnectionService}=await load('packages/client/connection/src/rpc-host.ts')
 const {bridge}=await load('packages/client/connection/src/http-bridge.ts')
 const ctx=new Context(),connection=new HostConnectionService(ctx,[],{isAuthenticated:()=>true})
 const observed:any={received:'',called:false}
 connection.fetch.register({path:'/api/upload',methods:['POST'],requestBody:action.mode,fetch:async(request:Request)=>{
  observed.called=true;observed.mode=action.mode
  if(action.early)return new Response('early',{status:202})
  if(action.mode==='streaming'){
   for await(const chunk of request.body as any){observed.received+=Buffer.from(chunk).toString('utf8');if(action.takeFirst)break}
  }else observed.received=await request.text()
  observed.aborted=request.signal.aborted
  return new Response(observed.received)
 }})
 const handler=connection.createSharedFetchHandler('/api')
 const server=createServer((req,res)=>{void bridge(req,res,handler,action.limit??8).catch(error=>res.destroy(error))})
 await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve))
 let client:any
 try{
  return await new Promise<any>((resolve,reject)=>{
   const headers:any=action.chunked?{'transfer-encoding':'chunked'}:{'content-length':String(action.declared??Buffer.byteLength((action.chunks??[]).join('')))}
   client=httpRequest({host:'127.0.0.1',port:(server.address() as any).port,path:'/api/upload',method:'POST',headers},response=>{
    const chunks:Buffer[]=[];response.on('data',chunk=>chunks.push(chunk));response.on('end',()=>resolve({status:response.statusCode,body:Buffer.concat(chunks).toString('utf8'),observed}))
   })
   client.setTimeout(3000,()=>client.destroy(new Error('HTTP observation timed out')))
   client.on('error',reject);client.flushHeaders()
   for(const chunk of action.chunks??[])client.write(chunk)
   if(!action.unfinished&&action.declared===undefined)client.end()
  })
 }finally{client?.destroy();server.closeAllConnections();await new Promise<void>(resolve=>server.close(()=>resolve()));await ctx.fiber.dispose()}
}

/** Real Source callbacks and icon IO, with only native command/launch seams. */
import {join,dirname} from 'node:path'
import {pathToFileURL} from 'node:url'
import {mkdtemp,mkdir,writeFile,readFile,rm,stat} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {Readable} from 'node:stream'
export async function openInAppHostCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts'),plugin=await load('packages/host/open-in-app/src/index.ts'),icons=await load('packages/host/open-in-app/src/icons.ts'),{internals}=await load('packages/host/open-in-app/src/internals.ts'),environment=await load('packages/util/launch-environment/src/index.ts')
 const root=await mkdtemp(join(tmpdir(),'rc3-open-app-host-')),ctx=new Context(),routes=new Map(),probes:any={},launches:any[]=[],commands:any[]=[],temps:string[]=[]
 const expand=(value:any):any=>typeof value==='string'?value.replaceAll('$ROOT',root):Array.isArray(value)?value.map(expand):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([k,v])=>[k,expand(v)])):value
 const normalize=(value:any):any=>typeof value==='string'?value.replaceAll(root,'$ROOT').replaceAll('\\','/'):Array.isArray(value)?value.map(normalize):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([k,v])=>[k,normalize(v)])):value
 const exists=async(path:string)=>{try{await stat(path);return true}catch{return false}}
 const removed=async()=>!(await Promise.all(temps.map(exists))).some(Boolean)
 const count=(key:string)=>{probes[key]=(probes[key]??0)+1}
 const resolveExecutable=async(name:string)=>{count(name);const path=expand(test.executables?.[name]??null);return test.resolveFromDisk&&(path===null||!await exists(path))?null:path}
 const launch=async(command:string,args:any,options:any)=>{launches.push({command,args,options});const outcomes=test.outcomes??['launched'],outcome=outcomes[Math.min(launches.length-1,outcomes.length-1)];if(test.removeOnLaunch)await rm(join(root,test.removeOnLaunch),{force:true});if(outcome!=='launched')throw Object.assign(new Error('failed'),{code:outcome==='missing'?'ENOENT':'EACCES'})}
 const run=async(command:string,args:string[])=>{
  if(command==='sips'||command==='powershell.exe'){
   const target=args.at(-1)!;temps.push(dirname(target))
   if(command==='powershell.exe')commands.push({command,flags:args.slice(0,5),executable:args.at(-2),script:await readFile(args.at(-3)!,'utf8')})
   else commands.push({command,flags:args.slice(0,-1)})
   if(test.commandFailure)throw new Error('extraction failure')
   if(!test.noOutput)await writeFile(target,Buffer.from([137,80,78,71,0,255]))
   return{stdout:'',stderr:''}
  }
  if(command==='plutil'){commands.push({command,args});return{stdout:test.plist??'{"CFBundleIconFile":"AppIcon"}',stderr:''}}
  count(command);throw new Error('command unavailable')
 }
 const facts={...expand({platform:test.platform??'darwin',home:'$ROOT/home',env:test.env??{},applicationRoots:['$ROOT/apps']}),resolveExecutable,run,launch}
 try{
  for(const name of test.directories??['workspace','apps/Cursor.app/Contents/Resources'])await mkdir(join(root,name),{recursive:true})
  for(const[name,content]of Object.entries(test.files??{'apps/Cursor.app/Contents/Resources/AppIcon.icns':'icns'})){const path=join(root,name);await mkdir(dirname(path),{recursive:true});await writeFile(path,expand(content),'utf8')}
  if(test.operation==='icon'){
   const value=await icons.extractAppIcon(expand(test.app??{id:'cursor',platforms:{}}),expand(test.resolved??{launch:{kind:'argv',command:'open',args:[]},icon:{kind:'app-bundle',path:'$ROOT/apps/Cursor.app'}}),1000,facts)
   return normalize({icon:value===null?null:{contentType:value.contentType,base64:value.bytes.toString('base64')},commands,tempsRemoved:await removed()})
  }
  internals.catalog=facts
  ctx.provide(environment.DSH_LAUNCH_ENVIRONMENT_KEY,environment.createLaunchEnvironmentSnapshot(expand(test.layers??[])))
  let rejection=test.rejection
  ctx.provide('connection',{requestRejection:()=>rejection});ctx.provide('subprocess',{resolveExecutable})
  ctx.provide('webServer',{register:(route:any)=>{routes.set(route.path,route.handler);return()=>routes.delete(route.path)}})
  const fiber=await ctx.plugin(plugin,{probeTimeoutMs:1000,iconTimeoutMs:1000,launchWatchMs:123}),responses:any[]=[]
  for(const action of test.requests??[{}]){
   if('rejection'in action)rejection=action.rejection??undefined
   const path=action.path??'/open-in-app/apps',headers:any={},chunks:Buffer[]=[]
   const response:any={statusCode:200,setHeader:(key:string,value:string)=>{headers[key.toLowerCase()]=value},end:(body?:any)=>{if(body!==undefined)chunks.push(Buffer.isBuffer(body)?body:Buffer.from(body))}}
   let text=action.text??JSON.stringify(expand(action.body??{app:'cursor',path:'$ROOT/workspace'}));if('size'in action)text='x'.repeat(action.size)
   const request:any=action.unreadable?new Readable({read(){this.destroy(new Error('body unavailable'))}}):Readable.from([Buffer.from(text)])
   request.url=path;request.method=action.method??(path==='/open-in-app/open'?'POST':'GET');request.headers=action.headers??{'content-type':'application/json'}
   const handler=routes.get(path)??(path.startsWith('/open-in-app/icon')?routes.get('/open-in-app/icon'):undefined)
   await handler(request,response)
   const data=Buffer.concat(chunks),body=headers['content-type']?.startsWith('application/json')?JSON.parse(data.toString('utf8')):{base64:data.toString('base64')}
   responses.push({status:response.statusCode,headers,body})
  }
  await fiber.dispose()
  return normalize({responses,probes:Object.fromEntries(Object.entries(probes).sort(([a],[b])=>a.localeCompare(b))),launches,commands,withdrawn:routes.size===0,tempsRemoved:await removed()})
 }finally{internals.catalog={};await ctx.fiber.dispose();await rm(root,{recursive:true,force:true})}
}

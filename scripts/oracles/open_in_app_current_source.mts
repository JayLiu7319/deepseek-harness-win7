/** Source resolver observations; all artifact probes touch real private files. */
import {join,resolve} from 'node:path'
import {pathToFileURL} from 'node:url'
import {mkdtemp,mkdir,writeFile,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
export async function openInAppCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const api=await load('packages/host/open-in-app/src/resolver.ts'),op=test.operation
 if(op==='catalog')return (await load('packages/host/open-in-app/src/catalog.ts')).OPEN_IN_APP_CATALOG
 if(op==='desktop')return api.parseDesktopEntry(test.text)
 if(op==='exec')return api.execCommand(test.text)
 if(op==='registry')return [...api.parseRegistryDump(test.text)].map(([key,values]:any)=>[key,[...values]])
 if(op==='versions')return [...test.values].sort((a,b)=>b.localeCompare(a,'en',{numeric:true}))
 const initial={home:'HOME',env:test.env??{},resolveExecutable:async()=>null}
 if(op==='expand')return api.expandCandidate(test.text,initial)
 if(op==='xdg')return api.xdgDataDirectories(initial)
 if(op==='launch'){
  const calls:any[]=[]
  const launch=async(command:string,args:any,options:any)=>{calls.push({command,args,options});const outcome=test.outcomes[calls.length-1];if(outcome!=='launched')throw Object.assign(new Error('launch rejected'),{code:outcome==='missing'?'ENOENT':'EACCES'})}
  const outcome=await api.launchResolved(test.resolved,test.path,123,{resolveExecutable:async()=>null,launch})
  return{outcome,calls}
 }
 const root=await mkdtemp(join(tmpdir(),'rc3-open-app-')),calls:any[]=[]
 const expand=(value:any):any=>typeof value==='string'?value.replaceAll('$ROOT',root):Array.isArray(value)?value.map(expand):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([key,v])=>[key,expand(v)])):value
 const normalize=(value:any):any=>typeof value==='string'?value.replaceAll(root,'$ROOT').replaceAll('\\','/'):Array.isArray(value)?value.map(normalize):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([key,v])=>[key,normalize(v)])):value
 try{
  for(const name of test.directories??[])await mkdir(join(root,name),{recursive:true})
  for(const[name,content]of Object.entries(test.files??{})){const path=join(root,name);await mkdir(resolve(path,'..'),{recursive:true});await writeFile(path,expand(content),'utf8')}
  const facts={...expand({platform:test.platform??'win32',ssh:test.ssh??false,env:test.env??{},home:'$ROOT/home',applicationRoots:['$ROOT/apps']}),resolveExecutable:async(name:string)=>{calls.push({resolve:name});return expand(test.executables?.[name]??null)},run:async(name:string,args:string[])=>{calls.push({command:name,args});const value=expand(test.commands?.[name==='reg.exe'?args[1]:name]);if(value===undefined)throw new Error('unavailable');return{stdout:value,stderr:''}}}
  let result:any
  if(op==='registry-view'){result=await api.readWindowsRegistryView(1000,api.resolveInternals(facts));result={...result,appPaths:[...result.appPaths]}}
  else if(op==='resolve')result=await api.resolveLaunch(expand(test.app),1000,facts)
  else if(op==='all')result=[...await api.resolveOpenInAppApps(1000,facts)]
  else throw new Error(op)
  return normalize(JSON.parse(JSON.stringify({result,calls})))
 }finally{await rm(root,{recursive:true,force:true})}
}

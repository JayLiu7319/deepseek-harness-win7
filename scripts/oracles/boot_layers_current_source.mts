import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
import {mkdtemp,mkdir,writeFile,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
export async function bootLayersCase(source:string,test:any){
 const api=await import(pathToFileURL(join(source,'packages/boot/app-boot/src/index.ts')).href),root=await mkdtemp(join(tmpdir(),'rc3-boot-layers-')),home=join(root,'home'),project=test.sameDirectory?home:join(root,'project')
 await mkdir(home);await mkdir(project,{recursive:true})
 const normalize=(value:any)=>JSON.parse(JSON.stringify(value).replaceAll(JSON.stringify(root).slice(1,-1),'$ROOT').replaceAll(pathToFileURL(root).href,'file:///$ROOT').replaceAll('\\\\','/'))
 try{
  if(test.operation==='env'){
   for(const[path,key]of [[home,'home'],[project,'project']])if(key in test)await writeFile(join(path,'.env'),test[key],'utf8')
   const original={...process.env};for(const key of Object.keys(process.env))delete process.env[key];Object.assign(process.env,{...test.inherited,DSH_HOME:home})
   try{
    let result:any
    try{const snapshot=api.loadLayeredEnv('dsh',project,()=>{});result={entries:Object.fromEntries(test.names.map((key:string)=>[key,snapshot.get(key)??null])),materialized:Object.fromEntries(test.names.map((key:string)=>[key,process.env[key]??null]))}}
    catch(error:any){result={error:error.message,materialized:Object.fromEntries(test.names.map((key:string)=>[key,process.env[key]??null]))}}
    return normalize(result)
   }finally{for(const key of Object.keys(process.env))delete process.env[key];Object.assign(process.env,original)}
  }
  const file=join(root,'patches','extra.yml');await mkdir(join(root,'patches'))
  const expand=(value:any):any=>typeof value==='string'?value.replaceAll('$ABS',join(root,'plugin #100% 中文.py')).replaceAll('$URL',pathToFileURL(join(root,'plugin #100% 中文.py')).href):Array.isArray(value)?value.map(expand):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([k,v])=>[k,expand(v)])):value
  await writeFile(file,JSON.stringify(expand(test.patches)),'utf8')
  return normalize((test.operation==='optional'?api.loadOptionalPatches:api.loadOverlayPatches)('dsh',file))
 }finally{await rm(root,{recursive:true,force:true})}
}

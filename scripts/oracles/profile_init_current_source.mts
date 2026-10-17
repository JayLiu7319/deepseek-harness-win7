/** Unchanged public CLI parser and actual exclusive profile directory claims. */
import {join,relative,dirname} from 'node:path'
import {pathToFileURL} from 'node:url'
import {mkdtemp,mkdir,writeFile,readFile,readdir,rm,stat} from 'node:fs/promises'
import {tmpdir} from 'node:os'
export async function profileInitCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 if(test.operation==='args'){
  const {parseDshArgs}=await load('apps/cli/src/args.ts'),originalExit=process.exit,out=process.stdout.write,err=process.stderr.write
  let code:any
  process.exit=((value:any)=>{code=value;throw new Error('exit')}) as any;process.stdout.write=(()=>true) as any;process.stderr.write=(()=>true) as any
  try{try{return JSON.parse(JSON.stringify({value:parseDshArgs(test.argv,'1.2.3')}))}catch(error){if(code!==undefined)return{exit:code};throw error}}finally{process.exit=originalExit;process.stdout.write=out;process.stderr.write=err}
 }
 const {initializeProfileFromDefault}=await load('apps/cli/src/profile-boot.ts'),home=await mkdtemp(join(tmpdir(),'rc3-profile-init-')),target=join(home,'profiles',test.name??'rescue')
 const exists=async(path:string)=>{try{await stat(path);return true}catch{return false}}
 const files=async(root:string):Promise<any>=>{const result:any={};for(const entry of await readdir(root,{withFileTypes:true})){const path=join(root,entry.name);if(entry.isDirectory())Object.assign(result,await files(path));else result[relative(home,path)]=await readFile(path)}return result}
 try{
  for(const[name,content]of Object.entries(test.files??{})){const path=join(home,name);await mkdir(dirname(path),{recursive:true});await writeFile(path,content as string,'utf8')}
  if(test.existingDirectory)await mkdir(target,{recursive:true})
  const before=await files(home);let outcome:any
  try{initializeProfileFromDefault(test.name??'rescue',test.template??'web',home);outcome={ok:true}}catch(error:any){outcome={error:error.message.replaceAll(home,'$HOME').replaceAll('\\','/')}}
  const after=await files(home),manifestPath=join(target,'package.json'),hasTarget=await exists(target)
  return{outcome,exists:hasTarget,beforePreserved:Object.entries(before).every(([key,value]:any)=>after[key]?.equals(value)),files:hasTarget?Object.keys(await files(target)).map(path=>relative(target,join(home,path)).replaceAll('\\','/')).sort():[],manifest:await exists(manifestPath)&&!test.invalidManifest?JSON.parse(await readFile(manifestPath,'utf8')):null}
 }finally{await rm(home,{recursive:true,force:true})}
}

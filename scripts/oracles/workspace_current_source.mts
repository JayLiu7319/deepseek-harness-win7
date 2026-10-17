/** Real original domain/registry over snapshot-only persistence and private dirs. */
import {join,basename} from 'node:path'
import {pathToFileURL} from 'node:url'
import {mkdtemp,mkdir,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
export async function workspaceCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const paths=await load('packages/workspace/workspace/src/paths.ts')
 if(test.operation==='path')return{qualified:paths.fullyQualifiedWorkspacePath(test.path,test.platform),title:paths.defaultWorkspaceTitle(test.path,test.platform)}
 const {Context}=await load('vendor/cordis/src/index.ts')
 const {default:Storage}=await load('packages/storage/storage/src/index.ts')
 const {DomainFacility}=await load('packages/storage/storage-domain/src/index.ts')
 const {MemoryMediaPool,MemoryStorageBackend}=await load('packages/storage/storage-domain/tests/helpers/memory-backend.ts')
 const {default:Workspace}=await load('packages/workspace/workspace/src/index.ts')
 const root=await mkdtemp(join(tmpdir(),'rc3-workspace-')),contexts:any[]=[],pool=new MemoryMediaPool(),results:any[]=[]
 await mkdir(join(root,'a'));await mkdir(join(root,'b'))
 let headers=[{version:3,id:'one',createdAt:1,isSeeded:false,cwd:join(root,'a')}]
 const boot=async()=>{const ctx=new Context();contexts.push(ctx);await ctx.plugin(Storage);ctx.storage.backend.register('memory',new MemoryStorageBackend(pool));const domain=new DomainFacility(ctx,{backend:'memory',routes:{}});ctx.storage.mount('domain',domain);ctx.provide('storageDomain',domain);ctx.provide('sessionPersistence',{list:async()=>headers.map(header=>({header,revision:'revision-'+header.id}))});await ctx.plugin(Workspace);return{ctx,registry:ctx.workspaceRegistry}}
 let {ctx,registry}=await boot()
 const snapshot=()=>({items:registry.list().map((item:any)=>({path:basename(item.path),title:item.title,sessionIds:item.sessionIds})),archived:registry.archivedSessionIds})
 try{
  for(const action of test.actions){const op=action.op
   if(op==='reopen'){await ctx.fiber.dispose();({ctx,registry}=await boot())}
   else if(op==='create')await registry.create(join(root,action.path))
   else if(op==='headers')headers=action.headers.map((row:any)=>({version:3,id:row.id,createdAt:row.time??1,isSeeded:false,cwd:join(root,row.path)}))
   else if(op==='archive')await registry.archiveSession(action.id)
   else if(op==='attach')await(await registry.resolveByPath(join(root,action.path))).attachSession(action.id)
   else if(op==='detach')await(await registry.resolveByPath(join(root,action.path))).detachSession(action.id)
   else if(op==='relative'){try{await registry.create(action.path)}catch(error:any){results.push({error:error.message});continue}}
   else if(op!=='view')throw new Error(op)
   results.push(snapshot())
  }
  return JSON.parse(JSON.stringify({results}))
 }finally{for(const ctx of contexts.reverse())await ctx.fiber.dispose();await rm(root,{recursive:true,force:true})}
}

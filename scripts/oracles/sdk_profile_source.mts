import {pathToFileURL} from 'node:url'
import {resolve} from 'node:path'
import {readFileSync,writeFileSync,renameSync} from 'node:fs'

const root=process.env.DSH_SDK_SOURCE_ROOT!
const load=(path:string)=>import(pathToFileURL(resolve(root,path)).href)
const {parseDshArgs}=await load('apps/cli/src/args.ts')
const {runProfile}=await load('apps/cli/src/profile-boot.ts')
const {loadLayeredEnv}=await load('packages/boot/app-boot/src/index.ts')
const {version}=JSON.parse(readFileSync(resolve(root,'apps/cli/package.json'),'utf8'))
const invocation=parseDshArgs(process.argv.slice(2),version)
if(invocation.mode!=='profile')throw new Error('SDK profile observer requires profile invocation')
const {ctx}=await runProfile({environment:loadLayeredEnv('dsh'),profile:invocation.profile,
  fromDefaultProfile:invocation.fromDefaultProfile,patchFiles:invocation.patches,args:invocation.args})
// SDK forwards durable facts. Observe the real transient chunk separately to
// establish cancellation admission without manufacturing protocol frames.
ctx.on('agent/assistant-stream',(info:any)=>{
  if(info.frame.type!=='chunk'||info.frame.chunk.type!=='text-delta'||info.frame.chunk.text!=='SDK_PENDING')return
  const path=process.env.DSH_SDK_LIVE_BARRIER!
  writeFileSync(path+'.tmp',JSON.stringify({sessionId:String(info.agent.session.id),frame:info.frame}),{flag:'wx'})
  renameSync(path+'.tmp',path)
})

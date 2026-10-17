import {it} from 'vitest'
import {Context} from '@deepseek-ai/cordis'
import SessionStore from '@deepseek-ai/dsh-session'
import Jsonl from '@deepseek-ai/dsh-session-persistence-jsonl'
import {mkdtemp,rm,writeFile} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {execFileSync} from 'node:child_process'

it('observes independent current handle reads and per-read cancellation',async()=>{
  const pin='a4c74a91e06b00fe0b0937bde982170c526cc842'
  if(process.version!=='v22.22.2'||execFileSync('git',['-C','reference','rev-parse','HEAD'],{encoding:'utf8'}).trim()!==pin
    ||execFileSync('git',['-C','reference','status','--porcelain'],{encoding:'utf8'}).trim())throw new Error('Pinned clean Source required')
  const rows:any[]=[]
  for(const name of ['jsonl-none/queued','jsonl-zstd/queued']){
    const root=await mkdtemp(join(tmpdir(),'dsh-read-order-')),context=new Context()
    const row:any={name},controller=new AbortController(),reason=new Error('controlled read retired')
    let enter:any,release:any
    const entered=new Promise(resolve=>{enter=resolve}),released=new Promise(resolve=>{release=resolve})
    try{
      await context.plugin(SessionStore)
      await context.plugin(Jsonl,{root,compression:name.startsWith('jsonl-zstd')?'zstd':'none'})
      const provider:any=context.sessionPersistence
      const handle=await provider.create({id:'s',version:3,createdAt:1,isSeeded:false} as any)
      await handle.append([{type:'session/end-seed',seq:0,time:1,data:{}}] as any)
      const original=provider.readStoredLog.bind(provider),calls:any[]=[]
      provider.readStoredLog=async(...args:any[])=>{
        const first=calls.length===0
        calls.push({signalForwarded:args[args.length-1]===controller.signal})
        if(!first)controller.abort(reason)
        const value=await original(...args)
        if(first){enter();await released}
        return value
      }
      const settle=(promise:Promise<any>)=>promise.then(value=>({value}),error=>({error:{name:error.name,message:error.message},reasonIdentity:error===reason}))
      const first=settle(handle.read())
      await entered
      const second=settle(handle.read(0,undefined,{signal:controller.signal}))
      let timer:any
      const early:any=await Promise.race([second,new Promise(resolve=>{timer=setTimeout(()=>resolve({pending:true}),1000)})])
      clearTimeout(timer)
      row.settledBeforeRelease=!early.pending
      row.callsBeforeRelease=calls.length
      release()
      row.first=await first
      Object.assign(row,await second)
      row.calls=calls
      row.aborted=controller.signal.aborted
      provider.readStoredLog=original
    }finally{release();await context.fiber.dispose();await rm(root,{recursive:true,force:true})}
    rows.push(row)
  }
  await writeFile(process.env.DSH_ORDER_SOURCE_OUTPUT!,JSON.stringify({sourceCommit:pin,node:process.version,rows},null,2)+'\n',{flag:'wx'})
})

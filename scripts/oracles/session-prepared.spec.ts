import { it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import SessionStore from '@deepseek-ai/dsh-session'
import Jsonl from '@deepseek-ai/dsh-session-persistence-jsonl'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// The retired preparation reservation is now explicit single-writer ownership.
it('observes current handle ownership, detached reads and cancelled acquisition', async () => {
 const rows=[]
 for(const mode of ['reuse','mutated-release','reserved-write','cancel-wait','revision']) {
  const root=await mkdtemp(join(tmpdir(),'dsh-prepared-'));const ctx=new Context()
  try {
   await ctx.plugin(SessionStore);await ctx.plugin(Jsonl,{root,compression:'none'})
   const p=ctx.sessionPersistence;const sid='s' as any
   const initial=await p.create({id:sid,version:3,createdAt:1,delegationDepth:0,isSeeded:false})
   await initial.append([{type:'turn/start',seq:0,time:1,data:{turn:1}},{type:'turn/end',seq:1,time:2,data:{turn:1,reason:{kind:'completed'}}}])
   await initial.close()
   const first=await p.open(sid,'write')
   const exact=(await first.read()).events
   if(mode==='revision'){
    const before=await p.stat(sid)
    await first.append([{type:'turn/start',seq:2,time:3,data:{turn:2}}])
    const after=await p.stat(sid)
    rows.push({mode,changed:before!.revision!==after!.revision,types:(await first.read()).events.map(e=>e.type)})
   }else if(mode==='reserved-write'){
    let rejected=false
    try {await p.open(sid,'write')}catch{rejected=true}
    const reader=await p.open(sid,'read')
    rows.push({mode,rejected,physical:(await reader.read()).events.length})
    await reader.close()
   }else if(mode==='cancel-wait'){
    const controller=new AbortController();const reason=new Error('cancel observer')
    controller.abort(reason)
    let cancelled=false
    try{await p.open(sid,'write',{signal:controller.signal})}catch(error){cancelled=error===reason}
    await first.close();const second=await p.open(sid,'write')
    rows.push({mode,cancelled,types:(await second.read()).events.map(e=>e.type)})
    await second.close()
   }else{
    if(mode==='mutated-release')(exact as any[]).push({type:'turn/start',seq:2,time:3,data:{turn:2}})
    await first.close();const second=await p.open(sid,'write')
    rows.push({mode,same:second===first,types:(await second.read()).events.map(e=>e.type)})
    await second.close()
   }
   await first.close()
  }finally{await ctx.fiber.dispose();await rm(root,{recursive:true,force:true})}
 }
 await writeFile(process.env.SESSION_PREPARED_OUTPUT!,JSON.stringify(rows,null,2))
})

import { it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import SessionStore from '@deepseek-ai/dsh-session'
import Jsonl from '@deepseek-ai/dsh-session-persistence-jsonl'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
const modes=['lazy','duplicate','cursor','legacy','unknown','cold-adopt','materialize','invalid-read']
it('observes the public storage boundary through real JSONL services',async()=>{
 const rows=[]
 for(const mode of modes){
  const root=await mkdtemp(join(tmpdir(),'dsh-storage-'));let ctx=new Context()
  const mount=async()=>{await ctx.plugin(SessionStore);await ctx.plugin(Jsonl,{root,compression:'none'});return ctx.sessionPersistence}
  const event=(seq=0,type='session/end-seed',data={})=>({seq,type,time:seq+1,data}) as any
  const meta={id:'s' as any,version:3 as const,createdAt:1,isSeeded:false}
  try{
   let p=await mount();let writer=await p.create(meta)
   const read=async()=>{const h=await p.open(meta.id,'read');try{return {...await h.read(),meta:h.header}}finally{await h.close()}}
   if(mode==='lazy'){
    meta.createdAt=20;const before=(await p.list()).length;await writer.append([event()])
    rows.push({mode,before,createdAt:(await read()).meta.createdAt})
   }else if(mode==='duplicate'){
    let rejected=false;try{await p.create({...meta,cwd:root})}catch{rejected=true}
    rows.push({mode,rejected,physical:(await p.list()).length})
   }else if(mode==='cursor'){
    let rejected=0;for(const events of [[event(1)],[event(),event(2)]]){try{await writer.append(events)}catch{rejected++}}
    await writer.append([event()]);try{await writer.append([event()])}catch{rejected++}
    rows.push({mode,rejected,seqs:(await read()).events.map(e=>e.seq)})
   }else if(mode==='legacy'){
    let rejected=0;for(const ev of [event(0,'mode/set'),event(0,'request/header-delta'),event(0,'request/header',{reason:'fallback'})]){try{await writer.append([ev])}catch{rejected++}}
    rows.push({mode,rejected,physical:(await p.list()).length})
   }else if(mode==='unknown'){
    let rejected=0;try{await writer.append([event(0,'future/plugin')])}catch{rejected++}
    rows.push({mode,rejected,physical:(await p.list()).length})
   }else if(mode==='cold-adopt'){
    await writer.append([event(0,'turn/start',{turn:1})]);await ctx.fiber.dispose();ctx=new Context();p=await mount()
    writer=await p.open(meta.id,'write');await writer.append([event(1)])
    rows.push({mode,types:(await read()).events.map(e=>e.type)})
   }else if(mode==='materialize'){
    await writer.flush();await writer.flush();rows.push({mode,events:(await read()).events.length,physical:(await p.list()).length})
   }else{
    let rejected=0;try{await writer.append([{...event(0,'turn/start',{turn:1}),time:'bad'} as any])}catch{rejected++}
    rows.push({mode,rejected,physical:(await read()).events.length})
   }
  }finally{await ctx.fiber.dispose();await rm(root,{recursive:true,force:true})}
 }
 await writeFile(process.env.SESSION_STORAGE_OUTPUT!,JSON.stringify(rows,null,2))
})

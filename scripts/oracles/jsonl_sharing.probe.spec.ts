import {writeFileSync} from 'node:fs'
import {execFileSync} from 'node:child_process'
import {expect,it} from 'vitest'
import {Context} from '@deepseek-ai/cordis'
import SessionStore from '@deepseek-ai/dsh-session'
import Jsonl from '@deepseek-ai/dsh-session-persistence-jsonl'

it('observes complete original JSONL readers beside an owned Windows shared holder',async()=>{
  const pin='a66e4702047846cdaa10c66c9d3df3951f5ea70d'
  expect(process.version).toBe('v22.22.2')
  expect(execFileSync('git',['-C','reference','rev-parse','HEAD'],{encoding:'utf8'}).trim()).toBe(pin)
  expect(execFileSync('git',['-C','reference','status','--porcelain'],{encoding:'utf8'}).trim()).toBe('')
  const ctx=new Context()
  try{
    await ctx.plugin(SessionStore)
    await ctx.plugin(Jsonl,{root:process.env.DSH_JSONL_SHARING_ROOT!,compression:process.env.DSH_JSONL_SHARING_COMPRESSION! as 'none'|'zstd'})
    const provider=ctx.sessionPersistence
    const listed=await provider.list()
    const inspected=await provider.inspect('sharing-session' as any)
    const raw=await provider.readRaw('sharing-session' as any)
    expect(listed.map(value=>value.id)).toEqual(['sharing-session'])
    expect(inspected.events.map(value=>value.type)).toEqual(['session/end-seed'])
    expect(raw!.content).toContain('sharing-session')
    writeFileSync(process.env.DSH_JSONL_SHARING_SOURCE_OUTPUT!,JSON.stringify({sourceCommit:pin,node:process.version,name:process.env.DSH_JSONL_SHARING_NAME,observed:{listed,inspected,raw}},null,2)+'\n',{encoding:'utf8',flag:'wx'})
  }finally{await ctx.fiber.dispose()}
})

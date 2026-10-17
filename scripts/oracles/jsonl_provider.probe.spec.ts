import {it} from 'vitest'
import {Context} from '@deepseek-ai/cordis'
import SessionStore from '@deepseek-ai/dsh-session'
import JsonlPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import {oneTurnLog} from '../../reference/packages/session/session-persistence/tests/contract.ts'
import {createHash} from 'node:crypto'
import {existsSync, readFileSync, writeFileSync} from 'node:fs'
import {join, relative} from 'node:path'

const directory = process.env.JSONL_PROVIDER_DIRECTORY!
const phase = process.env.JSONL_PROVIDER_PHASE!
const sha = (bytes: Buffer) => createHash('sha256').update(bytes).digest('hex')

it('observes actual original compressed and plaintext providers and mutual files', async () => {
  const rows: any[] = []
  const inputs: any[] = []
  for (const compression of ['zstd','none'] as const) {
    for (const batchSplit of [true,false]) {
      const key = compression + '-' + (batchSplit ? 'split' : 'whole')
      const root = join(directory, (phase === 'produce' ? 'source-' : 'native-') + key)
      const context = new Context()
      await context.plugin(SessionStore)
      const fiber = await context.plugin(JsonlPersistence, {root, compression})
      const provider: any = context.sessionPersistence
      const metadata: any = {id:'mutual-'+key+'中文😀', version:3, createdAt:1234, cwd:'C:/jsonl-provider-fixture', delegationDepth:0,isSeeded:false}
      const events = oneTurnLog()
      if (phase === 'produce') {
        const lazy = !existsSync(root)
        const handle = await provider.create(metadata)
        const detached = !existsSync(root)
        await handle.append(batchSplit ? events.slice(0,3) : events)
        const path = provider.locate(metadata).path
        const prior = readFileSync(path)
        if (batchSplit) await handle.append(events.slice(3))
        await handle.close()
        const appended = readFileSync(path)
        inputs.push({key, compression, batchSplit, metadata, events, path, revision:(await provider.stat(metadata.id)).revision})
        rows.push({id:'materialization/'+key,lazy,detached,retained:appended.subarray(0,prior.length).equals(prior),
          sha256:sha(appended),relative:relative(root,path).replaceAll('\\','/')})
      } else {
        const revisions = JSON.parse(readFileSync(join(directory,'native-revisions.json'),'utf8'))
        const snapshot = await provider.stat(metadata.id)
        if (snapshot.revision !== revisions[key]) throw new Error('Native cross-file full revision differs')
        const handle = await provider.open(metadata.id,'read')
        try {
          const loaded = await handle.read(),suffix = await handle.read(2)
          rows.push({id:'mutual/'+key,meta:handle.header,events:loaded.events,eventState:loaded.eventState,
            suffix:suffix.events,access:handle.access,revisionMatched:true,inheritedEventCount:handle.inheritedEventCount})
        } finally {await handle.close()}
      }
      await fiber.dispose()
    }
  }
  writeFileSync(join(directory,'source-'+phase+'.json'), JSON.stringify({node:process.versions.node,rows,inputs},null,2)+'\n')
})

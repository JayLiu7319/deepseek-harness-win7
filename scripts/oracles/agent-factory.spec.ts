import Rc1SessionProjections from '@deepseek-ai/dsh-session-projection'
// Observation-only probes against the pinned source. No Python behavior is mocked here.
import { it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import Llm from '@deepseek-ai/dsh-llm'
import Sessions, { SessionId } from '@deepseek-ai/dsh-session'
import Tools from '@deepseek-ai/dsh-tools'
import Prompt from '@deepseek-ai/dsh-system-prompt'
import Agents from '@deepseek-ai/dsh-agent'
import Loop from '@deepseek-ai/dsh-agent-loop'
import { writeFileSync } from 'node:fs'

it('records unpublished setup and abort observations', async () => {
  const rows: unknown[] = []
  for (const mode of ['success', 'reject', 'commit', 'caller-load', 'owner-load', 'factory-load',
                      'caller-setup', 'owner-setup', 'factory-setup']) {
    const ctx = new Context()
    await ctx.plugin(Llm); await ctx.plugin(Sessions); await ctx.plugin(Tools)
    await ctx.plugin(Prompt); await ctx.plugin(Agents)
    if (!ctx.sessionProjections) await ctx.plugin(Rc1SessionProjections);
    const factory = await ctx.plugin(Loop, { agents: [] })
    const owner = await ctx.plugin(Object.assign(() => {}, { inject: ['agents'] }))
    const signal = new AbortController()
    const session = ctx.sessions.prepare(SessionId('probe'))
    const reached = Promise.withResolvers<void>(), late = Promise.withResolvers<void>(), released = Promise.withResolvers<void>()
    let releases = 0, committed = 0
    let setupSession: unknown
    const events: string[] = []
    for (const name of ['session/created', 'agent/created', 'agent/session-start'] as const) {
      ctx.on(name, () => { events.push(name) })
    }
    ctx.provide('sessionPersistence', { open: async () => {
      if (mode.endsWith('-load')) { reached.resolve(); await late.promise }
      return { header: session.header, inheritedEventCount: session.inheritedEventCount,
        read: async () => ({ events: session.snapshotEvents(), eventState: 'shared-frozen' }),
        append: async () => {}, close: async () => { releases++; released.resolve() } }
    } } as any)
    const job = owner.ctx.agents.resume({ resumeSessionId: SessionId('probe'), options: {}, signal: signal.signal,
      setup: async (_scope, agent) => {
        setupSession = agent.session
        if (!mode.endsWith('-load')) { reached.resolve(); await late.promise }
        if (mode === 'reject') throw new Error('setup failed')
        return { commit: () => { if (mode === 'commit') throw new Error('commit failed'); committed++ } }
      },
    })
    const settled = job.then(handle => ({ handle, rejected: false, error: undefined }), error => ({ handle: undefined, rejected: true, error }))
    await Promise.race([reached.promise, settled.then(result => { if (result.rejected) throw result.error })])
    const before = { session: !!ctx.sessions.get(session.id), agent: !!ctx.agents.get(session.id), events: [...events] }
    if (mode.startsWith('caller-')) signal.abort(new Error('cancelled'))
    else if (mode.startsWith('owner-')) await owner.dispose()
    else if (mode.startsWith('factory-')) await factory.dispose()
    else late.resolve()
    const result = await settled
    late.resolve()
    if (result.rejected) await released.promise
    const after = { rejected: result.rejected, exact: Boolean(result.handle && result.handle.agent.session === setupSession),
      events: [...events], releases, committed }
    await result.handle?.dispose()
    const clean = !ctx.sessions.get(session.id) && !ctx.agents.get(session.id)
    await ctx.fiber.dispose()
    rows.push({ mode, before, after, clean })
  }
  writeFileSync(process.env.AGENT_ORACLE_OUTPUT!, JSON.stringify(rows, null, 2) + '\n')
}, 15000)

/** Derive frozen payload fixtures and systematic mutations from the explicit rc.3 Source. */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { createHash } from 'node:crypto'

const [sourceArg, outputArg] = process.argv.slice(2)
if (!sourceArg || !outputArg) throw new Error('Explicit Source and fresh output required')
const source = resolve(sourceArg), output = resolve(outputArg)
mkdirSync(output, { recursive: false })
const base = 'packages/session/session-format-v0-to-v1/'
const api = await import(pathToFileURL(join(source, base, 'src/index.ts')).href)
const validation = await import(pathToFileURL(join(source, base, 'src/validation.ts')).href)
const text = readFileSync(join(source, base, 'tests/validation.spec.ts'), 'utf8')
const start = text.indexOf('const textBlock = '), end = text.indexOf('\nfunction v1Artifact(')
if (start < 0 || end <= start) throw new Error('Source fixture declarations changed')
const fixturePath = join(output, 'source-fixtures.mts')
writeFileSync(fixturePath, text.slice(start, end) + '\nexport { validPayloads }\n', { encoding: 'utf8', flag: 'wx' })
const { validPayloads } = await import(pathToFileURL(fixturePath).href)
const cases: any[] = []
const clone = (value: any) => JSON.parse(JSON.stringify(value))
function add(name: string, event: any, version = 1, operation = 'payload') {
  let expected
  try {
    if (operation === 'semantics') api.assertReleasedPayloadSemantics(event, version)
    else validation.assertReleasedEventPayload(event, version)
    expected = { outcome: 'value', value: null }
  } catch (error: any) { expected = { outcome: 'error', name: error.name, message: error.message } }
  cases.push({ case: name, kind: 'released-logical', operation, version, event, expected })
}
function mutate(type: string, value: any, path: (string | number)[] = []): any[] {
  const opaque = api.RELEASED_V0_EVENT_DISPOSITIONS[type].opaque.includes(path[0])
    || path.at(-1) === 'replayState' || path.at(-1) === 'parameters'
  if (opaque) return []
  const replacement = value === null ? false : typeof value === 'string' ? 1
    : typeof value === 'number' || typeof value === 'boolean' ? 'invalid' : Array.isArray(value) ? {} : []
  const result: any[] = path.length ? [{ path, replacement }] : []
  if (value && typeof value === 'object') for (const [key, child] of Object.entries(value)) {
    result.push(...mutate(type, child, [...path, Array.isArray(value) ? Number(key) : key]))
  }
  return result
}
for (const [type, data] of Object.entries(validPayloads)) {
  const event = { type, seq: 3, time: 4, data }
  add(`${type}/valid`, event)
  for (const mutation of mutate(type, data)) {
    const altered = clone(data)
    let owner = altered
    for (const key of mutation.path.slice(0, -1)) owner = owner[key]
    owner[mutation.path.at(-1)!] = mutation.replacement
    add(`${type}/mutate/${mutation.path.join('.')}`, { ...event, data: altered })
  }
  for (const key of Object.keys(data as any)) {
    const altered = clone(data)
    delete altered[key]
    add(`${type}/omit/${key}`, { ...event, data: altered })
  }
  add(`${type}/unexpected`, { ...event, data: { ...(data as any), unexpected: true } })
}
// These known owner variants are deliberately extensible; unknown kinds stay opaque.
const user = (content: any[], source: any) => ({ type: 'user/message', seq: 3, time: 4, data: { id: 'user', role: 'user', content, source } })
const sources: any[] = [
  { kind: 'plugin', plugin: 'p', form: 'snapshot', sections: [{ name: 'n', text: '' }] },
  { kind: 'plugin', plugin: 'p', form: 'notice', summary: '' },
  { kind: 'plugin', plugin: 'compact', compactionId: 'c' },
  { kind: 'agent-instructions', form: 'instructions', changes: [{ action: 'set', scope: '', path: '' }], baseline: true },
  { kind: 'skill-catalog', form: 'catalog', entries: [{ name: 's', description: '' }], update: true },
  { kind: 'skill-invocation', form: 'instructions', name: 's' },
  { kind: 'coordinator', form: 'relay', senderSessionId: 's' },
  { kind: 'subagent-report', form: 'relay', senderSessionId: 's' },
  { kind: 'subagent-settled', form: 'notice', senderSessionId: 's', summary: '' },
  { kind: 'webhook', provider: 'p', source: 's', deliveryId: 'd', ruleId: 'r', form: 'notice', summary: '' },
  { kind: 'goal', goalId: 'g', revision: 1, round: 1 },
  { kind: 'session-reference', form: 'recall', version: 1, references: [{ sessionId: 's', label: '', capturedThroughSeq: null, compacted: false, originalMessages: 1, retainedMessages: 1, omittedMessages: 0, omittedBytes: 0, truncated: false, inputIndex: 0, capturedFormatVersion: 1 }] },
  { kind: 'owner-future', payload: { seq: 999 } },
]
const blocks: any[] = [
  { type: 'reasoning', text: '' },
  { type: 'image', attachment: { attachmentId: 'a', mediaType: 'image/png', bytes: 0, width: 1, height: 2, name: '', originalDimensions: { width: 1, height: 2 } } },
  { type: 'tool-call', id: 'c', name: 'n', arguments: '{}' },
  { type: 'tool-result', toolCallId: 'c', content: [{ type: 'text', text: '' }], isError: true },
  { type: 'owner-future', data: { seq: 999 } },
]
for (const [index, source] of sources.entries()) {
  add(`source-${index}/valid`, user([], source))
  for (const mutation of mutate('user/message', { source })) {
    const altered = clone({ source }); let owner = altered
    for (const key of mutation.path.slice(0, -1)) owner = owner[key]
    owner[mutation.path.at(-1)!] = mutation.replacement
    add(`source-${index}/mutate/${mutation.path.join('.')}`, user([], altered.source))
  }
}
for (const [index, block] of blocks.entries()) {
  add(`content-${index}/valid`, user([block], { kind: 'user' }))
  for (const mutation of mutate('user/message', { content: [block] })) {
    const altered = clone({ content: [block] }); let owner = altered
    for (const key of mutation.path.slice(0, -1)) owner = owner[key]
    owner[mutation.path.at(-1)!] = mutation.replacement
    add(`content-${index}/mutate/${mutation.path.join('.')}`, user(altered.content, { kind: 'user' }))
  }
}
writeFileSync(join(output, 'dispositions.json'), JSON.stringify(api.RELEASED_V0_EVENT_DISPOSITIONS, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' })
writeFileSync(join(output, 'payload-cases.json'), JSON.stringify(cases, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' })
writeFileSync(join(output, 'generation.json'), JSON.stringify({ source_fixture: base + 'tests/validation.spec.ts', source_fixture_sha256: createHash('sha256').update(text).digest('hex'), cases: cases.length }, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' })
console.log(cases.length)

/** Candidate-only observations from an unmodified rc.1 worktree. */
import { readFile, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { resolve, join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'

const [sourcePath, inputPath, outputPath] = process.argv.slice(2)
if (!sourcePath || !inputPath || !outputPath) throw new Error('Explicit Source, input and fresh output required')
const source = resolve(sourcePath)
const pin = 'a66e4702047846cdaa10c66c9d3df3951f5ea70d'
if (execFileSync('git', ['-C', source, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim() !== pin
    || execFileSync('git', ['-C', source, 'diff', 'HEAD', '--'], { encoding: 'utf8' }) !== '') {
  throw new Error('Source must be the clean pinned rc.1 candidate')
}
const bytes = await readFile(inputPath)
const input = JSON.parse(bytes.toString('utf8'))
Date.now = () => input.clock
const imported = []
async function load(path: string) {
  const bytes = await readFile(join(source, path))
  imported.push({ path, sha256: createHash('sha256').update(bytes).digest('hex') })
  return import(pathToFileURL(join(source, path)).href)
}
const { activeAtToken, formatFileMention } = await load('packages/context/file-reference/src/grammar.ts')
const { WorkspaceFileSearch, DEFAULT_FILE_SEARCH_EXCLUDED_DIRECTORIES } = await load('packages/context/file-reference-local/src/search.ts')
const { turnOutlineProjectionDefinition: definition } = await load('packages/session/session-turn-outline/src/projection.ts')
const { Session, SessionSeq, SessionLogOffset, SessionStore } = await load('packages/core/session/src/index.ts')
const { toHeaderLine, parseHeader, scanLog } = await load('packages/session/session-persistence-jsonl/src/format.ts')
const { SessionProjectionRegistry } = await load('packages/session/session-projection/src/index.ts')
const { default: SystemPrompt } = await load('packages/core/system-prompt/src/index.ts')
const require = createRequire(join(source, 'packages/core/system-prompt/package.json'))
const { Context } = await import(pathToFileURL(require.resolve('@deepseek-ai/cordis')).href)
const observations: any = {
  grammar: input.tokens.map((row: any) => activeAtToken(row.line, row.cursor) ?? null),
  mentions: input.mentions.map((row: any) => formatFileMention(row.candidate, row.quote) ?? null),
  searches: [], positions: [], outline: [], changes: [], orders: {},
  searchLimits: [],
  lineage: [], storageLineage: [], strictHeaders: [],
}
function scalar(token: string) {
  return token === '-0' ? -0 : token === 'NaN' ? NaN : token === 'Infinity' ? Infinity : JSON.parse(token)
}
for (const row of input.lineage) {
  try {
    const cut = row.cut === undefined ? undefined : scalar(row.cut)
    const session = row.mode === 'restore'
      ? Session.fromRestore(row.header.id, row.seed, row.header, cut)
      : Session.create(row.header.id, row.seed, row.header, cut)
    const owned = session.ownEvents()
    observations.lineage.push({ header: session.header, firstLiveSeq: session.firstLiveSeq,
      inheritedEventCount: session.inheritedEventCount, seq: session.seq, owned,
      ownPositions: [-1, 0, 1, 2, 3, session.seq].map(seq => session.isOwnSeq(seq)) })
  } catch (error: any) { observations.lineage.push({ error: error.message }) }
}
for (const row of input.storageLineage) {
  try {
    const physical = row.physical ?? toHeaderLine(row.header, row.cut === undefined ? undefined : scalar(row.cut))
    const line = JSON.stringify(physical)
    const parsed = parseHeader(line)
    const scanned = scanLog(Buffer.from(line + '\n'))
    observations.storageLineage.push({ physical, parsed: parsed ?? null,
      scanned: { meta: scanned.meta, inheritedEventCount: scanned.inheritedEventCount } })
  } catch (error: any) { observations.storageLineage.push({ error: error.message }) }
}
for (const row of input.strictHeaders) {
  const header = { ...row }
  if (header.seedLength === 'UNDEFINED') header.seedLength = undefined
  try { observations.strictHeaders.push({ header: Session.fromRestore('child', [], header, 0).header }) }
  catch (error: any) { observations.strictHeaders.push({ error: error.message }) }
}
const search = new WorkspaceFileSearch(input.workspace, {
  maxResults: 20, maxEntries: 50000, excludedDirectories: DEFAULT_FILE_SEARCH_EXCLUDED_DIRECTORIES,
})
try {
  for (const query of input.queries) observations.searches.push(await search.list(query, new AbortController().signal))
} finally { search.dispose() }
for (const config of input.searchConfigs) {
  try {
    const configured = new WorkspaceFileSearch(input.workspace, {
      maxResults: 20, maxEntries: 50000, excludedDirectories: DEFAULT_FILE_SEARCH_EXCLUDED_DIRECTORIES, ...config,
    })
    try { observations.searchLimits.push({ accepted: true, candidates: await configured.list('py', new AbortController().signal) }) }
    finally { configured.dispose() }
  } catch (error: any) { observations.searchLimits.push({ accepted: false, error: error.message }) }
}
for (const name of ['SessionSeq', 'SessionLogOffset']) {
  for (const token of input.positions) {
    const value = token === '-0' ? -0 : token === 'NaN' ? NaN : token === 'Infinity' ? Infinity : JSON.parse(token)
    try { observations.positions.push({ name, token, value: (name === 'SessionSeq' ? SessionSeq : SessionLogOffset)(value) }) }
    catch (error: any) { observations.positions.push({ name, token, error: error.message }) }
  }
}
const ctx = new Context()
try {
  await ctx.plugin(SessionStore)
  await ctx.plugin(SessionProjectionRegistry)
  await ctx.plugin(SystemPrompt)
  ctx.sessionProjections.register(definition)
  ctx.sessionProjections.onChanged((_session: any, _key: any, value: any, seq: any) => observations.changes.push({ seq, value }))
  const session = ctx.sessions.create('paired-outline')
  for (const event of input.events) {
    session.append(event.type, event.data, event.surfaceOp === undefined ? undefined : { surfaceOp: event.surfaceOp })
    observations.outline.push(ctx.sessionProjections.snapshot(session))
  }
  const first = session.snapshotEvents()
  const subset = session.snapshotEvents(SessionLogOffset(0), SessionLogOffset(1))
  observations.indexed = {
    cached: first === session.snapshotEvents(), first: session.eventAt(SessionSeq(0)),
    absent: session.eventAt(SessionSeq(session.seq)) === undefined,
    range: session.snapshotEvents(SessionLogOffset(1), SessionLogOffset(3)),
    frozen: Object.isFrozen(first) && Object.isFrozen(subset) && Object.isFrozen(first[0]),
  }
  session.append('probe/mark', {})
  observations.indexed.stable = first.length === input.events.length && subset.length === 1
  for (const name of input.sectionNames) observations.orders[name] = ctx.systemPrompt.getSectionOrder(name)
  for (const name of input.contextNames) observations.orders[name] = ctx.systemPrompt.getContextOrder(name)
  observations.checkpoint = ctx.sessionProjections.checkpoint(session)
  ctx.sessionProjections.register({ key: 'lineageProbe', stateVersion: 1,
    stateSchema: { parse: (value: any) => value },
    init: (_header: any, cut: number) => ({ cut, own: [] }),
    apply: (state: any, event: any) => event.seq < state.cut ? state : { cut: state.cut, own: [...state.own, event.seq] },
    wire: { view: (state: any) => state, viewSchema: { parse: (value: any) => value } },
  })
  const child = Session.create('lineage-child', input.lineage[1].seed,
    { ...input.lineage[1].header, id: 'lineage-child' }, SessionLogOffset(2))
  const checkpoint = ctx.sessionProjections.checkpoint(child)
  child.append('probe/owned', {})
  observations.projectionLineage = {
    initial: checkpoint.lineageProbe,
    full: ctx.sessionProjections.restore({}, child.snapshotEvents(), 0, child.header, child.inheritedEventCount),
    tail: ctx.sessionProjections.restore(checkpoint, child.snapshotEvents(SessionLogOffset(4)), 4, child.header, child.inheritedEventCount),
  }
} finally { await ctx.fiber.dispose() }
await writeFile(outputPath, JSON.stringify({ pin, node: process.version, inputSha256: createHash('sha256').update(bytes).digest('hex'), imported, observations }, null, 2) + '\n', { flag: 'wx' })

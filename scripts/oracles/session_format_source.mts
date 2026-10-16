import { readFileSync, writeFileSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { pathToFileURL } from 'node:url'

const [sourceArg, corpusArg, outputArg] = process.argv.slice(2)
if (!sourceArg || !corpusArg || !outputArg) throw new Error('Explicit Source, corpus and fresh output required')
const api = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format/src/index.ts')).href)
const header = (version: number) => ({ version, id: 'paired-session', createdAt: 1, isSeeded: false, delegationDepth: 0 })
const fail = (message: string): never => { throw new Error(message) }
function decode(value: any): any {
  if (value && !Array.isArray(value) && typeof value === 'object') {
    if (Object.keys(value).length === 1 && '$scalar' in value) {
      return ({ undefined, '-0': -0, NaN, Infinity } as any)[value.$scalar]
    }
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, decode(child)]))
  }
  return Array.isArray(value) ? value.map(decode) : value
}
function options(test: any, observations: any[]) {
  const current = test.current ?? 2
  return {
    currentVersion: current,
    restoreCurrentHeader: (value: any) => ({ ...value, version: test.restoredHeaderVersion ?? current }),
    migrations: (test.edges ?? [{ first: 0 }, { first: 1 }]).map((spec: any) => ({
      name: spec.name ?? `edge-${spec.first}`, fromVersion: spec.first, toVersion: spec.last ?? spec.first + 1,
      migrateHeader(value: any) {
        if (spec.fail === 'header') fail('blocked header')
        return { ...value, version: spec.headerVersion ?? spec.last ?? spec.first + 1 }
      },
      validateTargetHeader() { if (spec.fail === 'validate') fail('blocked validation') },
      createStage(source: any) {
        if (spec.fail === 'create') fail('blocked create')
        const inherited = 'cut' in spec ? spec.cut : source.sourceInheritedEventCount
        observations.push({ first: spec.first, sourceKind: source.sourceKind, sourceCut: source.sourceInheritedEventCount ?? null })
        const transform = (event: any) => ({ ...event, hops: [...(event.hops ?? []), spec.first] })
        return {
          ...(inherited === undefined ? {} : { headerInheritedEventCount: inherited }),
          transformEvent(event: any, context: any) {
            if (spec.fail === 'event') fail('blocked event')
            context.emitEvent(transform(event))
          },
          transformRun(run: any, context: any) {
            if (spec.fail === 'run') fail('blocked run')
            context.emitRun({ *expand() { for (const event of run.expand()) yield transform(event) } })
          },
          finish(context: any) {
            if (spec.fail === 'finish') fail('blocked finish')
            if (spec.tail) context.emitEvent({ tail: spec.first })
            return spec.finishCut ?? inherited ?? 0
          },
        }
      },
    })),
  }
}
function catalog(test: any, observations: any[]) {
  const config = options(test, observations)
  const codec = (version: number) => ({ version, decodeHeader: (value: any) => value,
    createDecoder(value: any) {
      if (test.fail === 'decoder-create') fail('bad decoder create')
      return {
        header: value, ...(test.unknownCut ? {} : { headerInheritedEventCount: test.cut ?? 0 }),
        decodeRow(row: any, context: any) {
          if (test.fail === 'decoder-row') fail('bad physical row')
          if (Array.isArray(row)) context.emitRun({ *expand() { yield* row } })
          else context.emitEvent(row)
        },
        finish() {
          if (test.fail === 'decoder-finish') fail('bad decoder finish')
          return test.decoderFinishCut ?? test.cut ?? 0
        },
      }
    },
  })
  function restore(value: any) {
    if (test.fail === 'restore') fail('bad target artifact')
    if (test.fail === 'explicit') throw new api.SessionFormatUnsupportedMigrationError('explicit refusal')
    return { ...value, header: { ...value.header, version: test.restoredVersion ?? test.current ?? 2 } }
  }
  return api.createSessionFormatCatalog({ ...config,
    codecs: (test.codecs ?? Array.from({ length: config.currentVersion + 1 }, (_, i) => i)).map(codec),
    currentEncoder: { encodeHeader: (value: any) => ({ ...value, version: test.encodedVersion ?? config.currentVersion }), encodeEvent: (value: any) => value },
    restoreCurrent: restore, restoreTransformedCurrent: restore,
  })
}
function execute(test: any): any {
  const kind = test.kind
  if (kind === 'count' || kind === 'safe') return (kind === 'count' ? api.sessionFormatCount : api.sessionFormatSafeInteger)(decode(test.value), 'coordinate')
  if (kind === 'filename') return api.parseSessionFormatLogFilename(test.value) ?? null
  if (kind === 'filename-write') return api.sessionFormatLogFilename(decode(test.value))
  if (kind === 'snapshot') {
    const value = decode(test.value)
    if (test.cycle) value.self = value
    const result = (test.header ? api.snapshotSessionFormatHeader : api.snapshotSessionFormatJson)(value)
    let frozen = true
    if (result && !Array.isArray(result) && typeof result === 'object') {
      try { result.changed = true; frozen = false } catch {}
    }
    return { value: result, frozen }
  }
  const observations: any[] = []
  if (kind === 'chain') {
    const chain = api.createSessionFormatChain(options(test, observations)), source = header(test.stored ?? 0)
    if (test.headerOnly) return chain.migrateHeader(source)
    const collector = new api.SessionFormatEventCollector()
    const stream = chain.createStream(source, test.unknownCut ? undefined : test.cut ?? 0, collector)
    stream.emitEvent({ seq: 0 })
    stream.emitRun({ *expand() { yield { seq: 1 }; yield { seq: 2 } } })
    const cut = stream.finish()
    return { header: stream.header, events: collector.values, cut, stages: observations }
  }
  if (kind === 'catalog') {
    const current = catalog(test, observations), source = 'header' in test ? decode(test.header) : header(test.stored ?? 0)
    if (test.operation === 'read') return current.readHeader(source)
    if (test.operation === 'encode') return current.encodeCurrentHeader(source, test.cut ?? 0)
    const restore = current.createRestore(source, { recovery: 'strict', validation: test.validation ?? 'transformed' })
    restore.decodeRow({ seq: 0 })
    restore.decodeRow([{ seq: 1 }, { seq: 2 }])
    return restore.finish()
  }
  throw new Error(`Unknown scenario kind: ${kind}`)
}
const corpus = JSON.parse(readFileSync(resolve(corpusArg), 'utf8'))
const result = corpus.map((test: any) => {
  try { return { case: test.case, outcome: 'value', value: execute(test) } }
  catch (error: any) { return { case: test.case, outcome: 'error', name: error.name, message: error.message,
    ...(error.cause === undefined ? {} : { cause: error.cause instanceof Error ? error.cause.message : String(error.cause) }) } }
})
writeFileSync(resolve(outputArg), JSON.stringify(result, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' })

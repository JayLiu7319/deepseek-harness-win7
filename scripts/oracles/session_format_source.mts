import { readFileSync, writeFileSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { pathToFileURL } from 'node:url'

const [sourceArg, corpusArg, outputArg] = process.argv.slice(2)
if (!sourceArg || !corpusArg || !outputArg) throw new Error('Explicit Source, corpus and fresh output required')
const api = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format/src/index.ts')).href)
const old = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format-v0-to-v1/src/codec.ts')).href)
const v2 = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format-v1-to-v2/src/codec.ts')).href)
const released = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format-v0-to-v1/src/index.ts')).href)
const releasedValidation = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format-v0-to-v1/src/validation.ts')).href)
const releasedRestore = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format-v0-to-v1/src/testing/restore.ts')).href)
const releasedV2 = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format-v1-to-v2/src/index.ts')).href)
const v2Writer = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format-v1-to-v2/src/testing/validation.ts')).href)
const assistantStream = await import(pathToFileURL(join(resolve(sourceArg), 'packages/llm/llm/src/assistant-stream.ts')).href)
const releasedV3 = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format-v2-to-v3/src/index.ts')).href)
const v3Payload = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format-v2-to-v3/src/payload.ts')).href)
const v3References = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format-v2-to-v3/src/references.ts')).href)
const currentCatalog = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format-catalog/src/index.ts')).href)
const installedCurrent = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-format-catalog/src/current.ts')).href)
const jsonlCurrent = await import(pathToFileURL(join(resolve(sourceArg), 'packages/session/session-persistence-jsonl/src/format.ts')).href)
const sessionRuntime = await import(pathToFileURL(join(resolve(sourceArg), 'packages/core/session/src/index.ts')).href)
const {sessionRuntimeCase} = await import('./session_runtime_source.mts')
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
  if(kind==='jsonl-current') {
    const bytesValues=(v:any):any=>v&&typeof v==='object'?Array.isArray(v)?v.map(bytesValues):Object.keys(v).length===1&&'$bytes'in v?Buffer.from(v.$bytes,'hex'):Object.fromEntries(Object.entries(v).map(([k,c])=>[k,bytesValues(c)])):v
    if(test.operation==='function')return jsonlCurrent[test.name](...bytesValues(decode(test.args)))??null
    const scanner=new jsonlCurrent.SessionLogScanner(bytesValues(test.header),test.recovery)
    let result:any={checkpoint:scanner.checkpoint()}
    for(const action of test.actions) {
      if(action.method==='write'){scanner.write(bytesValues(action.chunk));result={checkpoint:scanner.checkpoint()}}
      else if(action.method==='checkpoint')result={checkpoint:scanner.checkpoint()}
      else if(action.method==='finish'){const finished=scanner.finish();result={checkpoint:scanner.checkpoint(),result:finished}}
    }
    return result
  }
  if(kind==='session-catalog') {
    const catalog=currentCatalog.sessionFormatCatalog,operation=test.operation
    if(operation==='currentHeader'){installedCurrent.validateInstalledCurrentSessionHeader(decode(test.header));return null}
    if(operation==='currentArtifact'){installedCurrent.validateInstalledCurrentSessionArtifact(decode(test.artifact));return null}
    if(operation==='readHeader')return catalog.readHeader(decode(test.header))
    if(operation==='encodeCurrentHeader')return catalog.encodeCurrentHeader(decode(test.header),decode(test.cut))
    if(operation==='encodeCurrentEvent')return catalog.encodeCurrentEvent(decode(test.event))
    const reader=catalog.createRestore(decode(test.header),decode(test.options))
    for(const row of test.rows??[])reader.decodeRow(decode(row))
    return test.finish?reader.finish():{header:reader.header}
  }
  if (kind === 'released-v3-logical') {
    const operation=test.operation
    if(['assertEvent','assertV3Event','assertV3StructuralRow','canonicalizeTransformedEvent','isRepairIdentity'].includes(operation))return v3Payload[operation](...decode(test.args))??null
    if(operation==='remapEvent')return v3References.remapEvent(...decode(test.args))
    if(operation==='header') {releasedV3.assertReleasedV3Header(decode(test.header));return null}
    if(operation==='migrateHeader')return releasedV3.sessionFormatV2ToV3.migrateHeader(decode(test.header))
    if(operation==='restore')return releasedV3.restoreReleasedV3Artifact(decode(test.artifact),new Set(test.known))
    const codec=releasedV3.releasedV3SessionFormatCodec
    if(operation==='decodeHeader')return codec.decodeHeader(decode(test.header))
    if(operation==='encodeHeader')return codec.encodeHeader(decode(test.header),decode(test.cut))
    if(operation==='encodeEvent')return codec.encodeEvent(decode(test.event))
    const collector=new api.SessionFormatEventCollector()
    if(operation==='decoder') {
      const decoder=codec.createDecoder(decode(test.header),test.recovery)
      for(const row of test.rows)decoder.decodeRow(decode(row),collector)
      return {header:decoder.header,events:collector.values,...(test.finish?{cut:decoder.finish(collector)}:{})}
    }
    if(operation==='stage') {
      const stage=releasedV3.sessionFormatV2ToV3.createStage(decode(test.input)),result:any={events:collector.values}
      for(const action of test.actions) {
        if(action.method==='finish')result.cut=stage.finish(collector)
        else if(action.method==='transformEvent')stage.transformEvent(decode(action.event),collector)
        else stage.transformRun({*expand(){yield*decode(action.expanded)}},collector)
      }
      return result
    }
    throw new Error('Unknown v3 operation: '+operation)
  }
  if (kind === 'assistant-stream') {
    if(test.operation==='push'||test.operation==='snapshot') {
      const accumulator=new assistantStream.AssistantStreamAccumulator()
      let result=null
      for(const timed of decode(test.timed)) result=accumulator.push(timed)
      return test.operation==='snapshot'?accumulator.snapshot():result
    }
    if(test.operation==='assemble') {
      const assembler=assistantStream.assembleAssistantStream(decode(test.stream))
      return {blocks:assembler.blocks(),interrupted:assembler.interruptedBlocks(),finish:assembler.finish,
        ...(assembler.usage===undefined?{}:{usage:assembler.usage}),...(assembler.replayState===undefined?{}:{replayState:assembler.replayState})}
    }
    return assistantStream[test.operation](...decode(test.args))??null
  }
  if (kind === 'released-v2-logical') {
    if(test.operation==='stage') {
      const stage=releasedV2.sessionFormatV1ToV2.createStage(decode(test.input)), collector=new api.SessionFormatEventCollector()
      const result: any={events:collector.values}
      for(const action of test.actions) {
        if(action.method==='finish') result.cut=stage.finish(collector)
        else if(action.method==='transformEvent') stage.transformEvent(decode(action.event),collector)
        else if(action.method==='transformRun') stage.transformRun({...decode(action.run),*expand(){yield*decode(action.expanded)}},collector)
        else throw new Error('Unknown stage method: '+action.method)
      }
      result.events=collector.values
      return result
    }
    const artifact = decode(test.artifact)
    if (test.operation === 'writer') { v2Writer.assertReleasedV2Artifact(artifact); return null }
    if (test.operation === 'restore') return releasedV2.restoreReleasedV2Artifact(artifact, new Set(test.known), test.relationshipVersion)
    if (test.operation !== 'migrate') throw new Error('Unknown v2 logical operation: ' + test.operation)
    const restore = (value: any) => { v2Writer.assertReleasedV2Artifact(value); return value }
    const catalog = api.createSessionFormatCatalog({currentVersion:2,
      codecs:[old.releasedV0SessionFormatCodec,old.releasedV1SessionFormatCodec,v2.releasedV2SessionFormatCodec],
      currentEncoder:v2.releasedV2SessionFormatCodec,migrations:[released.sessionFormatV0ToV1,releasedV2.sessionFormatV1ToV2],
      restoreCurrent:restore,restoreTransformedCurrent:restore,
      restoreCurrentHeader:(value: any)=>{releasedV2.assertReleasedV2Header(value);return value}})
    const source = artifact.header
    const physical = {type:'session',version:1,id:source.id,createdAt:source.createdAt,delegationDepth:source.delegationDepth,
      ...Object.fromEntries(['cwd','parentSession','origin','agentPreset'].filter(key=>source[key]!==undefined).map(key=>[key,source[key]])),
      ...(source.isSeeded?{seedLength:artifact.inheritedEventCount}:{})}
    const current = catalog.createRestore(physical,{recovery:'strict',validation:'current'})
    for(const row of artifact.events) current.decodeRow(row)
    return current.finish()
  }
  if (kind === 'released-logical') {
    switch (test.operation) {
      case 'semantics': released.assertReleasedPayloadSemantics(decode(test.event), test.version); break
      case 'payload': released.assertReleasedEventPayload(decode(test.event), test.version); break
      case 'relationships': released.assertReleasedArtifactRelationships(decode(test.artifact), test.extensions); break
      case 'surface-metadata': released.assertReleasedSurfaceMetadata(decode(test.event), test.event.seq, test.event.type, test.assistantSources ?? 'allow-empty-assistant'); break
      case 'header': releasedValidation.assertReleasedSessionFormatHeader(decode(test.header), test.version); break
      case 'coordinates': releasedValidation.assertReleasedArtifactCoordinates(decode(test.artifact), test.allowLegacy ?? false, test.known ? new Set(test.known) : undefined, test.neutral ?? false, test.frozen ?? false); break
      case 'restore-v0': return releasedRestore.restoreV0ToV1(decode(test.header), decode(test.rows), test.recovery ?? 'strict')
      case 'restore-v1': return releasedRestore.restoreV1(decode(test.header), decode(test.rows), test.recovery ?? 'strict')
      default: throw new Error('Unknown released logical operation: ' + test.operation)
    }
    return null
  }
  if (kind === 'released-codec') {
    const codec = [old.releasedV0SessionFormatCodec, old.releasedV1SessionFormatCodec, v2.releasedV2SessionFormatCodec][test.version]
    const source = decode(test.header)
    if (test.operation === 'header') return codec.decodeHeader(source)
    if (test.operation === 'encode') return { header: codec.encodeHeader(source, test.cut ?? 0), rows: (test.rows ?? []).map((event: any) => codec.encodeEvent(decode(event))) }
    const decoder = codec.createDecoder(source, test.recovery ?? 'strict'), items: any[] = [], collector = new api.SessionFormatEventCollector()
    const context = {
      emitEvent(event: any) { items.push({ event }); collector.emitEvent(event) },
      emitRun(run: any) { items.push({ run: Object.fromEntries(Object.entries(run).filter(([key]) => key !== 'expand')) }); collector.emitRun(run) },
    }
    for (const row of test.rows ?? []) decoder.decodeRow(decode(row), context)
    return { header: decoder.header, earlyCut: decoder.headerInheritedEventCount ?? null, cut: decoder.finish(context), items, events: collector.values }
  }
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
const result = []
for (const test of corpus) {
  try { result.push({ case: test.case, outcome: 'value', value: test.kind==='session-reference-current'
    ? await (await import('./session_reference_current_source.mts')).sessionReferenceCase(resolve(sourceArg),test)
    : test.kind==='instructions-current'
    ? await (await import('./instructions_current_source.mts')).instructionsCase(resolve(sourceArg),test)
    : test.kind==='log-export-current'
    ? await (await import('./log_export_current_source.mts')).logExportCase(resolve(sourceArg),test)
    : test.kind==='headless-current'
    ? await (await import('./headless_current_source.mts')).headlessCase(resolve(sourceArg),test)
    : test.kind==='session-log-current'
    ? await (await import('./session_log_current_source.mts')).sessionLogCase(resolve(sourceArg),test,decode)
    : test.kind==='telemetry-current'
    ? await (await import('./telemetry_current_source.mts')).telemetryCase(resolve(sourceArg),test)
    : test.kind==='session-stats-current'
    ? await (await import('./session_stats_current_source.mts')).statsCase(resolve(sourceArg),test,decode)
    : test.kind==='http-proxy-install-current'
    ? await (await import('./http_proxy_install_current_source.mts')).httpProxyInstallCase(resolve(sourceArg),test)
    : test.kind==='http-proxy-current'
    ? await (await import('./http_proxy_current_source.mts')).httpProxyCase(resolve(sourceArg),test)
    : test.kind==='boot-layers-current'
    ? await (await import('./boot_layers_current_source.mts')).bootLayersCase(resolve(sourceArg),test)
    : test.kind==='profile-init-current'
    ? await (await import('./profile_init_current_source.mts')).profileInitCase(resolve(sourceArg),test)
    : test.kind==='mcp-current'
    ? await (await import('./mcp_current_source.mts')).mcpCurrentCase(resolve(sourceArg),test)
    : test.kind==='open-in-app-host-current'
    ? await (await import('./open_in_app_host_current_source.mts')).openInAppHostCase(resolve(sourceArg),test)
    : test.kind==='open-in-app-current'
    ? await (await import('./open_in_app_current_source.mts')).openInAppCase(resolve(sourceArg),test)
    : test.kind==='workspace-current'
    ? await (await import('./workspace_current_source.mts')).workspaceCase(resolve(sourceArg),test)
    : test.kind==='present-open-current'
    ? await (await import('./present_open_current_source.mts')).presentOpenCase(resolve(sourceArg),test)
    : test.kind==='file-tools-current'
    ? await (await import('./file_tools_current_source.mts')).fileToolsCase(resolve(sourceArg),test)
    : test.kind==='present-current'
    ? await (await import('./present_current_source.mts')).presentCase(resolve(sourceArg),test)
    : test.kind==='workspace-files-current'
    ? await (await import('./workspace_files_current_source.mts')).workspaceFilesCase(resolve(sourceArg),test)
    : test.kind==='fs-range-current'
    ? await (await import('./fs_range_current_source.mts')).fsRangeCase(resolve(sourceArg),test)
    : test.kind==='session-facade-current'
    ? await (await import('./session_facade_current_source.mts')).sessionFacadeCase(resolve(sourceArg),test)
    : test.kind==='native-path-current'
    ? await (await import('./native_path_current_source.mts')).nativePathCase(resolve(sourceArg),test)
    : test.kind==='session-history-current'
    ? await (await import('./session_history_current_source.mts')).sessionHistoryCase(resolve(sourceArg),test)
    : test.kind==='session-list-current'
    ? await (await import('./session_list_current_source.mts')).sessionListCase(resolve(sourceArg),test)
    : test.kind==='session-agents-current'
    ? await (await import('./session_agents_current_source.mts')).sessionAgentsCase(resolve(sourceArg),test)
    : test.kind==='session-media-current'
    ? await (await import('./session_media_current_source.mts')).sessionMediaCase(resolve(sourceArg),test)
    : test.kind==='attachment-images-current'
    ? await (await import('./attachment_images_current_source.mts')).attachmentImagesCase(resolve(sourceArg),test)
    : test.kind==='file-upload-current'
    ? await (await import('./file_upload_current_source.mts')).fileUploadCase(resolve(sourceArg),test)
    : test.kind==='llm-files-current'
    ? await (await import('./llm_files_current_source.mts')).llmFilesCase(resolve(sourceArg),test)
    : test.kind==='attachment-files-current'
    ? await (await import('./attachment_files_current_source.mts')).attachmentFilesCase(resolve(sourceArg),test)
    : test.kind==='session-runtime'
    ? sessionRuntimeCase(sessionRuntime,test,decode)
    : test.kind==='query-current'
    ? await (await import('./session_query_current_source.mts')).queryCurrentCase(resolve(sourceArg),test,decode)
    : test.kind==='loop-current'
    ? await (await import('./agent_loop_current_source.mts')).loopCurrentCase(resolve(sourceArg),test,decode)
    : test.kind==='machine-current'
    ? await (await import('./agent_machine_current_source.mts')).machineCurrentCase(resolve(sourceArg),test,decode)
    : test.kind==='storage-backend'
    ? await (await import('./session_backend_current_source.mts')).backendCase(resolve(sourceArg),test,decode)
    : test.kind==='storage-contract'||test.kind==='storage-handle'
    ? await (await import('./session_storage_source.mts')).storageCase(resolve(sourceArg),test,decode)
    : test.kind==='generation'
    ? await (await import('./session_generation_source.mts')).generationCase(resolve(sourceArg), test)
    : execute(test) }) }
  catch (error: any) { result.push({ case: test.case, outcome: 'error', name: error.name, message: error.message,
    ...(error.cause === undefined ? {} : { cause: error.cause instanceof Error ? error.cause.message : String(error.cause) }) }) }
}
writeFileSync(resolve(outputArg), JSON.stringify(result, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' })

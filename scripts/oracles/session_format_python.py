"""Candidate rc.3 format observations; synthetic edges deliberately exercise the planner.

These are library contracts, not released codecs or persistence acceptance.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dsh.core.session.json import UNDEFINED
from dsh.session.format import (SessionFormatError, SessionFormatUnsupportedMigrationError,
    SessionFormatEventCollector, createSessionFormatChain, createSessionFormatCatalog,
    parseSessionFormatLogFilename, sessionFormatLogFilename, sessionFormatCount,
    sessionFormatSafeInteger, snapshotSessionFormatHeader, snapshotSessionFormatJson)


def decode(value):
    if isinstance(value, dict):
        if set(value) == {'$scalar'}:
            return {'undefined': UNDEFINED, '-0': -0.0, 'NaN': math.nan, 'Infinity': math.inf}[value['$scalar']]
        return {key: decode(child) for key, child in value.items()}
    if isinstance(value, list):
        return [decode(child) for child in value]
    return value


def header(version):
    return dict(version=version, id='paired-session', createdAt=1, isSeeded=False, delegationDepth=0)


def fail(message):
    raise RuntimeError(message)


def options(case, observations):
    current = case.get('current', 2)
    migrations = []
    for spec in case.get('edges', [dict(first=0), dict(first=1)]):
        first = spec['first']
        def migrate(value, spec=spec):
            if spec.get('fail') == 'header':
                fail('blocked header')
            return dict(value, version=spec.get('headerVersion', spec.get('last', spec['first'] + 1)))

        def validate(value, spec=spec):
            if spec.get('fail') == 'validate':
                fail('blocked validation')

        def create(source, spec=spec):
            if spec.get('fail') == 'create':
                fail('blocked create')
            inherited = spec.get('cut', source['sourceInheritedEventCount'])
            observations.append(dict(first=spec['first'], sourceKind=source['sourceKind'],
                sourceCut=None if source['sourceInheritedEventCount'] is UNDEFINED else source['sourceInheritedEventCount']))

            def transform(event):
                return dict(event, hops=event.get('hops', []) + [spec['first']])

            def on_event(event, context):
                if spec.get('fail') == 'event':
                    fail('blocked event')
                context.emitEvent(transform(event))

            def on_run(run, context):
                if spec.get('fail') == 'run':
                    fail('blocked run')
                context.emitRun(dict(expand=lambda: (transform(e) for e in run['expand']())))

            def finish(context):
                if spec.get('fail') == 'finish':
                    fail('blocked finish')
                if spec.get('tail'):
                    context.emitEvent(dict(tail=spec['first']))
                return spec.get('finishCut', 0 if inherited is UNDEFINED else inherited)

            stage = dict(transformEvent=on_event, transformRun=on_run, finish=finish)
            if inherited is not UNDEFINED:
                stage['headerInheritedEventCount'] = inherited
            return stage

        migrations.append(dict(name=spec.get('name', 'edge-%s' % first), fromVersion=first,
            toVersion=spec.get('last', first + 1), migrateHeader=migrate,
            validateTargetHeader=validate, createStage=create))
    return dict(currentVersion=current, migrations=migrations,
        restoreCurrentHeader=lambda value: dict(value, version=case.get('restoredHeaderVersion', current)))


def catalog(case, observations):
    config = options(case, observations)
    def codec(version):
        def decoder(value, recovery):
            if case.get('fail') == 'decoder-create':
                fail('bad decoder create')
            def row(value, context):
                if case.get('fail') == 'decoder-row':
                    fail('bad physical row')
                if isinstance(value, list):
                    context.emitRun(dict(expand=lambda: iter(value)))
                else:
                    context.emitEvent(value)
            def finish(context):
                if case.get('fail') == 'decoder-finish':
                    fail('bad decoder finish')
                return case.get('decoderFinishCut', case.get('cut', 0))
            result = dict(header=value, decodeRow=row, finish=finish)
            if not case.get('unknownCut'):
                result['headerInheritedEventCount'] = case.get('cut', 0)
            return result
        return dict(version=version, decodeHeader=lambda value: value, createDecoder=decoder)

    def restore(value):
        if case.get('fail') == 'restore':
            fail('bad target artifact')
        if case.get('fail') == 'explicit':
            raise SessionFormatUnsupportedMigrationError('explicit refusal')
        return dict(value, header=dict(value['header'], version=case.get('restoredVersion', case.get('current', 2))))

    config.update(codecs=[codec(version) for version in case.get('codecs', range(config['currentVersion'] + 1))],
        currentEncoder=dict(encodeHeader=lambda value, cut: dict(value, version=case.get('encodedVersion', config['currentVersion'])),
            encodeEvent=lambda value: value), restoreCurrent=restore, restoreTransformedCurrent=restore)
    return createSessionFormatCatalog(config)


def execute(case):
    if case['kind'] == 'jsonl-current':
        from dsh.session import jsonl_current as framing
        def bytes_values(value):
            if isinstance(value, dict):
                if set(value) == {'$bytes'}:
                    return bytes.fromhex(value['$bytes'])
                return {key:bytes_values(child) for key,child in value.items()}
            return [bytes_values(child) for child in value] if isinstance(value, list) else value
        if case['operation'] == 'function':
            name = {'encodeSegment':'encode_segment', 'projectKey':'project_key'}.get(case['name'],case['name'])
            return getattr(framing,name)(*bytes_values(decode(case['args'])))
        scanner = framing.SessionLogScanner(bytes_values(case['header']),case['recovery'])
        result = dict(checkpoint=scanner.checkpoint())
        for action in case['actions']:
            if action['method'] == 'write':
                scanner.write(bytes_values(action['chunk']))
                result = dict(checkpoint=scanner.checkpoint())
            elif action['method'] == 'checkpoint':
                result = dict(checkpoint=scanner.checkpoint())
            elif action['method'] == 'finish':
                finished = scanner.finish()
                result = dict(checkpoint=scanner.checkpoint(), result=finished)
        return result
    if case['kind'] == 'session-catalog':
        from dsh.session.format_catalog import sessionFormatCatalog
        from dsh.session.format_catalog.current import validateInstalledCurrentSessionHeader, validateInstalledCurrentSessionArtifact
        operation = case['operation']
        if operation == 'currentHeader':
            return validateInstalledCurrentSessionHeader(decode(case['header']))
        if operation == 'currentArtifact':
            return validateInstalledCurrentSessionArtifact(decode(case['artifact']))
        if operation == 'readHeader':
            return sessionFormatCatalog.readHeader(decode(case['header']))
        if operation == 'encodeCurrentHeader':
            return sessionFormatCatalog.encodeCurrentHeader(decode(case['header']), decode(case['cut']))
        if operation == 'encodeCurrentEvent':
            return sessionFormatCatalog.encodeCurrentEvent(decode(case['event']))
        reader = sessionFormatCatalog.createRestore(decode(case['header']), decode(case['options']))
        for row in case.get('rows', []):
            reader.decodeRow(decode(row))
        return reader.finish() if case.get('finish') else dict(header=reader.header)
    if case['kind'] == 'released-v3-logical':
        from dsh.session import format_v2_to_v3 as v3
        from dsh.session.format_v2_to_v3 import payload, references
        operation = case['operation']
        if operation in ('assertEvent', 'assertV3Event', 'assertV3StructuralRow', 'canonicalizeTransformedEvent', 'isRepairIdentity'):
            return getattr(payload, operation)(*decode(case['args']))
        if operation == 'remapEvent':
            return references.remapEvent(*decode(case['args']))
        if operation == 'header':
            return v3.assertReleasedV3Header(decode(case['header']))
        if operation == 'migrateHeader':
            return v3.sessionFormatV2ToV3['migrateHeader'](decode(case['header']))
        if operation == 'restore':
            return v3.restoreReleasedV3Artifact(decode(case['artifact']), set(case['known']))
        codec = v3.releasedV3SessionFormatCodec
        if operation in ('decodeHeader', 'encodeHeader', 'encodeEvent'):
            args = [decode(case['event'] if operation == 'encodeEvent' else case['header'])]
            if operation == 'encodeHeader':
                args.append(decode(case['cut']))
            return codec[operation](*args)
        collector = SessionFormatEventCollector()
        if operation == 'decoder':
            decoder = codec['createDecoder'](decode(case['header']), case['recovery'])
            for row in case['rows']:
                decoder.decodeRow(decode(row), collector)
            result = dict(header=decoder.header, events=collector.values)
            if case.get('finish'):
                result['cut'] = decoder.finish(collector)
            return result
        if operation == 'stage':
            stage = v3.sessionFormatV2ToV3['createStage'](decode(case['input']))
            result = dict(events=collector.values)
            for action in case['actions']:
                if action['method'] == 'finish':
                    result['cut'] = stage.finish(collector)
                elif action['method'] == 'transformEvent':
                    stage.transformEvent(decode(action['event']), collector)
                else:
                    stage.transformRun(dict(expand=lambda action=action: iter(decode(action['expanded']))), collector)
            return result
        raise ValueError('Unknown v3 operation: ' + operation)
    if case['kind'] == 'assistant-stream':
        from dsh.llm import assistant_stream as stream
        operation = case['operation']
        if operation in ('push', 'snapshot'):
            accumulator = stream.AssistantStreamAccumulator()
            result = None
            for timed in decode(case['timed']):
                result = accumulator.push(timed)
            return accumulator.snapshot() if operation == 'snapshot' else result
        if operation == 'assemble':
            assembler = stream.assembleAssistantStream(decode(case['stream']))
            result = dict(blocks=assembler.blocks(), interrupted=assembler.interruptedBlocks(), finish=assembler.finish)
            if assembler.usage is not UNDEFINED:
                result['usage'] = assembler.usage
            if assembler.replayState is not UNDEFINED:
                result['replayState'] = assembler.replayState
            return result
        result = getattr(stream, operation)(*decode(case['args']))
        return None if result is UNDEFINED else result
    if case['kind'] == 'released-v2-logical':
        from dsh.session.format_v0_to_v1 import releasedV0SessionFormatCodec, releasedV1SessionFormatCodec, sessionFormatV0ToV1
        from dsh.session.format_v1_to_v2 import releasedV2SessionFormatCodec, sessionFormatV1ToV2, assertReleasedV2Header, restoreReleasedV2Artifact
        from dsh.session.format_v1_to_v2.validation import assertReleasedV2WriterArtifact
        if case['operation'] == 'stage':
            stage = sessionFormatV1ToV2['createStage'](decode(case['input']))
            collector = SessionFormatEventCollector()
            result = dict(events=collector.values)
            for action in case['actions']:
                method = action['method']
                if method == 'finish':
                    result['cut'] = stage.finish(collector)
                elif method == 'transformEvent':
                    stage.transformEvent(decode(action['event']), collector)
                elif method == 'transformRun':
                    run = decode(action['run'])
                    run['expand'] = lambda action=action: iter(decode(action['expanded']))
                    stage.transformRun(run, collector)
                else:
                    raise ValueError('Unknown stage method: ' + method)
            return result
        artifact = decode(case['artifact'])
        if case['operation'] == 'writer':
            assertReleasedV2WriterArtifact(artifact)
            return None
        if case['operation'] == 'restore':
            return restoreReleasedV2Artifact(artifact, set(case['known']), case.get('relationshipVersion'))
        if case['operation'] != 'migrate':
            raise ValueError('Unknown v2 logical operation: ' + case['operation'])
        def restore(value):
            assertReleasedV2WriterArtifact(value)
            return value
        compiled = createSessionFormatCatalog(dict(currentVersion=2,
            codecs=[releasedV0SessionFormatCodec, releasedV1SessionFormatCodec, releasedV2SessionFormatCodec],
            currentEncoder=releasedV2SessionFormatCodec, migrations=[sessionFormatV0ToV1, sessionFormatV1ToV2],
            restoreCurrent=restore, restoreTransformedCurrent=restore,
            restoreCurrentHeader=lambda value: (assertReleasedV2Header(value), value)[1]))
        source = artifact['header']
        physical = dict(type='session', version=1, id=source['id'], createdAt=source['createdAt'],
            delegationDepth=source['delegationDepth'])
        physical.update({key:source[key] for key in ('cwd', 'parentSession', 'origin', 'agentPreset') if key in source})
        if source['isSeeded']:
            physical['seedLength'] = artifact['inheritedEventCount']
        current = compiled.createRestore(physical, dict(recovery='strict', validation='current'))
        for row in artifact['events']:
            current.decodeRow(row)
        return current.finish()
    if case['kind'] == 'released-logical':
        from dsh.session.format_v0_to_v1.payload import assertReleasedPayloadSemantics
        from dsh.session.format_v0_to_v1 import (assertReleasedEventPayload, assertReleasedArtifactRelationships,
            assertReleasedSurfaceMetadata, releasedV0SessionFormatCodec, releasedV1SessionFormatCodec,
            sessionFormatV0ToV1, assertReleasedV1Header)
        from dsh.session.format_v0_to_v1.validation import assertReleasedArtifactCoordinates, RELEASED_V0_EVENT_TYPES
        from dsh.session.format_v0_to_v1.codec import assertReleasedSessionFormatHeader
        operation = case['operation']
        if operation in ('semantics', 'payload'):
            validate = assertReleasedPayloadSemantics if operation == 'semantics' else assertReleasedEventPayload
            validate(decode(case['event']), case['version'])
        elif operation == 'relationships':
            assertReleasedArtifactRelationships(decode(case['artifact']), case.get('extensions'))
        elif operation == 'surface-metadata':
            assertReleasedSurfaceMetadata(decode(case['event']), case['event']['seq'], case['event']['type'], case.get('assistantSources', 'allow-empty-assistant'))
        elif operation == 'header':
            assertReleasedSessionFormatHeader(decode(case['header']), case['version'])
        elif operation == 'coordinates':
            assertReleasedArtifactCoordinates(decode(case['artifact']), case.get('allowLegacy', False),
                set(case['known']) if 'known' in case else None, case.get('neutral', False), case.get('frozen', False))
        elif operation in ('restore-v0', 'restore-v1'):
            def restore(artifact, legacy=False):
                assertReleasedV1Header(artifact['header'])
                assertReleasedArtifactCoordinates(artifact, False, RELEASED_V0_EVENT_TYPES, False, True)
                for event in artifact['events']:
                    if event['type'] in RELEASED_V0_EVENT_TYPES:
                        assertReleasedEventPayload(event, 1)
                assertReleasedArtifactRelationships(artifact, dict(legacyInterruptedTurnRestart=True) if legacy else {})
                return artifact
            config = dict(currentVersion=1, codecs=[releasedV0SessionFormatCodec, releasedV1SessionFormatCodec],
                currentEncoder=dict(encodeHeader=lambda value: value, encodeEvent=lambda value: value), migrations=[sessionFormatV0ToV1],
                restoreCurrent=restore, restoreTransformedCurrent=lambda value: restore(value, True),
                restoreCurrentHeader=lambda value: (assertReleasedV1Header(value), value)[1])
            current = createSessionFormatCatalog(config).createRestore(decode(case['header']),
                dict(recovery=case.get('recovery', 'strict'), validation='transformed' if operation == 'restore-v0' else 'current'))
            for row in case['rows']:
                current.decodeRow(decode(row))
            return current.finish()
        else:
            raise ValueError('Unknown released logical operation: ' + operation)
        return None
    kind = case['kind']
    if kind == 'released-codec':
        from dsh.session.format_v0_to_v1 import releasedV0SessionFormatCodec, releasedV1SessionFormatCodec
        from dsh.session.format_v1_to_v2 import releasedV2SessionFormatCodec
        codec = [releasedV0SessionFormatCodec, releasedV1SessionFormatCodec, releasedV2SessionFormatCodec][case['version']]
        source = decode(case['header'])
        if case.get('operation') == 'header':
            return codec['decodeHeader'](source)
        if case.get('operation') == 'encode':
            return dict(header=codec['encodeHeader'](source, case.get('cut', 0)),
                rows=[codec['encodeEvent'](decode(event)) for event in case.get('rows', [])])
        decoder = codec['createDecoder'](source, case.get('recovery', 'strict'))
        items, collector = [], SessionFormatEventCollector()
        class Context:
            def emitEvent(self, event):
                items.append(dict(event=event))
                collector.emitEvent(event)
            def emitRun(self, run):
                items.append(dict(run={key: value for key, value in run.items() if key != 'expand'}))
                collector.emitRun(run)
        context = Context()
        for row in case.get('rows', []):
            decoder.decodeRow(decode(row), context)
        return dict(header=decoder.header, earlyCut=getattr(decoder, 'headerInheritedEventCount', None),
            cut=decoder.finish(context), items=items, events=collector.values)
    if kind in ('count', 'safe'):
        return (sessionFormatCount if kind == 'count' else sessionFormatSafeInteger)(decode(case['value']), 'coordinate')
    if kind == 'filename':
        return parseSessionFormatLogFilename(case['value'])
    if kind == 'filename-write':
        return sessionFormatLogFilename(decode(case['value']))
    if kind == 'snapshot':
        value = decode(case['value'])
        if case.get('cycle'):
            value['self'] = value
        result = (snapshotSessionFormatHeader if case.get('header') else snapshotSessionFormatJson)(value)
        frozen = True
        if isinstance(result, dict):
            try:
                result['changed'] = True
                frozen = False
            except TypeError:
                pass
        return dict(value=result, frozen=frozen)
    observations = []
    if kind == 'chain':
        chain = createSessionFormatChain(options(case, observations))
        source = header(case.get('stored', 0))
        if case.get('headerOnly'):
            return chain.migrateHeader(source)
        collector = SessionFormatEventCollector()
        stream = chain.createStream(source, UNDEFINED if case.get('unknownCut') else case.get('cut', 0), collector)
        stream.emitEvent(dict(seq=0))
        stream.emitRun(dict(expand=lambda: iter([dict(seq=1), dict(seq=2)])))
        cut = stream.finish()
        return dict(header=stream.header, events=collector.values, cut=cut, stages=observations)
    if kind == 'catalog':
        current = catalog(case, observations)
        source = decode(case['header']) if 'header' in case else header(case.get('stored', 0))
        if case.get('operation') == 'read':
            return current.readHeader(source)
        if case.get('operation') == 'encode':
            return current.encodeCurrentHeader(source, case.get('cut', 0))
        restore = current.createRestore(source, dict(recovery='strict', validation=case.get('validation', 'transformed')))
        restore.decodeRow(dict(seq=0))
        restore.decodeRow([dict(seq=1), dict(seq=2)])
        return restore.finish()
    raise ValueError('Unknown scenario kind: ' + kind)


def observe(case):
    try:
        if case['kind'] == 'present-current':
            from scripts.oracles.present_current_python import execute as present_execute
            value = present_execute(case)
        elif case['kind'] == 'workspace-files-current':
            from scripts.oracles.workspace_files_current_python import execute as workspace_files_execute
            value = workspace_files_execute(case)
        elif case['kind'] == 'fs-range-current':
            from scripts.oracles.fs_range_current_python import execute as fs_range_execute
            value = fs_range_execute(case)
        elif case['kind'] == 'session-facade-current':
            from scripts.oracles.session_facade_current_python import execute as facade_execute
            value = facade_execute(case)
        elif case['kind'] == 'native-path-current':
            from scripts.oracles.native_path_current_python import execute as native_path_execute
            value = native_path_execute(case)
        elif case['kind'] == 'session-history-current':
            from scripts.oracles.session_history_current_python import execute as history_execute
            value = history_execute(case)
        elif case['kind'] == 'session-list-current':
            from scripts.oracles.session_list_current_python import execute as list_execute
            value = list_execute(case)
        elif case['kind'] == 'session-agents-current':
            from scripts.oracles.session_agents_current_python import execute as agents_execute
            value = agents_execute(case)
        elif case['kind'] == 'session-media-current':
            from scripts.oracles.session_media_current_python import execute as media_execute
            value = media_execute(case)
        elif case['kind'] == 'attachment-images-current':
            from scripts.oracles.attachment_images_current_python import execute as images_execute
            value = images_execute(case)
        elif case['kind'] == 'file-upload-current':
            from scripts.oracles.file_upload_current_python import execute as upload_execute
            value = upload_execute(case)
        elif case['kind'] == 'llm-files-current':
            from scripts.oracles.llm_files_current_python import execute as llm_files_execute
            value = llm_files_execute(case)
        elif case['kind'] == 'attachment-files-current':
            from scripts.oracles.attachment_files_current_python import execute as files_execute
            value = files_execute(case)
        elif case['kind'] == 'session-runtime':
            from scripts.oracles.session_runtime_python import execute as runtime_execute
            value = runtime_execute(case, decode)
        elif case['kind'] == 'query-current':
            from scripts.oracles.session_query_current_python import execute as query_execute
            value = query_execute(case, decode)
        elif case['kind'] == 'loop-current':
            from scripts.oracles.agent_loop_current_python import execute as loop_execute
            value = loop_execute(case, decode)
        elif case['kind'] == 'machine-current':
            from scripts.oracles.agent_machine_current_python import execute as machine_execute
            value = machine_execute(case, decode)
        elif case['kind'] == 'storage-backend':
            from scripts.oracles.session_backend_current_python import execute as backend_execute
            value = backend_execute(case, decode)
        elif case['kind'] in ('storage-contract','storage-handle'):
            from scripts.oracles.session_storage_current_python import execute as storage_execute
            value = storage_execute(case, decode)
        elif case['kind'] == 'generation':
            from scripts.oracles.session_generation_python import execute as generation_execute
            value = generation_execute(case)
        else:
            value = execute(case)
        return dict(case=case['case'], outcome='value', value=value)
    except Exception as error:
        result = dict(case=case['case'], outcome='error', name=getattr(error, 'name', 'TypeError' if isinstance(error, TypeError) else 'Error'), message=str(error))
        if hasattr(error, 'cause'):
            result['cause'] = str(error.cause)
        return result


if __name__ == '__main__':
    corpus = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    with Path(sys.argv[2]).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump([observe(case) for case in corpus], stream, ensure_ascii=True, indent=2)
        stream.write('\n')

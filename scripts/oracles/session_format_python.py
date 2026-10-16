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
        return dict(case=case['case'], outcome='value', value=execute(case))
    except Exception as error:
        result = dict(case=case['case'], outcome='error', name=getattr(error, 'name', 'Error'), message=str(error))
        if hasattr(error, 'cause'):
            result['cause'] = str(error.cause)
        return result


if __name__ == '__main__':
    corpus = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    with Path(sys.argv[2]).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump([observe(case) for case in corpus], stream, ensure_ascii=True, indent=2)
        stream.write('\n')

"""Pure, streaming adjacent Session migration planner. No I/O or runtime pin."""
import json

from dsh.core.session.json import UNDEFINED, FrozenDict
from dsh.cordis.utils import js_to_string
from .error import SessionFormatError, SessionFormatUnsupportedMigrationError
from .json import snapshotSessionFormatHeader, sessionFormatCount, sessionFormatVersion


def member(value, name, default=UNDEFINED):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def call(value, name, *args):
    return member(value, name)(*args)


def refusal(migration, error, subject='Session'):
    if isinstance(error, SessionFormatUnsupportedMigrationError):
        raise error
    detail = str(error)
    wrapped = SessionFormatUnsupportedMigrationError('%s refuses this format v%s %s: %s' % (
        member(migration, 'name'), js_to_string(member(migration, 'fromVersion')), subject, detail))
    wrapped.cause = error
    raise wrapped from error


def defineSessionFormatMigration(migration):
    name = member(migration, 'name')
    if not isinstance(name, str) or not name:
        raise SessionFormatError('Session migration name must be a non-empty string')
    first = sessionFormatVersion(member(migration, 'fromVersion'), name + ' fromVersion')
    last = sessionFormatVersion(member(migration, 'toVersion'), name + ' toVersion')
    if last != first + 1:
        raise SessionFormatError('%s must declare adjacent v%s->v%s' % (name, js_to_string(first), js_to_string(first + 1)))
    return FrozenDict(migration if isinstance(migration, dict) else {key: member(migration, key) for key in (
        'name', 'fromVersion', 'toVersion', 'migrateHeader', 'createStage', 'validateTargetHeader')})


class SessionFormatEventCollector:
    def __init__(self):
        self.values = []

    def emitEvent(self, event):
        self.values.append(event)

    def emitRun(self, run):
        self.values.extend(call(run, 'expand'))


class CompiledSessionFormatChain:
    def __init__(self, options):
        self.currentVersion = sessionFormatVersion(member(options, 'currentVersion'), 'current Session format version')
        self._restoreCurrentHeader = member(options, 'restoreCurrentHeader')
        by_from, names = {}, set()
        for candidate in member(options, 'migrations'):
            migration = defineSessionFormatMigration(candidate)
            first, last, name = migration['fromVersion'], migration['toVersion'], migration['name']
            if first in by_from:
                raise SessionFormatError('Session migration v%s->v%s is duplicated' % (js_to_string(first), js_to_string(last)))
            if name in names:
                raise SessionFormatError('Session migration name %s is duplicated' % json.dumps(name, ensure_ascii=False))
            by_from[first] = migration
            names.add(name)
        ordered = []
        for version in range(int(self.currentVersion)):
            if version not in by_from:
                raise SessionFormatUnsupportedMigrationError('Session migration v%s->v%s is missing' % (version, version + 1))
            ordered.append(by_from[version])
        if len(by_from) != len(ordered):
            invalid = next(version for version in by_from if version >= self.currentVersion)
            raise SessionFormatError('Session migration from v%s does not lead to current v%s' % (js_to_string(invalid), js_to_string(self.currentVersion)))
        self._migrations = tuple(ordered)

    def _plan(self, version):
        first = sessionFormatVersion(version, 'stored Session format version')
        if first > self.currentVersion:
            raise SessionFormatUnsupportedMigrationError('stored Session uses newer format v%s; this build writes v%s' % (
                js_to_string(first), js_to_string(self.currentVersion)))
        return self._migrations[int(first):]

    def _advanceHeader(self, migration, source):
        name = migration['name']
        try:
            target = call(migration, 'migrateHeader', snapshotSessionFormatHeader(source, name + ' header input'))
        except Exception as error:
            refusal(migration, error, 'Session header')
        current = snapshotSessionFormatHeader(target, name + ' header output')
        if current['version'] != migration['toVersion']:
            raise SessionFormatError('%s header returned v%s; expected v%s' % (
                name, js_to_string(current['version']), js_to_string(migration['toVersion'])))
        try:
            call(migration, 'validateTargetHeader', current)
        except Exception as error:
            refusal(migration, error, 'Session header')
        return current

    def migrateHeader(self, source):
        current = snapshotSessionFormatHeader(source, 'stored Session header')
        for migration in self._plan(current['version']):
            current = self._advanceHeader(migration, current)
        current = snapshotSessionFormatHeader(self._restoreCurrentHeader(current), 'current Session header restoration')
        if current['version'] != self.currentVersion:
            raise SessionFormatError('current Session header restorer returned v%s; expected v%s' % (
                js_to_string(current['version']), js_to_string(self.currentVersion)))
        return current

    def createStream(self, sourceHeader, sourceCut, output):
        header = sourceHeader
        validated = UNDEFINED if sourceCut is UNDEFINED else sessionFormatCount(sourceCut, 'Session inherited event count')
        cut, stages = validated, []
        for index, migration in enumerate(self._plan(header['version'])):
            target = self._advanceHeader(migration, header)
            try:
                stage = call(migration, 'createStage', dict(sourceHeader=header, targetHeader=target,
                    sourceInheritedEventCount=cut, sourceKind='decoded' if index == 0 else 'transformed'))
            except Exception as error:
                refusal(migration, error)
            header = target
            stages.append((migration, stage))
            cut = member(stage, 'headerInheritedEventCount')
        return CompiledSessionFormatMigrationStream(header, validated, stages, output)


class ChainedMigrationContext:
    def __init__(self, migration, stage, output):
        self.migration, self.stage, self.output = migration, stage, output

    def emitEvent(self, event):
        try:
            call(self.stage, 'transformEvent', event, self.output)
        except Exception as error:
            refusal(self.migration, error)

    def emitRun(self, run):
        try:
            call(self.stage, 'transformRun', run, self.output)
        except Exception as error:
            refusal(self.migration, error)

    def finish(self):
        try:
            cut = call(self.stage, 'finish', self.output)
        except Exception as error:
            refusal(self.migration, error)
        declared = member(self.stage, 'headerInheritedEventCount')
        if declared is not UNDEFINED and declared != cut:
            raise SessionFormatError(self.migration['name'] + ' changed its predeclared inherited cut')
        return cut


class CompiledSessionFormatMigrationStream:
    def __init__(self, header, sourceCut, entries, output):
        self.header, self._sourceCut = header, sourceCut
        stages, downstream = [], output
        for migration, stage in reversed(entries):
            downstream = ChainedMigrationContext(migration, stage, downstream)
            stages.append(downstream)
        self._stages = tuple(reversed(stages))
        self._input = downstream

    def emitEvent(self, event):
        call(self._input, 'emitEvent', event)

    def emitRun(self, run):
        call(self._input, 'emitRun', run)

    def finish(self):
        cut = self._sourceCut
        for stage in self._stages:
            cut = stage.finish()
        return sessionFormatCount(cut, 'finished Session inherited event count')


def createSessionFormatChain(options):
    return CompiledSessionFormatChain(options)

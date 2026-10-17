"""Current workspace instructions: provider probes and durable step projection."""
import asyncio
import inspect
import json
import math
import os
import weakref
from types import SimpleNamespace

from dsh.cordis.environment import resolve_dsh_home, dsh_home_display
from dsh.cordis.plugin import Plugin
from dsh.cordis.schema import Schema
from dsh.cordis.json_text import stringify_json
from dsh.core.abort import AbortController
from dsh.llm.message import create_user_message
from dsh.session.preparations import throw_aborted
from dsh.context.agent_instructions.config import workspace_baseline_identity
from dsh.context.agent_instructions.digest import instruction_content_sha1, trimmed_instruction_digest
from dsh.context.agent_instructions.files import ancestor_chain, descendant_dirs_between, dedup_instruction_files_by_directory
from dsh.context.agent_instructions.render import (
    USER_GLOBAL_DIRECTORY, candidate_scope_key, decode_scope_key, instruction_scope_key,
    render_workspace_instruction_set, render_instruction_changes)


def field(value, key, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def config_of(value):
    def candidates(key, fallback):
        values = value.get(key)
        return [name for name in (fallback if values is None else values)
                if name not in ('', '.', '..') and '/' not in name and '\\' not in name]
    return SimpleNamespace(dsh_home=resolve_dsh_home(value.get('dshHome')),
        project_root_markers=value.get('projectRootMarkers', ['.git']), max_bytes=value['maxBytes'],
        max_source_bytes=value.get('maxSourceBytes', 1048576),
        instruction_file_candidates=candidates('instructionFileCandidates', ['AGENTS.md', 'CLAUDE.md']),
        local_instruction_file_candidates=candidates('localInstructionFileCandidates', ['AGENTS.local.md', 'CLAUDE.local.md']))


async def find_project_root(cwd, markers, fs, signal=None):
    current = os.path.abspath(cwd)
    while True:
        for marker in markers:
            try:
                throw_aborted(signal)
                target = await fs.resolve(os.path.join(current, marker), dict(signal=signal))
                if await fs.stat(target, signal) is not None:
                    return current
            except Exception as error:
                throw_aborted(signal)
                if getattr(error, 'code', None) != 'FS_NOT_FOUND':
                    raise
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.abspath(cwd)
        current = parent


async def probe_file(path, display, fs, signal):
    try:
        target = await fs.resolve(path, dict(signal=signal))
        throw_aborted(signal)
        info = await fs.stat(target, signal)
        throw_aborted(signal)
        if field(info, 'type') != 'file':
            return dict(kind='absent')
        return dict(kind='present', file=dict(absolutePath=path, displayPath=display, target=target,
                    version=field(info, 'version'), size=field(info, 'size')))
    except Exception:
        throw_aborted(signal)
        return dict(kind='unavailable')


async def read_file(file, maximum, fs, signal):
    throw_aborted(signal)
    if file.get('size') is not None and file['size'] > maximum:
        return None
    try:
        source = fs.streamText(file['target'], signal)
        if inspect.isawaitable(source):
            source = await source
        parts, size = [], 0
        try:
            async for chunk in source:
                throw_aborted(signal)
                size += len(chunk.encode('utf-8', 'replace'))
                if size > maximum:
                    return None
                parts.append(chunk)
        finally:
            close = getattr(source, 'aclose', None)
            if close is not None:
                await close()
        throw_aborted(signal)
        return dict(absolutePath=file['absolutePath'], displayPath=file['displayPath'],
                    version=file['version'], content=''.join(parts))
    except Exception:
        throw_aborted(signal)
        return None


def display_path(root, path):
    value = os.path.relpath(path, root)
    return '' if value == '.' else value


async def baseline_files(config, cwd, root, fs, signal, replace=False):
    home_file = os.path.join(config.dsh_home, 'AGENTS.md')
    paths = {home_file: dsh_home_display(config.dsh_home) + '/AGENTS.md'}
    for directory in ancestor_chain(root, cwd):
        for candidate in config.instruction_file_candidates + config.local_instruction_file_candidates:
            path = os.path.join(directory, candidate)
            paths[path] = display_path(root, path)
    loaded = []
    for path, display in paths.items():
        probe = await probe_file(path, display, fs, signal)
        if probe['kind'] == 'present':
            file = await read_file(probe['file'], config.max_source_bytes, fs, signal)
            if file is not None:
                loaded.append(file)
    deduped = dedup_instruction_files_by_directory(loaded)
    if not deduped and not replace:
        return None
    rendered = render_workspace_instruction_set(deduped, dict(maxBytes=config.max_bytes, replacePreviousBaseline=replace))
    return dict(rendered=rendered['rendered'], observed=loaded if deduped else [], included=rendered['included'])


def baseline_state(files):
    changes, versions = {}, {}
    for file in files:
        scope, digest = instruction_scope_key(file['displayPath']), instruction_content_sha1(file['content'])
        changes[scope] = dict(action='set', scope=scope, path=file['displayPath'], digest=digest)
        if file.get('version') is not None:
            versions[scope] = dict(path=file['displayPath'], version=file['version'], digest=digest,
                                   trimmedDigest=trimmed_instruction_digest(file['content']))
    return changes, versions


def visible_messages(agent):
    result = []
    for seq in agent.session.surface.nodes:
        event = agent.session.eventAt(seq)
        if isinstance(event, dict) and event['type'] == 'user/message':
            result.append(event['data'])
    return result


def changes_of(message):
    source = message.get('source', {})
    if source.get('kind') != 'agent-instructions' or not isinstance(source.get('changes'), list):
        return []
    result = []
    for change in source['changes']:
        if (isinstance(change, dict) and change.get('action') in ('set', 'replace', 'remove')
                and isinstance(change.get('scope'), str) and isinstance(change.get('path'), str)
                and ('digest' not in change or isinstance(change['digest'], str))):
            result.append({key: change[key] for key in ('action', 'scope', 'path', 'digest') if key in change})
    return result


async def reconcile(agent, config, cache, fs, authority, pending, touched, include_baseline, excluded, root, signal):
    effective = {}
    for message in visible_messages(agent) + list(authority):
        for change in changes_of(message):
            effective[change['scope']] = change
    cwd = agent.session.header.cwd or os.getcwd()
    baseline, scopes = {}, {}
    def add_dir(target, directory):
        for candidate in config.instruction_file_candidates + config.local_instruction_file_candidates:
            target[candidate_scope_key(directory, candidate)] = None
    baseline[candidate_scope_key(USER_GLOBAL_DIRECTORY, 'AGENTS.md')] = None
    for directory in ancestor_chain(root, cwd):
        add_dir(baseline, display_path(root, directory) or '.')
    if include_baseline:
        scopes.update(baseline)
    for message in pending:
        for change in changes_of(message):
            if include_baseline or change['scope'] not in baseline:
                scopes[change['scope']] = None
    for scope in effective:
        if not include_baseline and scope in baseline:
            continue
        directory = decode_scope_key(scope)['directory']
        if directory == USER_GLOBAL_DIRECTORY:
            scopes[candidate_scope_key(directory, 'AGENTS.md')] = None
        else:
            add_dir(scopes, directory)
    for path in touched:
        for directory in descendant_dirs_between(cwd, path):
            add_dir(scopes, display_path(root, directory) or '.')
    versions = cache.setdefault(agent.session, {})
    items, updates, seen = [], [], set()
    def removal(scope, path):
        change = dict(action='remove', scope=scope, path=path)
        items.append(dict(change=change, file=dict(absolutePath='removed:' + scope, displayPath=path, content='')))
        updates.append(dict(change=change))
    directories = {}
    for scope in scopes:
        directories.setdefault(decode_scope_key(scope)['directory'], []).append(scope)
    for directory, group in directories.items():
        probes = []
        for scope in group:
            previous = effective.get(scope)
            if excluded is not None and scope in baseline and scope in excluded:
                if previous is None or previous['action'] == 'remove':
                    versions.pop(scope, None)
                else:
                    removal(scope, previous['path'])
            else:
                probes.append(scope)
        item_start, update_start, added = len(items), len(updates), []
        prior = {scope: versions.get(scope) for scope in probes}
        kept = set()
        for scope in probes:
            previous = effective.get(scope)
            parts = decode_scope_key(scope)
            folder = config.dsh_home if directory == USER_GLOBAL_DIRECTORY else os.path.join(root, directory)
            path = os.path.normpath(os.path.join(folder, parts['candidateName']))
            display = dsh_home_display(config.dsh_home) + '/AGENTS.md' if directory == USER_GLOBAL_DIRECTORY else display_path(root, path)
            probe = await probe_file(path, display, fs, signal)
            if probe['kind'] == 'unavailable':
                if previous is None or previous['action'] == 'remove':
                    continue
                del items[item_start:]
                del updates[update_start:]
                for key, state in prior.items():
                    if state is None:
                        versions.pop(key, None)
                    else:
                        versions[key] = state
                seen.difference_update(added)
                break
            if probe['kind'] == 'absent':
                if previous is None or previous['action'] == 'remove':
                    versions.pop(scope, None)
                else:
                    removal(scope, previous['path'])
                continue
            file = probe['file']
            if file['absolutePath'] in seen:
                continue
            seen.add(file['absolutePath'])
            added.append(file['absolutePath'])
            cached = versions.get(scope)
            if (cached is not None and cached['path'] == display and cached['version'] == file['version']
                    and previous is not None and previous['action'] != 'remove'
                    and previous['path'] == cached['path'] and previous.get('digest') == cached['digest']):
                if cached['trimmedDigest'] in kept:
                    removal(scope, previous['path'])
                kept.add(cached['trimmedDigest'])
                continue
            loaded = await read_file(file, config.max_source_bytes, fs, signal)
            if loaded is None:
                continue
            digest, trimmed = instruction_content_sha1(loaded['content']), trimmed_instruction_digest(loaded['content'])
            if trimmed in kept:
                if previous is not None and previous['action'] != 'remove':
                    removal(scope, previous['path'])
                else:
                    versions.pop(scope, None)
                continue
            kept.add(trimmed)
            state = dict(path=display, version=file['version'], digest=digest, trimmedDigest=trimmed)
            if previous is not None and previous['action'] != 'remove' and previous['path'] == display and previous.get('digest') == digest:
                versions[scope] = state
                continue
            change = dict(action='set' if previous is None or previous['action'] == 'remove' else 'replace', scope=scope, path=display, digest=digest)
            items.append(dict(change=change, file=loaded))
            updates.append(dict(change=change, state=state))
    if not items:
        return None
    rendered = render_instruction_changes(items, config.max_bytes)
    if not rendered['text'] or not rendered['changes']:
        return None
    return dict(context=create_user_message(dict(content=[dict(type='text', text=rendered['text'])],
        source=dict(kind='agent-instructions', form='instructions', changes=rendered['changes']))),
        updates=[update for update in updates if update['change'] in rendered['changes']])


def same_payload(left, right):
    return left.get('content') == right.get('content') and left.get('source') == right.get('source')


def workspace_context(message):
    return message.get('source', {}).get('kind') == 'agent-instructions'


class CurrentInstructionRuntime:
    def __init__(self, ctx, config):
        self.ctx, self.config = ctx, config_of(config)
        self.versions, self.prepared = weakref.WeakKeyDictionary(), weakref.WeakKeyDictionary()
        self.tails, self.steps = weakref.WeakKeyDictionary(), weakref.WeakKeyDictionary()
        self.executions, self.lifecycle = {}, AbortController()
        ctx.on('agent/pre-step', self.pre_step)
        ctx.on('tools/result', self.tool_result)
        ctx.on('session/event', self.session_event)
        def close():
            self.lifecycle.abort(RuntimeError('agent-instructions disposed'))
            self.executions.clear()
        ctx.effect(lambda: close, 'agent-instructions.projectionLifecycle')

    async def compose(self, agent, signal, claimed, pending, touched=()):
        throw_aborted(signal)
        config, fs = self.config, self.ctx.get('fs')
        if config.max_bytes <= 0 or not math.isfinite(config.max_bytes) or fs is None:
            return None
        if not touched and pending:
            return pending[0]
        cwd = agent.session.header.cwd or os.getcwd()
        root = await find_project_root(cwd, config.project_root_markers, fs, signal)
        identity = stringify_json(json.loads(workspace_baseline_identity(config, cwd, root)))
        visible = next((message['source'] for message in reversed(visible_messages(agent) + list(claimed))
                        if workspace_context(message) and message['source'].get('baseline') is True), None)
        keep = visible is not None and visible.get('baselineIdentity') == identity
        prepared = self.prepared.get(agent.session)
        excluded = prepared['excluded'] if keep and prepared is not None and prepared['identity'] == identity else None
        content, changes, authority, desired_baseline, preparation = [], [], list(claimed), False, None
        if visible is None or not keep or excluded is None:
            instructions = await baseline_files(config, cwd, root, fs, signal, visible is not None and not keep)
            included, versions = baseline_state(instructions['included'] if instructions else [])
            observed, _ = baseline_state(instructions['observed'] if instructions else [])
            excluded = set(observed).difference(included)
            preparation = dict(identity=identity, excluded=excluded)
            if versions:
                self.versions.setdefault(agent.session, {}).update(versions)
            if not keep and instructions is not None and instructions['rendered']['text']:
                baseline_content = [dict(type='text', text=instructions['rendered']['text'])]
                content.extend(baseline_content)
                removals = ([dict(action='remove', scope=change['scope'], path=change['path'])
                             for change in visible['changes'] if change['action'] != 'remove' and change['scope'] not in included]
                            if visible is not None and not keep else [])
                baseline_changes = removals + list(included.values())
                changes.extend(baseline_changes)
                authority.append(create_user_message(dict(content=baseline_content, source=dict(kind='agent-instructions',
                    form='instructions', baseline=True, baselineIdentity=identity, changes=baseline_changes))))
                desired_baseline = True
        update = await reconcile(agent, config, self.versions, fs, authority, pending, touched, keep,
                                 excluded if keep else None, root, signal)
        if update is not None:
            content.extend(update['context']['content'])
            changes.extend(update['context']['source']['changes'])
            states = self.versions.setdefault(agent.session, {})
            for item in update['updates']:
                if 'state' in item:
                    states[item['change']['scope']] = item['state']
                else:
                    states.pop(item['change']['scope'], None)
            if not states:
                self.versions.pop(agent.session, None)
        if preparation is not None:
            self.prepared[agent.session] = preparation
        if not content:
            return None
        source = dict(kind='agent-instructions', form='instructions', changes=changes)
        if desired_baseline:
            source.update(baseline=True, baselineIdentity=identity)
        return create_user_message(dict(content=content, source=source))

    def sync_inbox(self, agent, claimed, desired):
        pending = [message for message in agent.inbox.nextStep if workspace_context(message)]
        supplied = desired is not None and any(same_payload(message, desired) for message in list(claimed) + visible_messages(agent))
        if desired is None or supplied:
            for message in pending:
                agent.inbox.remove(message['id'])
            return
        reusable = next((message for message in pending if same_payload(message, desired)), None)
        if reusable is not None:
            for message in pending:
                if message is not reusable:
                    agent.inbox.remove(message['id'])
            return
        if pending:
            agent.inbox.replace(pending[0]['id'], desired)
        else:
            agent.inbox.prepend('next-step', desired)
        for message in pending[1:]:
            agent.inbox.remove(message['id'])

    def queue_projection(self, agent, path):
        previous = self.tails.get(agent)
        async def run():
            try:
                if previous is not None:
                    await previous
                pending = [message for message in agent.inbox.nextStep if workspace_context(message)]
                desired = await self.compose(agent, self.lifecycle.signal, [], pending, [path])
                throw_aborted(self.lifecycle.signal)
                self.sync_inbox(agent, [], desired)
            except Exception as error:
                if not self.lifecycle.signal.aborted:
                    self.ctx.logger.warn('workspace instruction refresh failed: %s', error)
        task = asyncio.create_task(run())
        self.tails[agent] = task
        def settled(_):
            if self.tails.get(agent) is task:
                self.tails.pop(agent, None)
        task.add_done_callback(settled)

    def project_touch(self, agent, path):
        boundary = self.ctx.get('sessionProjections').stateOf(agent.session, 'turnBoundary')
        if boundary is None:
            raise RuntimeError('agent-instructions requires the turnBoundary session projection')
        step = boundary.get('lastStepBoundary')
        if (boundary['openTurnStartSeq'] is not None and step is not None and step['kind'] == 'start'
                and step['seq'] > boundary['openTurnStartSeq']):
            self.steps.setdefault(agent.session, []).append((agent, path))
        else:
            self.queue_projection(agent, path)

    def tool_result(self, execution, result):
        touches = self.executions.pop(field(execution, 'token'), [])
        agent, signal, arguments = field(execution, 'agent'), field(execution, 'signal'), field(execution, 'arguments')
        if not field(result, 'isError', False) and agent is not None and not field(signal, 'aborted', False):
            if field(execution, 'name') in ('read', 'write', 'edit', 'str_replace_editor') and isinstance(arguments, dict):
                # The editor is the explicitly retained Win7 Minimal tool.
                path = arguments.get('file_path') or (arguments.get('path') if field(execution, 'name') == 'str_replace_editor' else None)
                if isinstance(path, str) and path.strip():
                    touches.append((agent, path.strip()))
        parent = field(execution, 'parent')
        if parent is not None:
            if touches:
                self.executions.setdefault(parent, []).extend(touches)
            return
        for agent, path in touches:
            self.project_touch(agent, path)

    def session_event(self, session, event):
        if event['type'] == 'step/end':
            for agent, path in self.steps.pop(session, []):
                self.queue_projection(agent, path)

    async def pre_step(self, payload, next_fn):
        decision = await next_fn()
        agent, claimed, signal = payload['agent'], payload['messages'], payload['signal']
        while self.tails.get(agent) is not None:
            await self.tails[agent]
            # Task done callbacks remove only their own tail.
            await asyncio.sleep(0)
        pending = [message for message in agent.inbox.nextStep if workspace_context(message)]
        desired = await self.compose(agent, signal, claimed, pending)
        throw_aborted(signal)
        if decision['kind'] == 'reject' or (payload['step'] == 1 and not decision['messages']):
            self.sync_inbox(agent, claimed, desired)
            return decision
        for message in pending:
            agent.inbox.remove(message['id'])
        if desired is None or any(same_payload(message, desired) for message in decision['messages']):
            return decision
        messages = list(decision['messages'])
        position = max((index for index, message in enumerate(messages) if any(message is item for item in claimed)), default=-1) + 1
        messages.insert(position, desired)
        return dict(decision, messages=messages)


class CurrentAgentInstructionsPlugin(Plugin):
    id = 'agent-instructions'
    inject = ['sessionProjections']
    Config = Schema.object({
        'dshHome': Schema.string(),
        'projectRootMarkers': Schema.array(Schema.string()).default(['.git']),
        'maxBytes': Schema.number().required(),
        'maxSourceBytes': Schema.number().step(1).min(1).default(1048576),
        'instructionFileCandidates': Schema.array(Schema.string()).default(['AGENTS.md', 'CLAUDE.md']),
        'localInstructionFileCandidates': Schema.array(Schema.string()).default(['AGENTS.local.md', 'CLAUDE.local.md']),
    })

    def apply(self, ctx):
        CurrentInstructionRuntime(ctx, self.config)

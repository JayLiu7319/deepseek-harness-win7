"""Observe the mounted instruction plugin against a deterministic provider."""
import asyncio
import copy
import os
from types import SimpleNamespace

from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.context.instructions_current import CurrentAgentInstructionsPlugin


def execute(test):
    async def run():
        ctx, trace, results = Context(), [], []
        root = os.path.abspath('C:/instruction-probe')
        def path(name):
            return os.path.join(root, name.replace('/', os.sep))
        files = {path(name): copy.deepcopy(value) for name, value in test.get('files', {}).items()}
        controller = AbortController()
        class Fs:
            async def resolve(self, name, options):
                controller.signal.throwIfAborted()
                value = files.get(name, {})
                if value.get('resolveError'):
                    error = RuntimeError(value['resolveError'])
                    error.code = value.get('code', 'FS_DENIED')
                    raise error
                return name
            async def stat(self, target, signal):
                signal.throwIfAborted()
                value = files.get(target)
                if value is None:
                    return None
                if value.get('statError'):
                    error = RuntimeError(value['statError'])
                    error.code = value.get('code', 'FS_DENIED')
                    raise error
                info = dict(type=value.get('type', 'file'), version=value.get('version', value.get('content', '')))
                if 'content' in value and not value.get('omitSize'):
                    info['size'] = len(value['content'].encode('utf-8'))
                return info
            async def streamText(self, target, signal):
                trace.append(os.path.relpath(target, root))
                value = files.get(target, {})
                if value.get('readError'):
                    raise RuntimeError(value['readError'])
                for chunk in value.get('chunks', [value.get('content', '')]):
                    signal.throwIfAborted()
                    yield chunk
        class Session:
            def __init__(self):
                self.header = SimpleNamespace(cwd=path(test.get('cwd', 'project')))
                self.surface = SimpleNamespace(nodes=[])
                self.events = []
            def eventAt(self, seq):
                return self.events[seq]
        class Inbox:
            def __init__(self): self.nextStep = []
            def remove(self, identity): self.nextStep[:] = [item for item in self.nextStep if item['id'] != identity]
            def prepend(self, _, message): self.nextStep.insert(0, message)
            def replace(self, identity, message):
                self.nextStep[:] = [message if item['id'] == identity else item for item in self.nextStep]
        class Agent: pass
        agent = Agent()
        agent.session, agent.inbox = Session(), Inbox()
        boundary = dict(openTurnStartSeq=None, lastStepBoundary=None)
        ctx.set_service('fs', Fs())
        ctx.set_service('sessionProjections', SimpleNamespace(stateOf=lambda *_: boundary))
        def normalize(value):
            if isinstance(value, dict): return {key: normalize(item) for key, item in value.items() if key != 'id'}
            if isinstance(value, (list, tuple)): return [normalize(item) for item in value]
            return value
        fiber = await ctx.plugin(CurrentAgentInstructionsPlugin, dict(dict(maxBytes=65536,
            dshHome=path('home')), **test.get('config', {})))
        try:
            for action in test.get('actions', [dict(op='step')]):
                op = action['op']
                if op == 'files':
                    for name, value in action['values'].items():
                        if value is None: files.pop(path(name), None)
                        else: files[path(name)] = copy.deepcopy(value)
                elif op == 'touch':
                    execution = SimpleNamespace(token=action.get('token', 'exec'), parent=action.get('parent'),
                        agent=agent, signal=controller.signal, name=action.get('name', 'read'),
                        arguments=dict(file_path=path(action.get('path', 'project/sub/file.txt'))))
                    ctx.emit('tools/result', execution, dict(isError=action.get('error', False)))
                elif op == 'step-open':
                    boundary.update(openTurnStartSeq=0, lastStepBoundary=dict(kind='start', seq=1))
                elif op == 'step-end':
                    boundary.update(lastStepBoundary=dict(kind='end', seq=2))
                    ctx.emit('session/event', agent.session, dict(type='step/end'))
                elif op == 'dispose':
                    await fiber.dispose()
                else:
                    claimed = [] if action.get('empty') else [dict(id='input', role='user', source=dict(kind='user'), content=[dict(type='text', text='task')])]
                    async def terminal(): return dict(kind='reject' if action.get('reject') else 'proceed', messages=claimed)
                    try:
                        decision = await ctx.waterfall('agent/pre-step', dict(agent=agent, messages=claimed,
                            step=action.get('step', 1), signal=controller.signal), terminal)
                        if action.get('commit', True) and decision['kind'] != 'reject':
                            for message in decision['messages']:
                                agent.session.surface.nodes.append(len(agent.session.events))
                                agent.session.events.append(dict(type='user/message', data=message))
                        results.append(dict(decision=normalize(decision), pending=normalize(agent.inbox.nextStep), reads=list(trace)))
                    except Exception as error:
                        results.append(dict(error=str(error), pending=normalize(agent.inbox.nextStep), reads=list(trace)))
            return results
        finally:
            await ctx.fiber.dispose()
    return asyncio.run(run())

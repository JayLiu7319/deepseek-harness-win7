"""Observe the mounted reference resolver, never mirror retention."""
import asyncio
import copy
from types import SimpleNamespace
from dsh.cordis.context import Context
from dsh.context.session_reference_current import CurrentSessionReferenceResolver
from dsh.core.abort import AbortController
from dsh.llm.llm_service import LlmError


def execute(test):
    async def run():
        ctx, saves, lookups, reads = Context(), [], [], []
        controller, snapshots = AbortController(), {}
        for item in test.get('sources', [dict(id='source', texts=['hello', 'answer'])]):
            events = []
            for index, value in enumerate(item.get('texts', [])):
                text = value if isinstance(value, str) else value['text'] * value.get('repeat', 1)
                content = [dict(type='text', text=text)]
                if index % 2 == 0:
                    data, kind = dict(source=dict(kind='user'), content=content), 'user/message'
                else:
                    data, kind = dict(message=dict(content=content)), 'assistant/message'
                events.append(dict(type=kind, data=data))
            snapshots[item['id']] = dict(session=dict(id=item['id'], cwd=item.get('cwd'), version=item.get('version', 3)),
                                          capturedThroughSeq=len(events) - 1 if events else None, events=events)
        class Query:
            async def readSurface(self, sid):
                reads.append(sid)
                if test.get('readError'): raise RuntimeError('read failed')
                return copy.deepcopy(snapshots[sid])
        class Llm:
            async def resolveModelInfo(self, provider, model, signal):
                lookups.append(dict(provider=provider, model=model))
                if test.get('modelError'):
                    if test['modelError'] == 'ordinary': raise RuntimeError('metadata failed')
                    raise LlmError('metadata failed', test['modelError'])
                return copy.deepcopy(test.get('modelInfo', {}))
        class Spill:
            async def saveText(self, request):
                saves.append(copy.deepcopy(request))
                if test.get('spillError'): raise RuntimeError('disk full')
                if test.get('abortOnSave'): controller.abort('cancelled')
                return dict(locator='spill://snapshot', bytes=len(request['content'].encode('utf-8')), retrievalHint='Read snapshot')
        ctx.set_service('sessionQuery', Query())
        if not test.get('noLlm'): ctx.set_service('llm', Llm())
        if test.get('spill'): ctx.set_service('spillStore', Spill())
        class Agent: pass
        agent = Agent()
        agent.id, agent.session = 'target', SimpleNamespace(id='target')
        agent.options = test.get('options', dict(provider='provider', model='model'))
        def normalize(value):
            if isinstance(value, dict): return {key: normalize(item) for key,item in value.items() if key != 'id'}
            if isinstance(value, (list, tuple)): return [normalize(item) for item in value]
            return value
        try:
            await ctx.plugin(CurrentSessionReferenceResolver, test.get('config', {}))
            service = ctx.get('sessionReferenceResolver')
            if 'assembled' in test:
                assembly=dict(variables=test['assembled'])
                await ctx.waterfall('system-prompt/assemble', assembly, dict(agent=agent), lambda: assembly)
            if test.get('abortBefore'): controller.abort('cancelled')
            try:
                result = await service.prepare(agent, [dict(type='text', text='accepted')],
                    test.get('references', [dict(sessionId=sid) for sid in snapshots]), controller.signal)
                result = dict(result=normalize(result))
            except Exception as error:
                result = dict(error=dict(message=getattr(error,'message',str(error)), **(dict(code=error.code) if hasattr(error,'code') else {})))
            return dict(result, saves=saves, lookups=lookups, reads=reads)
        finally:
            await ctx.fiber.dispose()
    return asyncio.run(run())

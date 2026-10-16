"""Actual transient file projection through current LLM dispatch boundaries."""
import asyncio
import copy
from types import SimpleNamespace

from dsh.cordis.context import Context
from dsh.core.session.json import FrozenDict, deep_freeze
from dsh.llm.file_content_current import file_handle_text, project_files_to_text
from dsh.llm.runtime_current import CurrentLLMService


async def run(case):
    if case['operation'] == 'pure':
        messages = case['messages']
        projected = project_files_to_text(messages, lambda ref: case.get('path'))
        return dict(messages=projected, same=projected is messages,
            rows=[dict(message=a is b, content=a['content'] is b['content']) for a, b in zip(messages, projected)])
    ctx = Context()
    current = {}
    requests, mappings, hooks, handles, chunks = [], [], [], [], []
    try:
        def host_path(ref):
            if current.get('hostError'):
                raise RuntimeError('invalid ref')
            return current.get('hostPath')
        def map_path(path):
            mappings.append(path)
            if current.get('mapError'):
                raise RuntimeError('mapping failed')
            return current.get('path')
        if case.get('attachments', True):
            ctx.set_service('attachments', SimpleNamespace(fileHostPath=host_path))
        if case.get('fs', True):
            ctx.set_service('fs', SimpleNamespace(processPathFromHostPath=map_path))
        llm = CurrentLLMService(ctx)
        original = None
        class Adapter:
            def resolveModel(self, provider, model, signal=None):
                return dict(provider=provider, id=model, name=model,
                    **({'inputModalities': case['modalities']} if 'modalities' in case else {}))
            async def stream(self, request):
                requests.append(dict(messages=copy.deepcopy(request['messages']),
                    sameOptions=request is original, sameMessages=request['messages'] is original['messages'],
                    frozen=isinstance(request, FrozenDict)))
                yield dict(type='text', text='accepted')
        adapter = Adapter()
        if case.get('preparedAdapter'):
            async def prepare(provider, model, signal=None):
                return dict(model=adapter.resolveModel(provider, model, signal), stream=adapter.stream)
            adapter.prepareCall = prepare
            adapter.prepare_call = prepare
        llm.registerAdapter(['test'], adapter)
        def middleware(options, next_fn):
            hooks.append(copy.deepcopy(options['messages']))
            if case.get('shortCircuit'):
                async def short():
                    yield dict(type='text', text='short')
                return short()
            return next_fn()
        ctx.on('llm/stream', middleware)
        for step in case.get('steps', [{}]):
            current.clear()
            current.update(step)
            original = dict(provider='test', model='model', messages=copy.deepcopy(case['messages']))
            if case.get('frozen'):
                original = deep_freeze(original)
            ref = case['ref']
            try:
                handles.append(dict(outcome='value', value=llm.fileRequestText(ref)))
            except Exception as error:
                handles.append(dict(outcome='error', message=str(error)))
            if case.get('prepared'):
                prepared = await llm.prepareCall(dict(provider='test', model='model'))
                stream = prepared['stream'](original)
            else:
                stream = llm.stream(original)
            chunks.append([chunk async for chunk in stream])
        return dict(handles=handles, requests=requests, mappings=mappings, hooks=hooks, chunks=chunks)
    finally:
        await ctx.fiber.dispose()


def execute(case):
    return asyncio.run(run(case))

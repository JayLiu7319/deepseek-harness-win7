"""Actual MCP tool generation swaps, retaining old tools on failed fetches."""
import asyncio
from types import SimpleNamespace
from dsh.cordis.context import Context
from dsh.core.tools import ToolsService
from dsh.mcp.current import sync_tools


async def run(test):
    ctx=Context();tools=ToolsService(ctx);ctx.set_service('tools',tools);calls=[];disposed=[]
    previous={}
    for name in test.get('previous',['old']):
        public='mcp__test__'+name
        disposer=tools.register(dict(name=public,description='',parameters=dict(type='object'),output=dict(schema=dict(type='object'),render=lambda *_:[]),execute=lambda *_:None))
        def release(disposer=disposer,name=name):disposed.append(name);disposer()
        previous[public]=release
    index=0
    async def request(value):
        nonlocal index
        calls.append(value);page=test['pages'][index];index+=1
        if 'error' in page:raise RuntimeError(page['error'])
        return page
    try:
        try:
            result=await sync_tools(SimpleNamespace(request=request),ctx,dict(serverName='test',toolCallTimeoutMs=1000),previous)
            outcome=dict(registered=list(result))
        except Exception as error:outcome=dict(error=str(error))
        return dict(outcome=outcome,calls=calls,disposed=disposed,names=[tool.name for tool in tools.list_tools()])
    finally:await ctx.fiber.dispose()


def execute(test):return asyncio.run(run(test))

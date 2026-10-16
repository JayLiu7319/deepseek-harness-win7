"""Actual current Tools/Session/projection with a controlled opaque FS seam."""
import asyncio
import json
from types import SimpleNamespace

from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.core.system_prompt.current import CurrentSystemPrompt
from dsh.core.tools import ToolsPlugin, ToolExecutionInput
from dsh.core.scope import create_scope
from dsh.core.turn_boundary import TURN_BOUNDARY_DEFINITION
from dsh.session.projections import SessionProjectionsPlugin
from dsh.fs.fs_local import FsError
from dsh.fs.tool_present_current import CurrentToolPresent


class Owner:
    pass


async def run(test):
    ctx, calls, results, controller = Context(), [], [], AbortController()
    try:
        for plugin in (CurrentSessionPlugin, SessionProjectionsPlugin, CurrentSystemPrompt, ToolsPlugin):
            await ctx.plugin(plugin)
        if not test.get('noBoundary'):ctx.get('sessionProjections').register(TURN_BOUNDARY_DEFINITION)
        async def lstat(path, options, signal):
            calls.append(dict(op='lstat',path=path,cwd=options['cwd'],signal=signal is controller.signal))
            if test.get('fsError'):raise FsError('filesystem refused',test['fsError'])
            return None if test.get('lstatMissing') else dict(type=test.get('entryKind','file'))
        async def resolve(path, options):
            calls.append(dict(op='resolve',path=path,cwd=options['cwd'],signal=options['signal'] is controller.signal))
            return SimpleNamespace(displayPath='opaque:'+path)
        async def stat(target, signal):
            calls.append(dict(op='stat',path=target.displayPath,signal=signal is controller.signal))
            if test.get('abortDuring'):controller.abort(ValueError('caller cancelled'))
            return None if test.get('missing') else dict(type=test.get('statKind','file'))
        ctx.set_service('fs',SimpleNamespace(lstat=lstat,resolve=resolve,stat=stat))
        fiber=await ctx.plugin(CurrentToolPresent,test.get('config',{}))
        owner=Owner();owner.id='one';owner.options={}
        owner.session=ctx.get('sessions').create('one',dict(meta={} if test.get('noWorkspace') else dict(cwd='/project')))
        def scoped(inner):owner.ctx=create_scope(inner,owner).ctx
        scoped.inject=['tools']
        await ctx.plugin(scoped)
        await asyncio.sleep(0)
        if not test.get('closed'):owner.session.append('turn/start',dict(turn=3))
        if test.get('nested'):await owner.ctx.plugin(CurrentToolPresent,test.get('config',{}))
        if test.get('override'):
            owner.ctx.get('tools').register(dict(name='present',description='Scoped replacement.',parameters=dict(type='object',properties=dict(files=dict(type='array',items=dict(type='string'))),required=['files']),output=dict(schema=dict(type='object',additionalProperties=False,properties=dict(turn=dict(type='integer'),files=dict(type='array',items=dict(type='string'))),required=['turn','files']),render=lambda args,value:[]),execute=lambda args,execution:dict(turn=3,files=[])))
        if test.get('block'):
            async def block(execution,result,next_fn):
                await next_fn()
                return dict(kind='block',feedback=[dict(type='text',text='blocked')])
            ctx.on('tools/post-execute',block)
        if test.get('aborted'):controller.abort(ValueError('caller cancelled'))
        for index,files in enumerate(test.get('calls',[[dict(path='report.docx')]])):
            result=await ctx.get('tools').execute(ToolExecutionInput('call-'+str(index),'present',dict(files=files),agent=None if test.get('detached') else owner,signal=controller.signal))
            results.append(dict(isError=result.isError,content=result.content,**({} if result.isError else dict(value=result.value))))
        events=[dict(event['data']) for event in owner.session.snapshotEvents() if event['type']=='deliverables/presented']
        await fiber.dispose()
        return dict(results=results,calls=calls,deliveries=events,registered=ctx.get('tools').get('present',owner) is not None)
    finally:await ctx.fiber.dispose()


def execute(test):return json.loads(json.dumps(asyncio.run(run(test))))

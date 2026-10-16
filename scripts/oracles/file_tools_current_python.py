"""Current file tool prompts and execution boundaries, with controlled providers."""
import asyncio
import json
from types import SimpleNamespace

from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.core.scope import create_scope
from dsh.core.system_prompt.current import CurrentSystemPrompt
from dsh.core.tools import ToolsPlugin, ToolExecutionInput
from dsh.fs.fs_local import FsError
from dsh.fs.tools_current import CurrentToolFs, CurrentToolFsSearch


class Owner:
    pass


async def run(test):
    ctx=Context();saved=[]
    try:
        await ctx.plugin(CurrentSystemPrompt);await ctx.plugin(ToolsPlugin)
        async def resolve(path,options):return SimpleNamespace(displayPath='/project/'+path,targetKey='opaque')
        async def mutation(*args,**kwargs):raise FsError(test.get('reason','edit-specific provider reason'),test.get('code','FS_NOT_OBSERVED'))
        async def stat(*args):return SimpleNamespace(type='file',size=4,version='v1')
        async def read_bytes(*args):return b'PNG!'
        ctx.set_service('fs',SimpleNamespace(resolve=resolve,writeText=mutation,editText=mutation,stat=stat,readBytes=read_bytes))
        if test.get('operation')=='read_image':
            image=dict(attachmentId='sha256:'+'a'*64,mediaType='image/png',bytes=4,width=1,height=1)
            ctx.set_service('attachments',SimpleNamespace(image_limits=dict(mediaTypes=['image/png'],maxImageBytes=100,maxMessageImageBytes=100),save_image=lambda value:image))
            async def model(*args):return dict(inputModalities=['image'])
            ctx.set_service('llm',SimpleNamespace(resolve_model_info=model))
        def spawn(spec):
            if test.get('failure')=='launch':raise ValueError('private launch error')
            done=asyncio.get_running_loop().create_future()
            if test.get('failure')=='provider':done.set_exception(ValueError('private provider error'))
            else:done.set_result(SimpleNamespace(exitCode=0,signal=None))
            def reader(text):return SimpleNamespace(read_from=lambda offset:SimpleNamespace(text=text,lossy=False))
            stdout='a.txt\nb.txt\n' if test.get('operation','glob')=='glob' else '\n'.join(json.dumps(dict(type='match',data=dict(path=dict(text='a.txt'),lines=dict(text='line\n'),line_number=i))) for i in (1,2))
            return SimpleNamespace(done=done,collected=SimpleNamespace(stdout=reader(stdout),stderr=reader('')))
        ctx.set_service('subprocess',SimpleNamespace(spawn=spawn))
        async def save(value):
            saved.append(value)
            return dict(locator='/spill/result',retrievalHint='read spill')
        ctx.set_service('spillStore',SimpleNamespace(saveText=save))
        await ctx.plugin(CurrentToolFs)
        await ctx.plugin(CurrentToolFsSearch,dict(sampleOverCapGlobResults=False,globMaxResults=1,grepMaxMatches=1))
        owner=Owner();owner.id='one';owner.options=dict(provider='fixture',model='model');owner.session=SimpleNamespace(header=SimpleNamespace(cwd='/project',id='one'),requestHeader=lambda:None)
        def scoped(inner):owner.ctx=create_scope(inner,owner).ctx
        scoped.inject=['tools'];await ctx.plugin(scoped);await asyncio.sleep(0)
        if 'allow'in test:owner.ctx.get('tools').restrict(dict(allow=test['allow']))
        if test.get('replaceImage'):
            async def replace(execution,result,next_fn):
                await next_fn()
                return dict(kind='accept',content=[dict(type='text',text='replacement')])
            ctx.on('tools/post-execute',replace)
        if test.get('operation')=='prompt':
            prompt=await ctx.get('systemPrompt').assemble(dict(scope=owner))
            return dict(sections=[row for row in prompt['sections'] if row['name'].startswith('tool:')])
        op=test.get('operation','glob')
        arguments=dict(file_path='output',content='new') if op=='write' else dict(file_path='output',old_string='old',new_string='new') if op=='edit' else dict(file_path='image.png') if op=='read_image' else dict(pattern='x')
        result=await ctx.get('tools').execute(ToolExecutionInput('call',''+op,arguments,agent=owner,signal=AbortController().signal))
        return dict(isError=result.isError,content=result.content,**({} if result.isError else dict(value=result.value)),saved=saved,**(dict(meta=result.meta) if op=='read_image' and result.meta is not None else {}))
    finally:await ctx.fiber.dispose()


def execute(test):return json.loads(json.dumps(asyncio.run(run(test))))

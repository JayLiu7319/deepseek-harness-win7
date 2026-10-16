"""Published subprocess ownership boundaries, with controllable range observations."""
import asyncio
import io
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from dsh.core.abort import AbortController
from dsh.subagent.acp_current import dispose_acp_child, CurrentAcpRun, CurrentAcpProvider


def failure(error):
    result=dict(name=getattr(error,'name','AcpRunFailure' if type(error).__name__=='AcpRunFailure' else 'Error'),message=str(error))
    if hasattr(error,'errors'):result['errors']=[failure(item) for item in error.errors]
    if getattr(error,'cause',None) is not None:result['cause']=failure(error.cause)
    return result


async def run(test):
    if test['mode']=='peer':
        from dsh.cordis.context import Context
        from dsh.subprocess.local import LocalSubprocessRuntime
        from dsh.subagent.acp import CONFIG
        from scripts.oracles.subagent_acp_python import request
        ctx=Context();errors=[];child=None
        with tempfile.TemporaryDirectory(prefix='rc3-acp-peer-') as directory:
            try:
                await ctx.plugin(LocalSubprocessRuntime)
                service=ctx.get('subprocess');spawn=service.spawn
                def capture(spec):
                    nonlocal child
                    child=spawn(spec);return child
                service.spawn=capture
                config=CONFIG(dict(command=sys.executable,args=[str(Path(__file__).with_name('subagent_acp_peer.py'))],
                    env=test.get('env',{}),permission=test.get('permission','reject'),disposeEofGraceMs=150,disposeGraceMs=100))
                provider=CurrentAcpProvider(ctx,config);provider.report=lambda error,reason:errors.append(failure(error))
                handle=await provider.start(request(Path(directory),AbortController()))
                result=await handle.result
                await handle.dispose();await handle.dispose()
                return dict(result=result,errors=errors,reaped=await child.wait_for_exit(),exitCode=(await child.done).exitCode,
                            detached=not handle.request['signal']._listeners)
            finally:await ctx.fiber.dispose()
    trace=[];waits=list(test.get('waits',[True]));done=asyncio.get_running_loop().create_future()
    done.set_exception(RuntimeError('direct result rejected')) if test.get('reject') else done.set_result(None)
    done.exception()
    read_fd,write_fd=os.pipe()
    writer=os.fdopen(write_fd,'wb',buffering=0)
    reader=os.fdopen(read_fd,'rb')
    class Input(io.BytesIO):
        def close(self):
            if not self.closed:
                trace.append('eof');writer.close()
            super().close()
    def terminate():
        trace.append('terminate')
        if test.get('terminateError'):raise RuntimeError('termination failed')
    async def wait(signal=None):
        trace.append('bounded' if signal else 'unbounded')
        value=waits.pop(0)
        if isinstance(value,str):raise RuntimeError(value)
        return value
    child=SimpleNamespace(pid=test.get('pid',1),stdin=Input(),stdout=reader,done=done,terminate=terminate,wait_for_exit=wait)
    errors=[]
    try:
        try:
            if test['mode']=='dispose':
                await dispose_acp_child(child,5)
                result=dict(outcome='value')
            else:
                request=dict(parent=SimpleNamespace(),signal=AbortController().signal,prompt=[])
                config=dict(disposeEofGraceMs=5,disposeGraceMs=5,permission='reject')
                await CurrentAcpRun(child,request,config,lambda error,reason:errors.append(failure(error))).initialize(os.getcwd())
                raise AssertionError('rejected child published')
        except Exception as error:result=dict(outcome='error',error=failure(error))
        return dict(result=result,trace=trace,errors=errors)
    finally:
        child.stdin.close();writer.close();reader.close()

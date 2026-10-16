"""Observe current native desktop intent at the executable/argv boundary."""
import asyncio
from dsh.core.abort import AbortController
from dsh.host.native_command_current import can_open_native_path, native_file_manager, open_native_path, open_native_text_file, reveal_native_path


async def run(case):
    controller, calls = AbortController(), []
    async def command(executable, args, signal):
        calls.append(dict(command=executable, args=args, signal=signal is controller.signal))
        signal.throwIfAborted()
        reply = case.get('replies', {}).get(executable, {})
        if reply.get('abort'):
            controller.abort(RuntimeError('cancelled by caller'))
        if 'error' in reply:
            error = RuntimeError(reply['error'])
            if 'code' in reply:
                error.code = reply['code']
            raise error
        return dict(stdout=reply.get('stdout', ''), stderr='')
    options = dict(env={}, osRelease='generic')
    options.update(case.get('facts', {}))
    options['run'] = command
    if case.get('aborted'):
        controller.abort(RuntimeError('cancelled by caller'))
    try:
        operation = case['operation']
        if operation == 'facts':
            result = dict(available=can_open_native_path(options), manager=native_file_manager(options))
        else:
            await dict(open=open_native_path, text=open_native_text_file, reveal=reveal_native_path)[operation](case['path'], controller.signal, options)
            result = dict(opened=True)
        return dict(result=result, calls=calls)
    except Exception as error:
        return dict(error=str(error), calls=calls)


def execute(case):
    return asyncio.run(run(case))

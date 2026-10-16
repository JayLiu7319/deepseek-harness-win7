import { pathToFileURL } from 'node:url'
export async function nativePathCase(source: string, test: any) {
  const mod = await import(pathToFileURL(`${source}/packages/util/native-command/src/index.ts`).href)
  const controller = new AbortController(), calls: any[] = []
  const run = async (command: string, args: string[], signal: AbortSignal) => {
    calls.push({ command, args, signal: signal === controller.signal })
    signal.throwIfAborted()
    const reply = test.replies?.[command] ?? {}
    if (reply.abort) controller.abort(new Error('cancelled by caller'))
    if ('error' in reply) throw Object.assign(new Error(reply.error), 'code' in reply ? { code: reply.code } : {})
    return { stdout: reply.stdout ?? '', stderr: '' }
  }
  const options = { env: {}, osRelease: 'generic', ...test.facts, run }
  if (test.aborted) controller.abort(new Error('cancelled by caller'))
  try {
    let result
    if (test.operation === 'facts') result = { available: mod.canOpenNativePath(options), manager: mod.nativeFileManager(options) }
    else {
      await ({ open: mod.openNativePath, text: mod.openNativeTextFile, reveal: mod.revealNativePath })[test.operation](test.path, controller.signal, options)
      result = { opened: true }
    }
    return { result, calls }
  } catch (error) { return { error: (error as Error).message, calls } }
}

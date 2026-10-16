/** Observe actual restore arguments/results from unchanged upstream assertions.
 * Copies test files to an ignored, owned Source cache; production Source stays untouched.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve, join } from 'node:path'
const [sourceArg, outputArg] = process.argv.slice(2)
if (!sourceArg || !outputArg) throw new Error('Explicit Source and fresh cache output required')
const source = resolve(sourceArg).replaceAll('\\', '/'), output = resolve(outputArg).replaceAll('\\', '/')
if (!output.startsWith(source + '/.cache/')) throw new Error('Capture output must be in Source .cache')
mkdirSync(source + '/.cache', { recursive: true })
mkdirSync(output, { recursive: false })
const base = source + '/packages/session/session-format-v0-to-v1'
writeFileSync(join(output, 'restore.mts'), `
import { appendFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import * as source from ${JSON.stringify(base + '/src/testing/restore.ts')}
const encode = (v: any) => JSON.parse(JSON.stringify(v, (_k, value) => value === undefined ? {$scalar:'undefined'} : typeof value === 'number' && (!Number.isFinite(value) || Object.is(value,-0)) ? {$scalar: Object.is(value,-0) ? '-0' : String(value)} : value))
function run(operation: string, header: any, rows: any, recovery: any) {
  const args = {header: encode(header), rows: encode(rows), recovery: recovery ?? 'strict'}
  const name = operation + '/' + createHash('sha256').update(JSON.stringify(args)).digest('hex').slice(0, 20)
  let expected, value, failure
  try { value = (operation === 'restore-v0' ? source.restoreV0ToV1 : source.restoreV1)(header, rows, recovery); expected = {outcome:'value', value} }
  catch (error: any) { failure = error; expected = {outcome:'error',name:error.name,message:error.message,...(error.cause ? {cause: error.cause.message} : {})} }
  appendFileSync(${JSON.stringify(output + '/observations.jsonl')}, JSON.stringify({case:name,kind:'released-logical',operation,...args,expected})+'\\n', 'utf8')
  if (failure) throw failure
  return value
}
export const restoreV0ToV1 = (h: any, r: any, recovery?: any) => run('restore-v0', h, r, recovery)
export const restoreV1 = (h: any, r: any, recovery?: any) => run('restore-v1', h, r, recovery)
`, { encoding: 'utf8', flag: 'wx' })
for (const name of ['validation', 'relationships', 'migration', 'legacy']) {
  const original = readFileSync(join(base, 'tests', name + '.spec.ts'), 'utf8')
  const copied = original.replaceAll("'../src/testing/restore.ts'", "'./restore.mts'")
    .replace(/(['"])\.\.\/src\/(.*?)\1/g, (_all, quote, path) => quote + base + '/src/' + path + quote)
  writeFileSync(join(output, name + '.spec.ts'), copied, { encoding: 'utf8', flag: 'wx' })
}
writeFileSync(join(output, 'vitest.config.mts'), `
import {defineConfig} from 'vitest/config'
import tsconfigPaths from 'vite-tsconfig-paths'
import {standardDecoratorPlugin, vitestExecArgv} from ${JSON.stringify(source + '/vitest.shared.ts')}
export default defineConfig({plugins:[standardDecoratorPlugin(),tsconfigPaths({projects:[${JSON.stringify(source + '/tsconfig.base.json')}]})],test:{include:[${JSON.stringify(output + '/*.spec.ts')}],fileParallelism:false,maxWorkers:1,execArgv:vitestExecArgv}})
`, { encoding: 'utf8', flag: 'wx' })
console.log(output + '/vitest.config.mts')

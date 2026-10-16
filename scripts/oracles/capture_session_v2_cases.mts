/** Capture the target's v2 writer validation and real adjacent migration examples. */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve, join } from 'node:path'
const [sourceArg, outputArg] = process.argv.slice(2)
if (!sourceArg || !outputArg) throw new Error('Explicit Source and fresh cache output required')
const source = resolve(sourceArg).replaceAll('\\', '/'), output = resolve(outputArg).replaceAll('\\', '/')
if (!output.startsWith(source + '/.cache/')) throw new Error('Capture output must be in Source .cache')
mkdirSync(source + '/.cache', { recursive: true })
mkdirSync(output, { recursive: false })
const base = source + '/packages/session/session-format-v1-to-v2'
writeFileSync(join(output, 'capture.mts'), `
import {appendFileSync} from 'node:fs'
import {createHash} from 'node:crypto'
const encode = (v: any) => JSON.parse(JSON.stringify(v, (_k, value) => value === undefined ? {$scalar:'undefined'} : typeof value === 'number' && (!Number.isFinite(value) || Object.is(value,-0)) ? {$scalar:Object.is(value,-0)?'-0':String(value)} : value))
export function capture(operation: string, args: any, run: () => any) {
  const inputs = operation==='stage'?args:encode(args)
  let expected, result, failure
  try { result=run(); expected={outcome:'value',value:result ?? null} }
  catch(error: any) {failure=error;expected={outcome:'error',name:error.name,message:error.message,...(error.cause ? {cause:error.cause.message} : {})}}
  const name=operation+'/'+createHash('sha256').update(JSON.stringify(inputs)).digest('hex').slice(0,20)
  appendFileSync(${JSON.stringify(output + '/observations.jsonl')},JSON.stringify({case:name,kind:'released-v2-logical',operation,...inputs,expected})+'\\n','utf8')
  if(failure) throw failure
  return result
}
export function wrapStage(stage: any,input: any,output: any) {
  const actions: any[]=[]
  const call=(method: string,value?: any)=>{
    const action: any={method}
    if(method==='transformEvent') action.event=encode(value)
    if(method==='transformRun') {
      action.run=encode(Object.fromEntries(Object.entries(value).filter(([key])=>key!=='expand')))
      action.expanded=[]
    }
    actions.push(action)
    let result
    capture('stage',{input,actions},()=>{
      const run=method==='transformRun'?{...value,*expand(){for(const event of value.expand()){action.expanded.push(encode(event));yield event}}}:undefined
      result=method==='finish'?stage.finish(output):stage[method](method==='transformRun'?run:value,output)
      return {events:output.values,...(method==='finish'?{cut:result}:{})}
    })
    return result
  }
  return {transformEvent:(v: any)=>call('transformEvent',v),transformRun:(v: any)=>call('transformRun',v),finish:()=>call('finish')}
}
`, { encoding: 'utf8', flag: 'wx' })
writeFileSync(join(output, 'validation.mts'), `
import {capture} from './capture.mts'
import {assertReleasedV2Artifact as original} from ${JSON.stringify(base + '/src/testing/validation.ts')}
export {assertReleasedV2PhysicalArtifact} from ${JSON.stringify(base + '/src/testing/validation.ts')}
export const assertReleasedV2Artifact=(artifact: any)=>capture('writer',{artifact},()=>original(artifact))
`, { encoding: 'utf8', flag: 'wx' })
writeFileSync(join(output, 'api.mts'), `
export * from ${JSON.stringify(base + '/src/index.ts')}
import {restoreReleasedV2Artifact as original} from ${JSON.stringify(base + '/src/index.ts')}
import {capture} from './capture.mts'
export const restoreReleasedV2Artifact=(artifact: any,known: any,version?: number)=>capture('restore',{artifact,known:[...known],...(version===undefined?{}:{relationshipVersion:version})},()=>original(artifact,known,version))
`, { encoding: 'utf8', flag: 'wx' })
for (const name of ['validation', 'migration']) {
  let copied = readFileSync(join(base, 'tests', name + '.spec.ts'), 'utf8')
    .replaceAll("'../src/testing/validation.ts'", "'./validation.mts'")
    .replaceAll("'@deepseek-ai/dsh-session-format-v1-to-v2'", "'./api.mts'")
    .replace(/(['"])\.\.\/src\/(.*?)\1/g, (_all, quote, path) => quote + base + '/src/' + path + quote)
  if (name === 'migration') {
    if (!copied.includes('function migrateV1ToV2(source: SessionFormatArtifact)')) throw new Error('Source migration fixture changed')
    if (!copied.includes('return { stage, output: new SessionFormatEventCollector() }')) throw new Error('Source stage harness changed')
    copied = "import {capture,wrapStage} from './capture.mts'\n" + copied.replace('function migrateV1ToV2(source: SessionFormatArtifact)', 'function originalMigrateV1ToV2(source: SessionFormatArtifact)')
      .replace('return { stage, output: new SessionFormatEventCollector() }', "const output = new SessionFormatEventCollector(); return {stage:wrapStage(stage,{sourceHeader,sourceInheritedEventCount:options.sourceCut??0,sourceKind:options.sourceKind??'decoded'},output),output}")
      + "\nfunction migrateV1ToV2(artifact: SessionFormatArtifact) {return capture('migrate',{artifact},()=>originalMigrateV1ToV2(artifact))}\n"
  }
  writeFileSync(join(output, name + '.spec.ts'), copied, { encoding: 'utf8', flag: 'wx' })
}
writeFileSync(join(output, 'vitest.config.mts'), `
import {defineConfig} from 'vitest/config'
import tsconfigPaths from 'vite-tsconfig-paths'
import {standardDecoratorPlugin,vitestExecArgv} from ${JSON.stringify(source + '/vitest.shared.ts')}
export default defineConfig({plugins:[standardDecoratorPlugin(),tsconfigPaths({projects:[${JSON.stringify(source + '/tsconfig.base.json')}]})],test:{include:[${JSON.stringify(output + '/*.spec.ts')}],fileParallelism:false,maxWorkers:1,execArgv:vitestExecArgv}})
`, { encoding: 'utf8', flag: 'wx' })
console.log(output + '/vitest.config.mts')

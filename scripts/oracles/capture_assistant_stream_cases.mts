/** Observe JSON-representable inputs in the target's unchanged LLM stream assertions. */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve, join } from 'node:path'
const [sourceArg, outputArg] = process.argv.slice(2)
if (!sourceArg || !outputArg) throw new Error('Explicit Source and fresh cache output required')
const source = resolve(sourceArg).replaceAll('\\', '/'), output = resolve(outputArg).replaceAll('\\', '/')
if (!output.startsWith(source + '/.cache/')) throw new Error('Capture output must be in Source .cache')
mkdirSync(source + '/.cache', { recursive: true })
mkdirSync(output, { recursive: false })
const base = source + '/packages/llm/llm'
const functions = ['expandAssistantStream','isTokenDelta','isVisibleChunk','chunkHasVisibleText','runFirstTokenTime','runFirstVisibleTime','assistantStreamFirstTokenTime','assistantStreamHasVisibleContent','assistantStreamHasVisibleText','lastAssistantStreamChunk','assistantStreamChunks','joinAssistantStreamText']
writeFileSync(join(output, 'api.mts'), `
export * from ${JSON.stringify(base + '/src/index.ts')}
import * as source from ${JSON.stringify(base + '/src/index.ts')}
import {appendFileSync} from 'node:fs'
import {createHash} from 'node:crypto'
import {types} from 'node:util'
function encodable(value: any, seen=new Set()): boolean {
  if(typeof value==='function'||typeof value==='symbol'||typeof value==='bigint') return false
  if(value===null||typeof value!=='object') return true
  if(types.isProxy(value)||seen.has(value)) return false
  seen.add(value)
  const ok=Reflect.ownKeys(value).filter(k=>k!=='length').every(k=>typeof k==='string'&&Object.getOwnPropertyDescriptor(value,k)?.get===undefined&&encodable(value[k],seen))
  seen.delete(value)
  return ok
}
const encode=(v: any)=>JSON.parse(JSON.stringify(v,(_k,value)=>value===undefined?{$scalar:'undefined'}:typeof value==='number'&&(!Number.isFinite(value)||Object.is(value,-0))?{$scalar:Object.is(value,-0)?'-0':String(value)}:value))
function capture(operation: string,args: any,run: ()=>any) {
  if(!encodable(args)) {appendFileSync(${JSON.stringify(output + '/skipped.jsonl')},JSON.stringify({operation,reason:'Non-JSON function, proxy, accessor or cycle; assertions still execute'})+'\\n','utf8');return run()}
  const inputs=encode(args)
  let expected,result,failure
  try {result=run();expected={outcome:'value',value:result??null}}
  catch(error: any){failure=error;expected={outcome:'error',name:error.name,message:error.message,...(error.cause?{cause:error.cause.message}:{})}}
  const name=operation+'/'+createHash('sha256').update(JSON.stringify(inputs)).digest('hex').slice(0,20)
  appendFileSync(${JSON.stringify(output + '/observations.jsonl')},JSON.stringify({case:name,kind:'assistant-stream',operation,...inputs,expected})+'\\n','utf8')
  if(failure) throw failure
  return result
}
export class AssistantStreamAccumulator extends source.AssistantStreamAccumulator {
  private observed: any[]=[]
  override push(value: any) {
    const candidate=encodable(value)?encode(value):undefined
    const result=capture('push',{timed:[...this.observed,value]},()=>super.push(value))
    if(candidate!==undefined) this.observed.push(candidate)
    return result
  }
  override snapshot(){return capture('snapshot',{timed:this.observed},()=>super.snapshot())}
}
${functions.map(name=>`export const ${name}=(...args: any[])=>capture('${name}',{args},()=>source.${name}(...args as never))`).join('\n')}
`, { encoding: 'utf8', flag: 'wx' })
writeFileSync(join(output, 'assistant-stream.spec.ts'), readFileSync(join(base, 'tests/assistant-stream.spec.ts'), 'utf8').replaceAll("'@deepseek-ai/dsh-llm'", "'./api.mts'"), { encoding: 'utf8', flag: 'wx' })
writeFileSync(join(output, 'vitest.config.mts'), `
import {defineConfig} from 'vitest/config'
import tsconfigPaths from 'vite-tsconfig-paths'
import {standardDecoratorPlugin,vitestExecArgv} from ${JSON.stringify(source + '/vitest.shared.ts')}
export default defineConfig({plugins:[standardDecoratorPlugin(),tsconfigPaths({projects:[${JSON.stringify(source + '/tsconfig.base.json')}]})],test:{include:[${JSON.stringify(output + '/*.spec.ts')}],fileParallelism:false,maxWorkers:1,execArgv:vitestExecArgv}})
`, { encoding: 'utf8', flag: 'wx' })
console.log(output + '/vitest.config.mts')

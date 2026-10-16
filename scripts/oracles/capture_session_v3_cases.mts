/** Run unchanged target assertions through wrappers recording JSON-visible API calls. */
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { resolve, join } from 'node:path'
const [sourceArg, outputArg] = process.argv.slice(2)
if (!sourceArg || !outputArg) throw new Error('Explicit Source and fresh cache output required')
const source = resolve(sourceArg).replaceAll('\\', '/'), output = resolve(outputArg).replaceAll('\\', '/')
if (!output.startsWith(source + '/.cache/')) throw new Error('Capture output must be in Source .cache')
mkdirSync(source + '/.cache', { recursive: true })
mkdirSync(output, { recursive: false })
const base = source + '/packages/session/session-format-v2-to-v3'
writeFileSync(join(output, 'capture.mts'), `
import {appendFileSync} from 'node:fs'
import {createHash} from 'node:crypto'
export const encode = (v: any) => JSON.parse(JSON.stringify(v, (_k, value) => value === undefined ? {$scalar:'undefined'} : typeof value === 'number' && (!Number.isFinite(value) || Object.is(value,-0)) ? {$scalar:Object.is(value,-0)?'-0':String(value)} : value))
export function capture(operation: string, args: any, run: () => any) {
  const inputs=encode(args)
  let expected, result, failure
  try {result=run();expected={outcome:'value',value:result??null}}
  catch(error:any) {failure=error;expected={outcome:'error',name:error.name,message:error.message,...(error.cause?{cause:error.cause.message}:{})}}
  const name=operation+'/'+createHash('sha256').update(JSON.stringify(inputs)).digest('hex').slice(0,20)
  appendFileSync(${JSON.stringify(output + '/observations.jsonl')},JSON.stringify({case:name,kind:'released-v3-logical',operation,...inputs,expected})+'\\n','utf8')
  if(failure) throw failure
  return result
}
export function wrapStage(stage: any,input: any) {
  const actions:any[]=[],events:any[]=[]
  const execute=(method:string,value:any,context:any)=>{
    const action:any={method}
    if(method==='transformEvent')action.event=encode(value)
    if(method==='transformRun')action.expanded=[...value.expand()].map(encode)
    actions.push(action)
    let result
    capture('stage',{input,actions},()=>{
      const proxy={emitEvent:(e:any)=>{events.push(e);context.emitEvent(e)},emitRun:(r:any)=>{events.push(...r.expand());context.emitRun(r)}}
      result=method==='finish'?stage.finish(proxy):stage[method](method==='transformRun'?{*expand(){yield*action.expanded}}:value,proxy)
      return {events,...(method==='finish'?{cut:result}:{})}
    })
    return result
  }
  return {...stage,transformEvent:(v:any,c:any)=>execute('transformEvent',v,c),transformRun:(v:any,c:any)=>execute('transformRun',v,c),finish:(c:any)=>execute('finish',undefined,c)}
}
export function wrapCodec(codec:any) {
 return {...codec,
  decodeHeader:(header:any)=>capture('decodeHeader',{header},()=>codec.decodeHeader(header)),
  encodeHeader:(header:any,cut:any)=>capture('encodeHeader',{header,cut},()=>codec.encodeHeader(header,cut)),
  encodeEvent:(event:any)=>capture('encodeEvent',{event},()=>codec.encodeEvent(event)),
  createDecoder:(header:any,recovery:any)=>{
   const decoder=codec.createDecoder(header,recovery),rows:any[]=[],events:any[]=[]
   return {...decoder,decodeRow:(row:any,context:any)=>{
    rows.push(encode(row))
    return capture('decoder',{header,recovery,rows},()=>{decoder.decodeRow(row,{emitEvent:(e:any)=>{events.push(e);context.emitEvent(e)},emitRun:(r:any)=>{events.push(...r.expand());context.emitRun(r)}});return {header:decoder.header,events}})
   },finish:(context:any)=>capture('decoder',{header,recovery,rows,finish:true},()=>({header:decoder.header,events,cut:decoder.finish(context)})).cut}
  }}
}
`, { encoding: 'utf8', flag: 'wx' })
writeFileSync(join(output, 'api.mts'), `
export * from ${JSON.stringify(base + '/src/index.ts')}
import * as original from ${JSON.stringify(base + '/src/index.ts')}
import {capture,wrapStage,wrapCodec} from './capture.mts'
export const assertReleasedV3Header=(header:any)=>capture('header',{header},()=>original.assertReleasedV3Header(header))
export const restoreReleasedV3Artifact=(artifact:any,known:any)=>capture('restore',{artifact,known:[...known]},()=>original.restoreReleasedV3Artifact(artifact,known))
export const releasedV3SessionFormatCodec=wrapCodec(original.releasedV3SessionFormatCodec)
export const sessionFormatV2ToV3={...original.sessionFormatV2ToV3,
 migrateHeader:(header:any)=>capture('migrateHeader',{header},()=>original.sessionFormatV2ToV3.migrateHeader(header)),
 createStage:(input:any)=>wrapStage(original.sessionFormatV2ToV3.createStage(input),input)}
`, { encoding: 'utf8', flag: 'wx' })
for (const [module, functions] of Object.entries({payload:['assertEvent','assertV3Event','assertV3StructuralRow','canonicalizeTransformedEvent','isRepairIdentity'],references:['remapEvent']})) {
 writeFileSync(join(output,module+'.mts'), `export * from ${JSON.stringify(base+'/src/'+module+'.ts')}\nimport * as original from ${JSON.stringify(base+'/src/'+module+'.ts')}\nimport {capture} from './capture.mts'\n`+functions.map(fn=>`export const ${fn}=(...args:any[])=>capture('${fn}',{args},()=>original.${fn}(...args))`).join('\n'), {encoding:'utf8',flag:'wx'})
}
for (const name of readdirSync(join(base,'tests')).filter(name=>name.endsWith('.spec.ts'))) {
 let copied=readFileSync(join(base,'tests',name),'utf8')
  .replaceAll("'../src/index.ts'","'./api.mts'")
  .replaceAll("'../src/payload.ts'","'./payload.mts'")
  .replaceAll("'../src/references.ts'","'./references.mts'")
  .replace(/(['"])\.\.\/src\/(.*?)\1/g, (_all,quote,path)=>quote+base+'/src/'+path+quote)
 writeFileSync(join(output,name),copied,{encoding:'utf8',flag:'wx'})
}
writeFileSync(join(output, 'vitest.config.mts'), `
import {defineConfig} from 'vitest/config'
import tsconfigPaths from 'vite-tsconfig-paths'
import {standardDecoratorPlugin,vitestExecArgv} from ${JSON.stringify(source + '/vitest.shared.ts')}
export default defineConfig({plugins:[standardDecoratorPlugin(),tsconfigPaths({projects:[${JSON.stringify(source + '/tsconfig.base.json')}]})],test:{include:[${JSON.stringify(output + '/*.spec.ts')}],fileParallelism:false,maxWorkers:1,execArgv:vitestExecArgv}})
`, { encoding: 'utf8', flag: 'wx' })
console.log(output + '/vitest.config.mts')

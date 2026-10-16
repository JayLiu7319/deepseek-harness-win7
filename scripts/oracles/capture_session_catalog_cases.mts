/** Capture real build-static catalog and installed-current boundary observations. */
import {mkdirSync,readFileSync,readdirSync,writeFileSync} from 'node:fs'
import {resolve,join} from 'node:path'
const [sourceArg,outputArg]=process.argv.slice(2)
if(!sourceArg||!outputArg)throw new Error('Explicit Source and fresh cache output required')
const source=resolve(sourceArg).replaceAll('\\','/'),output=resolve(outputArg).replaceAll('\\','/')
if(!output.startsWith(source+'/.cache/'))throw new Error('Owned Source cache required')
mkdirSync(output,{recursive:false})
const base=source+'/packages/session/session-format-catalog'
writeFileSync(join(output,'capture.mts'),`
import {appendFileSync} from 'node:fs'
import {createHash} from 'node:crypto'
export const encode=(v:any)=>JSON.parse(JSON.stringify(v,(_k,v)=>v===undefined?{$scalar:'undefined'}:typeof v==='number'&&(!Number.isFinite(v)||Object.is(v,-0))?{$scalar:Object.is(v,-0)?'-0':String(v)}:v))
export function capture(operation:string,args:any,run:()=>any) {
 const inputs=encode(args);let result,expected,failure
 try {result=run();expected={outcome:'value',value:result??null}}
 catch(error:any){failure=error;expected={outcome:'error',name:error.name,message:error.message,...(error.cause?{cause:error.cause.message}:{})}}
 const name=operation+'/'+createHash('sha256').update(JSON.stringify(inputs)).digest('hex').slice(0,20)
 appendFileSync(${JSON.stringify(output+'/observations.jsonl')},JSON.stringify({case:name,kind:'session-catalog',operation,...inputs,expected})+'\\n','utf8')
 if(failure)throw failure
 return result
}
`,{encoding:'utf8',flag:'wx'})
writeFileSync(join(output,'api.mts'),`
export * from ${JSON.stringify(base+'/src/index.ts')}
import {sessionFormatCatalog as original} from ${JSON.stringify(base+'/src/index.ts')}
import {capture,encode} from './capture.mts'
export const sessionFormatCatalog={...original,
 readHeader:(header:any)=>capture('readHeader',{header},()=>original.readHeader(header)),
 encodeCurrentHeader:(header:any,cut:any)=>capture('encodeCurrentHeader',{header,cut},()=>original.encodeCurrentHeader(header,cut)),
 encodeCurrentEvent:(event:any)=>capture('encodeCurrentEvent',{event},()=>original.encodeCurrentEvent(event)),
 createRestore:(header:any,options:any)=>{
  let reader:any;capture('createRestore',{header,options},()=>{reader=original.createRestore(header,options);return {header:reader.header}})
  const rows:any[]=[]
  return {...reader,decodeRow:(row:any)=>{rows.push(encode(row));capture('restore',{header,options,rows},()=>{reader.decodeRow(row);return {header:reader.header}})},
   finish:()=>capture('restore',{header,options,rows,finish:true},()=>reader.finish())}
 }}
`,{encoding:'utf8',flag:'wx'})
writeFileSync(join(output,'current.mts'),`
import * as original from ${JSON.stringify(base+'/src/current.ts')}
import {capture} from './capture.mts'
export const validateInstalledCurrentSessionHeader=(header:any)=>capture('currentHeader',{header},()=>original.validateInstalledCurrentSessionHeader(header))
export const validateInstalledCurrentSessionArtifact=(artifact:any)=>capture('currentArtifact',{artifact},()=>original.validateInstalledCurrentSessionArtifact(artifact))
`,{encoding:'utf8',flag:'wx'})
for(const name of readdirSync(join(base,'tests')).filter(name=>name.endsWith('.spec.ts'))){
 const copied=readFileSync(join(base,'tests',name),'utf8').replaceAll("'../src/index.ts'","'./api.mts'").replaceAll("'../src/current.ts'","'./current.mts'")
 writeFileSync(join(output,name),copied,{encoding:'utf8',flag:'wx'})
}
writeFileSync(join(output,'vitest.config.mts'),`
import {defineConfig} from 'vitest/config'
import tsconfigPaths from 'vite-tsconfig-paths'
import {standardDecoratorPlugin,vitestExecArgv} from ${JSON.stringify(source+'/vitest.shared.ts')}
export default defineConfig({plugins:[standardDecoratorPlugin(),tsconfigPaths({projects:[${JSON.stringify(source+'/tsconfig.base.json')}]})],test:{include:[${JSON.stringify(output+'/*.spec.ts')}],fileParallelism:false,maxWorkers:1,execArgv:vitestExecArgv}})
`,{encoding:'utf8',flag:'wx'})

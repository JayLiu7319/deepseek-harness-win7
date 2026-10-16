/** Record target JSONL helper/scanner behavior while executing original assertions. */
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs'
import {resolve,join} from 'node:path'
const [sourceArg,outputArg]=process.argv.slice(2)
if(!sourceArg||!outputArg)throw new Error('Explicit Source and fresh cache output required')
const source=resolve(sourceArg).replaceAll('\\','/'),output=resolve(outputArg).replaceAll('\\','/')
if(!output.startsWith(source+'/.cache/'))throw new Error('Owned Source cache required')
mkdirSync(output,{recursive:false})
const base=source+'/packages/session/session-persistence-jsonl'
writeFileSync(join(output,'format.mts'),`
export * from ${JSON.stringify(base+'/src/format.ts')}
import * as original from ${JSON.stringify(base+'/src/format.ts')}
import {appendFileSync} from 'node:fs'
import {createHash} from 'node:crypto'
function encode(v:any):any {
 if(v===undefined)return {$scalar:'undefined'}
 if(Buffer.isBuffer(v))return {$bytes:v.toString('hex')}
 if(typeof v==='number'&&(!Number.isFinite(v)||Object.is(v,-0)))return {$scalar:Object.is(v,-0)?'-0':String(v)}
 if(Array.isArray(v))return v.map(encode)
 if(v!==null&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,c])=>[k,encode(c)]))
 return v
}
function capture(operation:string,args:any,run:()=>any) {
 const inputs=encode(args);let result,expected,failure
 try {result=run();expected={outcome:'value',value:result??null}}
 catch(error:any){failure=error;expected={outcome:'error',name:error.name,message:error.message,...(error.cause?{cause:error.cause.message}:{})}}
 const name=operation+'/'+createHash('sha256').update(JSON.stringify(inputs)).digest('hex').slice(0,20)
 appendFileSync(${JSON.stringify(output+'/observations.jsonl')},JSON.stringify({case:name,kind:'jsonl-current',operation,...inputs,expected})+'\\n','utf8')
 if(failure)throw failure
 return result
}
${['assertNoRetiredHeaderFields','encodeSegment','projectKey','projectDir','sessionDir','generationLogFilename','parseGenerationLogFilename','generationLogPath','logPath','toHeaderLine','eventLine','eventLines','scanLog'].map(name=>`export const ${name}=(...args:any[])=>capture('function',{name:'${name}',args},()=>original.${name}(...args))`).join('\n')}
export class SessionLogScanner {
 private scanner:any
 private actions:any[]=[]
 constructor(private header:any,private recovery:any='recoverable') {
  capture('scanner',{header,recovery,actions:[]},()=>{this.scanner=new original.SessionLogScanner(header,recovery);return {checkpoint:this.scanner.checkpoint()}})
 }
 write(chunk:any){this.actions.push({method:'write',chunk:encode(chunk)});capture('scanner',{header:this.header,recovery:this.recovery,actions:this.actions},()=>{this.scanner.write(chunk);return {checkpoint:this.scanner.checkpoint()}})}
 checkpoint(){this.actions.push({method:'checkpoint'});return capture('scanner',{header:this.header,recovery:this.recovery,actions:this.actions},()=>({checkpoint:this.scanner.checkpoint()})).checkpoint}
 finish(){this.actions.push({method:'finish'});return capture('scanner',{header:this.header,recovery:this.recovery,actions:this.actions},()=>{const result=this.scanner.finish();return {checkpoint:this.scanner.checkpoint(),result}}).result}
}
`,{encoding:'utf8',flag:'wx'})
for(const name of ['jsonl','v3-event-admission']){
 let copied=readFileSync(join(base,'tests',name+'.spec.ts'),'utf8').replaceAll("'../src/format.ts'","'./format.mts'")
 copied=copied.replace(/(['"])(\.\.?\/[^'"]+)\1/g,(_all,quote,path)=>path==='./format.mts'?quote+path+quote:quote+resolve(base,'tests',path).replaceAll('\\','/')+quote)
 writeFileSync(join(output,name+'.spec.ts'),copied,{encoding:'utf8',flag:'wx'})
}
writeFileSync(join(output,'vitest.config.mts'),`
import {defineConfig} from 'vitest/config'
import tsconfigPaths from 'vite-tsconfig-paths'
import {standardDecoratorPlugin,vitestExecArgv} from ${JSON.stringify(source+'/vitest.shared.ts')}
export default defineConfig({plugins:[standardDecoratorPlugin(),tsconfigPaths({projects:[${JSON.stringify(source+'/tsconfig.base.json')}]})],test:{include:[${JSON.stringify(output+'/*.spec.ts')}],fileParallelism:false,maxWorkers:1,execArgv:vitestExecArgv,testNamePattern:'format helpers|scanLog unit|nested v3 Assistant streams|native V3 event admission'}})
`,{encoding:'utf8',flag:'wx'})

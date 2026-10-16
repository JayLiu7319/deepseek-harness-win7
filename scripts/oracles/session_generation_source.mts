/** Actual generation filesystem journeys; paths are replaced only by the owned root token. */
import {mkdtemp,writeFile,readFile,readdir,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function generationCase(source:string,test:any) {
 const root=await mkdtemp(join(tmpdir(),'dsh-generation-pair-'))
 const load=(path:string)=>import(pathToFileURL(join(source,path)).href)
 const api=await load('packages/session/session-persistence-jsonl/src/generation.ts')
 const zstd=await load('packages/session/session-persistence-jsonl/src/zstd.ts')
 const fmt=await load('packages/session/session-persistence-jsonl/src/format.ts')
 const {sessionFormatCatalog:catalog}=await load('packages/session/session-format-catalog/src/index.ts')
 const name=(v:number)=>fmt.generationLogFilename(v,test.compression)
 const sourcePath=join(root,name(test.version)),currentPath=join(root,name(3))
 const encode=async(raw:string)=>test.compression==='none'?Buffer.from(raw):await zstd.compressZstdFrame(Buffer.from(raw))
 try {
  let bytes:Buffer
  if(test.compression==='none')bytes=Buffer.from(test.raw)
  else {
   const end=test.raw.indexOf('\n')+1
   bytes=Buffer.concat([await encode(test.raw.slice(0,end)),...(test.raw.slice(end)?[await encode(test.raw.slice(end))]:[])])
   if(test.tornFrame)bytes=Buffer.concat([bytes,(await encode('tail\n')).subarray(0,6)])
   if(test.combinedFrame)bytes=await encode(test.raw)
  }
  await writeFile(sourcePath,bytes)
  let validationCalls=0,verificationCalls=0
  const options:any={sourcePath,currentPath,sourceVersion:test.version,compression:test.compression,
   format:{currentVersion:3,createRestore:(header:any)=>catalog.createRestore(header,{recovery:'recoverable',validation:'transformed'}),
    encodeHeader:(...args:any[])=>catalog.encodeCurrentHeader(...args),encodeEvent:(event:any)=>catalog.encodeCurrentEvent(event),
    isUnsupportedMigrationError:(error:any)=>error?.name==='SessionFormatUnsupportedMigrationError'},
   validateHistoricalHeader:async()=>{await Promise.resolve();validationCalls++;if(test.failHeader)throw new Error('historical header rejected')},
   verifyCurrentFile:async(...args:any[])=>{verificationCalls++;const result=await api.verifyJsonlCurrentGeneration(...args);return test.badDigest?{...result,digest:'0'.repeat(64)}:result}}
  let prepared:any
  if(test.operation==='verify') {
   const result=await api.verifyJsonlCurrentGeneration(sourcePath,test.compression,test.expectedId??'generation',test.count??0,test.prefix)
   return {bytes:result.bytes,digest:result.digest}
  }
  try {
   prepared=await api.prepareJsonlMigration(options)
   if(test.changedSource)await writeFile(sourcePath,Buffer.concat([bytes,Buffer.from('changed')]))
   if(test.target==='different')await writeFile(currentPath,'different')
   if(test.target==='same') {
    const first=await api.prepareJsonlMigration(options);await first.publish()
    if(test.appendWinner) {
     const winner=await readFile(currentPath)
     await writeFile(currentPath,Buffer.concat([winner,await encode('unvalidated append tail')]))
    }
   }
   if(test.publish)await Promise.all([prepared.publish(),prepared.publish()])
   const current=await readFile(currentPath).catch(()=>undefined)
   const plaintext=current?(test.compression==='none'?current.toString('utf8'):(await zstd.decompressZstdFrame(current.subarray(0,zstd.scanZstdFrames(current).frames[0].end)))).toString():null
   return {artifact:prepared.artifact,validationCalls,verificationCalls,sourceUnchanged:(await readFile(sourcePath)).equals(bytes),
    files:(await readdir(root)).sort(),currentHeader:plaintext?.split('\n')[0]??null}
  } catch(error:any) {
   if(error.cause instanceof SyntaxError)console.error(JSON.stringify({case:test.case,jsonParserCause:error.cause.message}))
   return {failure:{name:error.name,message:error.message.split(root).join('<root>'),
    ...(error.cause?{cause:error.cause instanceof SyntaxError?'$native-json-parser-error':error.cause.message.split(root).join('<root>')}:{})},validationCalls,verificationCalls,
    sourceUnchanged:(await readFile(sourcePath)).equals(bytes),files:(await readdir(root)).sort()}
  }
 } finally {await rm(root,{recursive:true,force:true})}
}

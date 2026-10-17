import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function logExportCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const api=await load('packages/session-query/session-log-export/src/archive.ts')
 const {SessionPersistenceNotFoundError}=await load('packages/session/session-persistence/src/index.ts')
 const trace:any[]=[],signal=new AbortController().signal
 const persistence={async open(id:string,access:string,options:any){
  trace.push(['open',id,access,Boolean(options.signal)])
  if(test.openError){if(test.openError==='missing')throw new SessionPersistenceNotFoundError(id);throw new Error(test.openError)}
  if(!test.logs[id])throw new SessionPersistenceNotFoundError(id)
  const record=structuredClone(test.logs[id])
  return {header:record.header,async read(start:number,end:any,options:any){trace.push(['read',id,start,Boolean(options.signal)]);if(test.readError)throw new Error(test.readError);return {events:record.events}},async close(){trace.push(['close',id]);if(test.closeError)throw new Error(test.closeError)}}
 }}
 const deps={sessionPersistence:persistence,sessions:{get:(id:string)=>test.live?.includes(id)?id:undefined,async flush(id:string){trace.push(['flush',id])}},sessionQuery:{async traceSession(id:string){trace.push(['trace',id]);return {descendants:test.descendants??[]}}},attachments:{async readImage(ref:any){trace.push(['image',ref.attachmentId]);return {data:new Uint8Array([1,2,3])}},async *readFileStream(ref:any){trace.push(['file',ref.attachmentId,ref.name]);yield new Uint8Array([4,5]);yield new Uint8Array([6])}}}
 try{
  let value:any
  if(test.operation==='serialize')value=api.serializeSessionLog(test.logs.root.header,test.logs.root.events)
  else if(test.operation==='read')value=await api.readSessionLogText(persistence,test.id??'root',test.signal?signal:undefined)??null
  else{
   value=[];const root=api.serializeSessionLog(test.logs.root.header,test.logs.root.events)
   for await(const row of api.sessionLogZipEntries(deps,root,'root',test.includeDescendants??false,signal)){
    if('chunks' in row){const chunks=[];for await(const chunk of row.chunks)chunks.push([...chunk]);value.push({path:row.path,chunks})}
    else if('data' in row)value.push({path:row.path,data:[...row.data]})
    else value.push(row)
   }
  }
  return {value,trace}
 }catch(error){return {error:String((error as Error).message),trace}}
}

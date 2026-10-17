import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function statsCase(source:string,test:any,decode:(value:any)=>any){
  const {sessionStatsProjectionDefinition:d}=await import(pathToFileURL(join(source,'packages/session/session-stats/src/projection.ts')).href)
  if(test.operation==='schema'){
    const result=(test.schema==='state'?d.stateSchema:d.wire.viewSchema).safeParse(decode(test.value))
    return result.success?{accepted:true,value:result.data}:{accepted:false}
  }
  let state=d.init();const stages=[]
  for(const event of decode(test.events)){
    const updated=d.apply(state,event)
    stages.push({same:updated===state,state:updated,view:d.wire.view(updated)});state=updated
  }
  return {version:d.stateVersion,stages}
}

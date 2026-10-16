/** Actual rc.3 catalog, attribution, and Activation inbox units. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function subagentUnits(source:string,test:any,normalize:(v:any)=>any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 if(test.operation==='catalog'){
  const {subagentCatalogProjectionDefinition:d}=await load('packages/subagent/subagent/src/catalog.ts')
  let state=d.init({},test.cut??0),results:any[]=[]
  for(const action of test.actions){
   try{
    if(action.method==='apply'){const old=state;state=d.apply(state,action.event);results.push({accepted:true,changed:old!==state})}
    else if(action.method==='checkpoint'){state=d.stateSchema.parse(JSON.parse(JSON.stringify(state)));results.push({accepted:true})}
    else if(action.method==='state'){results.push({accepted:true,value:d.stateSchema.parse(action.value)})}
    else if(action.method==='view'){results.push({accepted:true,value:d.wire.viewSchema.parse(action.value)})}
   }catch{results.push({accepted:false})}
  }
  return {results,state,view:d.wire.view(state)}
 }
 if(test.operation==='continuation-messages'){
  const m=await load('packages/subagent/subagent/src/continuation-messages.ts')
  return normalize(test.actions.map((action:any)=>action.method==='relay'?m.createAgentMessage({id:action.id},action.content)
   :action.method==='guidance'?m.withContinuableReturnGuidance(action.id,action.content):m.createSettlementMessage(action.id,action.terminal)))
 }
 if(test.operation==='subagent-inbox'){
  const {SubagentInbox}=await load('packages/subagent/subagent/src/inbox.ts')
  const inbox={nextTurn:[],nextStep:[]},sent:any[]=[],trace:any[]=[]
  const agent={id:'unit',inbox,steer:(value:any)=>{sent.push(['steer',value]);inbox.nextStep.push(value as never)},followup:(value:any)=>{sent.push(['queue',value]);inbox.nextTurn.push(value as never)}}
  const unit=new SubagentInbox(agent)
  unit.deliver({id:'one'},test.delivery)
  const before=unit.hasPending
  let finish:any
  const released=new Promise<void>((resolve,reject)=>{finish=test.fail?()=>reject(new Error('release failed')):resolve})
  const close=unit.close(async()=>{trace.push('release');try{unit.deliver({id:'reentry'},'queue')}catch(error:any){trace.push(error.code)}await released;trace.push('released')})
  const again=unit.close(async()=>{trace.push('duplicate release')})
  trace.push(close===again,unit.closing===close,unit.hasPending)
  finish();try{await close;trace.push('fulfilled')}catch(error:any){trace.push(error.message)}
  return {sent,before,trace}
 }
 throw new Error('Unknown subagent unit')
}

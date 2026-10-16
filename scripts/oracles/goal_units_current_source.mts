import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
export async function run(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,'packages/goal/goal/src',p)).href)
 const {goalProjectionDefinition:definition}=await load('index.ts'),{applyGoalEvent,emptyGoalFoldState}=await load('fold.ts')
 if(test.mode==='checkpoint'){const result=definition.stateSchema.safeParse(test.input);return result.success?{accepted:true,value:result.data}:{accepted:false}}
 let state=definition.init();const folded=emptyGoalFoldState(),results:any[]=[]
 for(const event of test.events){
  state=definition.apply(state,event)
  try{
   applyGoalEvent(folded,event)
   const {seenGoalIds,...fold}=folded
   results.push({fold:JSON.parse(JSON.stringify(fold)),state,view:definition.wire.view(state)})
  }catch(error:any){results.push({error:error.message,state,view:definition.wire.view(state)})}
 }
 return results
}

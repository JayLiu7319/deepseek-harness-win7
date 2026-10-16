import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function run(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,'packages/llm/token-meter/src',p)).href)
 if(test.mode==='turn-usage'){const m=await load('turn-usage.ts');return {usage:m.deriveTurnTokenUsage(test.events)??null}}
 if(test.mode==='estimate'){const m=await load('estimate.ts');return m.estimateMessage(test.input)}
 if(test.mode==='checkpoint'){
  const modules=[await load('usage-projection.ts'),await load('breakdown-projection.ts')]
  const definition=modules.flatMap(m=>Object.values(m)).find((d:any)=>d.key===test.key) as any
  const result=definition.stateSchema.safeParse(test.input)
  return result.success?{accepted:true,value:result.data}:{accepted:false}
 }
 const {planSurfaceTokens,commitSurfaceTokens}=await load('surface-fold.ts'),{priceSurface}=await load('route-pricing.ts')
 const nodes:any[]=[],trace:any[]=[]
 const pricing=test.prices===undefined?undefined:{priceImages:(refs:any)=>{trace.push(refs);return test.prices}}
 try{
  for(const event of test.events??[])commitSurfaceTokens(nodes,planSurfaceTokens(nodes,event))
  return {nodes,value:priceSurface(nodes,pricing,test.fileText?(ref:any)=>'File '+ref.id:undefined),trace}
 }catch(error:any){return {error:error.message,trace,nodes}}
}

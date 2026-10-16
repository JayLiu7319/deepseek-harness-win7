/** Actual original region transaction under the same explicit priced-meter contract. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'

export async function run(source:string,session:any,test:any,normalize:(v:any)=>any){
 const {selectCompactableRange,compactSurfaceRegion}=await import(pathToFileURL(join(source,'packages/compaction/compaction-basic/src/region.ts')).href)
 const calls:any[]=[],meter={measure:(subject:any)=>({nodes:subject.surface.nodes.map((seq:number)=>({seq,tokens:10000,heuristicTokens:10000}))}),estimateMessage:()=>1}
 const dependencies={meter,summarize:async(input:any)=>{calls.push(input);return {summary:[{type:'text',text:'summary'}],provider:'test',model:'model'}}}
 const ranges=(test.retain??[0]).map((retain:number)=>selectCompactableRange(session,meter.measure(session),retain))
 const result=test.compact&&ranges[0]!==null?await compactSurfaceRegion(dependencies,session,ranges[0].start,ranges[0].end,{session},{owner:null,stability:'selected-span'}):null
 return normalize({ranges,calls,result,events:session.snapshotEvents(),messages:session.deriveMessages(),nodes:session.surface.nodes})
}

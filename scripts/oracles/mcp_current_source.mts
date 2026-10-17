/** Invoke unchanged Source bridge and real ToolRuntime generation registry. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
export async function mcpCurrentCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href)
 const {Context}=await load('vendor/cordis/src/index.ts'),{default:Tools}=await load('packages/core/tools/src/index.ts'),{default:Prompt}=await load('packages/core/system-prompt/src/index.ts'),{syncTools}=await load('packages/mcp/mcp-client/src/tools.ts')
 const ctx=new Context(),calls:any[]=[],disposed:string[]=[],previous=new Map()
 await ctx.plugin(Prompt);await ctx.plugin(Tools)
 for(const name of test.previous??['old']){const pub='mcp__test__'+name,dispose=ctx.tools.register({name:pub,description:'',parameters:{type:'object'},output:{schema:{type:'object'},render:()=>[]},execute:async()=>({})});previous.set(pub,()=>{disposed.push(name);dispose()})}
 let index=0
 const client={request:async(value:any)=>{calls.push(value);const page=test.pages[index++];if('error'in page)throw new Error(page.error);return page}}
 try{
  let outcome:any
  try{outcome={registered:[...await syncTools(client,ctx,{serverName:'test',toolCallTimeoutMs:1000,registrationFailure:'contain'},previous)].map(([name])=>name)}}catch(error:any){outcome={error:error.message}}
  return{outcome,calls,disposed,names:ctx.tools.schemas().map((tool:any)=>tool.name)}
 }finally{await ctx.fiber.dispose()}
}

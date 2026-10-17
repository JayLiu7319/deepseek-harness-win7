/** Actual default/custom provider, public model discovery and prepared calls. */
import {execFileSync} from 'node:child_process'
import {mkdirSync,writeFileSync} from 'node:fs'
import {join,resolve} from 'node:path'
import {pathToFileURL} from 'node:url'
const [sourceArg,outputArg]=process.argv.slice(2)
if(!sourceArg||!outputArg)throw new Error('Explicit Source and fresh output required')
const root=resolve(sourceArg),output=resolve(outputArg)
const pin=()=>execFileSync('git',['-C',root,'rev-parse','HEAD'],{encoding:'utf8'}).trim()
if(pin()!=='a4c74a91e06b00fe0b0937bde982170c526cc842'||execFileSync('git',['-C',root,'status','--porcelain'],{encoding:'utf8'}).trim())throw new Error('Unchanged rc.3 Source required')
mkdirSync(output)
const load=(path:string)=>import(pathToFileURL(join(root,path)).href)
const {Context}=await load('vendor/cordis/src/index.ts')
const api=await load('packages/llm/llm/src/index.ts'),provider=await load('packages/llm/llm-deepseek/src/index.ts')
const observations=[]
for(const config of [{},{models:[{id:'custom',name:'Custom',systemPromptUpdate:'in-history'}]}]){
 const ctx=new Context()
 try{
  await ctx.plugin(api.default)
  await ctx.plugin(provider,config)
  const catalog=await ctx.llm.listModels('deepseek-official'),resolved=[],prepared=[]
  for(const row of [...catalog,{id:'unlisted'}]){
   resolved.push(await ctx.llm.resolveModelInfo('deepseek-official',row.id))
   const call=await ctx.llm.prepareCall({provider:'deepseek-official',model:row.id})
   prepared.push(Object.fromEntries(Object.entries(call).filter(([key])=>key!=='stream')))
  }
  observations.push({catalog,resolved,prepared})
 }finally{await ctx.fiber.dispose()}
}
if(pin()!=='a4c74a91e06b00fe0b0937bde982170c526cc842')throw new Error('Source changed during observation')
writeFileSync(join(output,'source.json'),JSON.stringify({pin:pin(),node:process.version,models:provider.Config({}).models,observations},null,2)+'\n','utf8')

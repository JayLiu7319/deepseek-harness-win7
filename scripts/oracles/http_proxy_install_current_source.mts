import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
export async function httpProxyInstallCase(source:string,test:any){
 const load=(p:string)=>import(pathToFileURL(join(source,p)).href),api=await load('packages/util/http-proxy/src/index.ts'),{PROXY_ENV_NAMES}=await load('packages/util/http-proxy/src/policy.ts'),{scrubbedParentEnv}=await load('packages/subprocess/subprocess/src/index.ts')
 const original={...process.env};for(const key of Object.keys(process.env))delete process.env[key];Object.assign(process.env,test.ambient??{})
 const snapshot=()=>Object.fromEntries(PROXY_ENV_NAMES.map((key:string)=>[key,process.env[key]??null])),initial=JSON.stringify(snapshot()),stages:any[]=[],disposers:any[]=[]
 const observe=(reported:string[])=>{let child=scrubbedParentEnv();if(process.platform==='win32')child=Object.fromEntries(Object.entries(child).map(([key,value])=>[key.toUpperCase(),value]));return{reported,routes:test.urls.map((url:string)=>{const route=api.proxyRouteFor(new URL(url));return route.proxied?{proxied:true,proxy:route.proxy}:{proxied:false}}),overlay:Object.fromEntries(Object.entries(api.proxyEnvironmentForChild()).map(([key,value])=>[key,value??null])),published:snapshot(),child}}
 try{
  for(const values of test.installs){const reported:string[]=[];disposers.push(await api.installProxyFromEnvironment({get:(name:string)=>name in values?{value:values[name]}:undefined},(s:string)=>reported.push(s)));stages.push(observe(reported))}
  while(disposers.length){await disposers.pop()();stages.push(observe([]))}
  return{stages,restored:JSON.stringify(snapshot())===initial,cleared:Object.fromEntries(Object.entries(api.clearedProxyEnv()).map(([key,value])=>[key,value??null]))}
 }finally{while(disposers.length)await disposers.pop()();for(const key of Object.keys(process.env))delete process.env[key];Object.assign(process.env,original)}
}

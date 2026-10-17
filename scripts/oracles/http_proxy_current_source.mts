import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
export async function httpProxyCase(source:string,test:any){
 const api=await import(pathToFileURL(join(source,'packages/util/http-proxy/src/policy.ts')).href)
 if(test.operation==='loopback')return test.hosts.map(api.isLoopbackHost)
 if(test.operation==='bypass')return test.requests.map((c:any)=>api.bypassesProxy(c.noProxy,new URL(c.url)))
 if(test.operation==='supported')return test.urls.map(api.isSupportedProxyUrl)
 const result=api.resolveProxyPolicy({get:(name:string)=>name in (test.env??{})?{value:test.env[name]}:undefined})
 return {...result,routes:(test.urls??[]).map((url:string)=>api.proxyForUrl(result.policy,new URL(url))??null)}
}

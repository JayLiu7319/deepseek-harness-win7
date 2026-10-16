/** JSON-line actor using the actual target's native kernel lease implementation. */
import {createInterface} from 'node:readline'
import {pathToFileURL} from 'node:url'
import {resolve,join} from 'node:path'
const [source]=process.argv.slice(2)
if(!source)throw new Error('Explicit Source checkout required')
const {SessionWriteLease}=await import(pathToFileURL(join(resolve(source),'packages/session/session-persistence-jsonl/src/lease.ts')).href)
const held=new Map<string,any>()
console.log(JSON.stringify({ready:true}))
for await(const line of createInterface({input:process.stdin,crlfDelay:Infinity})) {
 try {
  const command=JSON.parse(line)
  if(command.action==='acquire')held.set(command.slot,await SessionWriteLease.acquire(command.directory,command.id))
  else if(command.action==='release')await held.get(command.slot).release()
  else if(command.action==='exit')break
  else throw new Error('Unknown actor command')
  console.log(JSON.stringify({outcome:'value'}))
 } catch(error:any) {console.log(JSON.stringify({outcome:'error',name:error.name,message:error.message}))}
}
for(const lease of held.values())await lease.release()
process.stdin.destroy()

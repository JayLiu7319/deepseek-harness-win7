/** Actual unchanged rc.3 request/response codecs, including fragmented pipes. */
import {execFileSync} from 'node:child_process'
import {mkdirSync,writeFileSync} from 'node:fs'
import {join,resolve} from 'node:path'
import {pathToFileURL} from 'node:url'
const [sourceArg,outputArg]=process.argv.slice(2)
if(!sourceArg||!outputArg)throw new Error('Source and fresh output required')
const root=resolve(sourceArg),output=resolve(outputArg),pin='a4c74a91e06b00fe0b0937bde982170c526cc842'
const git=(...args:string[])=>execFileSync('git',['-C',root,...args],{encoding:'utf8'}).trim()
if(git('rev-parse','HEAD')!==pin||git('status','--porcelain'))throw new Error('Unchanged rc.3 Source required')
if(process.version!=='v22.22.2')throw new Error('Frozen Node required')
mkdirSync(output)
const shell=await import(pathToFileURL(join(root,'apps/desktop/src/host-protocol.ts')).href)
const host=await import(pathToFileURL(join(root,'apps/desktop-host/src/wire.ts')).href)
const cases:any[]=[]
const json=(value:unknown)=>Buffer.from(JSON.stringify(value))
const frame=(kind:number,id:number,payload=Buffer.alloc(0),length=payload.length,magic=0x44534833)=>{
 const h=Buffer.alloc(13);h.writeUInt32BE(magic);h.writeUInt8(kind,4);h.writeUInt32BE(id,5);h.writeUInt32BE(length,9)
 return Buffer.concat([h,payload])
}
const normalize=(frames:any[])=>frames.map(row=>row.type==='data'?{...row,data:row.data.toString('base64')}:row)
function observe(direction:string,bytes:Buffer,split:number,finish=true){
 const decoder=direction==='request'?new host.DesktopHostRequestDecoder():new shell.DesktopHostResponseDecoder()
 const frames:any[]=[]
 try{
  for(let offset=0;offset<bytes.length;offset+=split)frames.push(...decoder.push(bytes.subarray(offset,offset+split)))
  if(finish)decoder.finish()
  return {frames:normalize(frames)}
 }catch(error:any){return {frames:normalize(frames),error:error.message}}
}
const add=(name:string,direction:string,bytes:Buffer,split=7,finish=true)=>cases.push({case:name,direction,bytes:bytes.toString('base64'),split,finish,expected:observe(direction,bytes,split,finish)})
for(const direction of ['request','response']){
 const start=direction==='request'?shell.encodeDesktopRequestStart(0xffffffff,{url:'dsh-app://app/api/upload?q=中文',method:'POST',headers:[['x-a','一'],['x-a','二']],hasBody:true}):host.encodeDesktopResponseStart(0xffffffff,{status:206,headers:[['x-a','一'],['x-a','二']],hasBody:true})
 const data=Buffer.from(Array.from({length:65536},(_,i)=>i%256))
 const bytes=Buffer.concat([start,frame(2,0xffffffff,data),frame(3,0xffffffff),frame(4,2,direction==='response'?json({message:'故障💾'}):Buffer.alloc(0))])
 for(const split of [1,2,7,12,13,14,257,65536,1048576])add(direction+'-fragments-'+split,direction,bytes,split)
 for(const cut of [1,4,12,13,start.length-1,start.length+14])add(direction+'-truncated-'+cut,direction,bytes.subarray(0,cut),3)
 for(const [name,value] of [['marker',frame(3,1,Buffer.alloc(0),0,0)],['zero-id',frame(3,0)],['data-limit',frame(2,1,Buffer.alloc(0),65537)],['control-limit',frame(1,1,Buffer.alloc(0),1048577)],['unknown',frame(5,1)],['end-payload',frame(3,1,Buffer.from('x'))],['invalid-json',frame(1,1,Buffer.from('{'))],['invalid-start',frame(1,1,json({headers:[],hasBody:false}))]] as const)add(direction+'-'+name,direction,value)
 if(direction==='request')add('request-cancel-payload',direction,frame(4,1,Buffer.from('x')))
 else for(const value of [null,{},[],{message:4}])add('response-invalid-error-'+JSON.stringify(value),direction,frame(4,1,json(value)))
 const base=direction==='request'?{url:'dsh-app://app/',method:'GET',headers:[],hasBody:false}:{status:200,headers:[],hasBody:false}
 for(const headers of [null,{},['a'],[['a']],[[1,'b']],[['a','b','c']]])add(direction+'-headers-'+JSON.stringify(headers),direction,frame(1,1,json({...base,headers})))
 for(const hasBody of [null,0,'false'])add(direction+'-body-'+JSON.stringify(hasBody),direction,frame(1,1,json({...base,hasBody})))
 if(direction==='response')for(const status of [99,600,200.5,true,'200',null])add('response-status-'+JSON.stringify(status),direction,frame(1,1,json({...base,status})))
 add(direction+'-no-finish',direction,bytes.subarray(0,12),1,false)
 add(direction+'-empty-data',direction,Buffer.concat([frame(2,1),frame(3,1)]),13)
 add(direction+'-interleaved',direction,Buffer.concat([frame(1,1,json(base)),frame(1,2,json(base)),frame(2,2,Buffer.from('second')),frame(2,1,Buffer.from('first')),frame(3,2),frame(3,1)]),19)
 if(direction==='response')for(const status of [100,599])add('response-valid-status-'+status,direction,frame(1,1,json({...base,status})))
}
if(git('rev-parse','HEAD')!==pin||git('status','--porcelain'))throw new Error('Source changed')
writeFileSync(join(output,'cases.json'),JSON.stringify(cases,null,2)+'\n',{encoding:'utf8',flag:'wx'})
writeFileSync(join(output,'source.json'),JSON.stringify({pin,node:process.version,cases:cases.length,scope:'Actual unchanged shell/Host codecs; original JSON parser messages retained'},null,2)+'\n',{encoding:'utf8',flag:'wx'})
console.log(JSON.stringify({cases:cases.length,output}))

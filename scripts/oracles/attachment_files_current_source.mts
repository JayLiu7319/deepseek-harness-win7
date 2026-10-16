/** Actual unchanged rc.3 file storage and AttachmentStore methods. */
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
import {tmpdir} from 'node:os'
import {createHash} from 'node:crypto'
import {mkdtemp,rm,chmod,readdir,stat,writeFile} from 'node:fs/promises'

export async function attachmentFilesCase(source:string,test:any){
 const load=(path:string)=>import(pathToFileURL(join(source,path)).href)
 const files=await load('packages/attachment/attachment-local/src/file-store.ts')
 const {AttachmentStore,admitEncodedFile}=await load('packages/attachment/attachment/src/index.ts')
 const {Context}=await load('vendor/cordis/src/index.ts')
 const directory=await mkdtemp(join(tmpdir(),'rc3-files-')),root=join(directory,'attachments','v1')
 const refs:any[]=[],results:any[]=[]
 const failure=(error:any)=>({name:error.name,message:error.message,...('code' in error?{code:error.code}:{})})
 try{
  for(const action of test.actions){
   try{
    const op=action.op;let value:any
    if(op==='name')value=files.fileLeafName(action.value)
    else if(['save','stream','encoded','concurrent'].includes(op)){
     const controller=new AbortController()
     const data=(async function*(){
      for(const [index,item] of (action.chunks??[]).entries()){
       if(index===action.abortAt)controller.abort(new Error('upload cancelled'))
       yield Buffer.from(item as string,'hex')
      }
      if(action.fail)throw new Error('source failed')
     })()
     const input=action.name===undefined?{}:{name:action.name}
     if(op==='encoded')value=await admitEncodedFile({saveFile:(input:any)=>files.saveFileVerbatim(root,input)}, {...input,data:action.data})
     else if(op==='stream')value=await files.saveFileStreamVerbatim(root,{...input,data,signal:controller.signal})
     else if(op==='concurrent'){
      value=await Promise.all(action.names.map((name:string)=>files.saveFileVerbatim(root,{name,data:Buffer.from(action.hex,'hex')})))
      refs.push(...value)
     }else value=await files.saveFileVerbatim(root,{...input,data:action.size===undefined?Buffer.from(action.hex,'hex'):Buffer.from(Array.from({length:action.size},(_,index)=>index%251))})
     if(op!=='concurrent')refs.push(value)
    }else if(op==='path')value=files.storedFilePath(root,action.ref??refs[action.index??0]??{}).replace(root,'<root>').replaceAll('\\','/')
    else if(op==='inspect'){
     const ref=refs[action.index??0],digest=ref.attachmentId.slice(7)
     const facts=await stat(files.storedFilePath(root,ref)),canonical=await stat(join(root,'file-objects',digest.slice(0,2),digest))
     value={sameObject:facts.ino===canonical.ino,readOnly:(facts.mode&0o200)===0,staging:(await readdir(join(root,'tmp'))).sort()}
    }else if(op==='mutate'){
     const path=files.storedFilePath(root,refs[action.index??0]);await chmod(path,0o600);await writeFile(path,Buffer.from(action.hex,'hex'));value=true
    }else if(op==='read'||op==='readMissing'){
     const ref={...(action.ref??refs[action.index??0]??{}),...(action.bytes===undefined?{}:{bytes:action.bytes})}
     const controller=new AbortController();if(action.before)controller.abort(new Error('read cancelled'))
     const chunks:Buffer[]=[];let maxChunk=0
     try{
      for await(const chunk of files.readFileStreamVerbatim(root,ref,controller.signal)){
       chunks.push(chunk);maxChunk=Math.max(maxChunk,chunk.byteLength)
       if(action.during)controller.abort(new Error('read cancelled'))
      }
      const data=Buffer.concat(chunks)
      value=action.summary?{digest:createHash('sha256').update(data).digest('hex'),bytes:data.byteLength,maxChunk}:{hex:data.toString('hex'),maxChunk}
     }catch(error){value={error:failure(error),delivered:Buffer.concat(chunks).toString('hex')}}
    }else if(op==='staging')value=await readdir(join(root,'tmp')).then(items=>items.sort(),()=>[])
    else if(op==='base'){
     class Base extends AttachmentStore{
      inputs:any[]=[]
      async saveImages(inputs:any[]){this.inputs=inputs;return inputs.map((_,index)=>({attachmentId:'image-'+index}))}
     }
     const base=new Base(new Context())
     if(action.method==='admitPromptContent'){
      value={content:await base.admitPromptContent(action.content),images:base.inputs.map(item=>({...item,data:Buffer.from(item.data).toString('hex')}))}
     }else if(action.method==='readFileStream'){
      value=[];for await(const chunk of base.readFileStream({} as any))value.push(chunk)
     }else value=await (base as any)[action.method]({})
    }else throw new Error('Unknown file action: '+op)
    results.push({outcome:'value',value})
   }catch(error){results.push({outcome:'error',error:failure(error)})}
  }
  return {results}
 }finally{await rm(directory,{recursive:true,force:true})}
}

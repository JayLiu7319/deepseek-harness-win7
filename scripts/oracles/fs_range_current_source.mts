import {mkdtemp,writeFile,mkdir,rm} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import {pathToFileURL} from 'node:url'
export async function fsRangeCase(source:string,test:any){
 const {LocalFileSystem}=await import(pathToFileURL(`${source}/packages/fs/fs-local/src/index.ts`).href)
 const {Context}=await import(pathToFileURL(`${source}/vendor/cordis/src/index.ts`).href)
 const root=await mkdtemp(join(tmpdir(),'rc3-byte-range-')),ctx=new Context(),controller=new AbortController()
 try{
  await writeFile(join(root,'file.bin'),Buffer.concat(Array.from({length:test.repeat??1},()=>Buffer.from(test.data??'','base64'))));await mkdir(join(root,'directory'))
  const fs=new LocalFileSystem(ctx,{diffBasisMaxBytes:10*1024*1024}),target=await fs.resolve(test.path??'file.bin',{cwd:root})
  if(test.aborted)controller.abort()
  try{const data=await fs.readByteRange(target,test.range,controller.signal);return {data:Buffer.from(data).toString('base64'),bytes:data.length}}
  catch(error:any){return {error:{message:error.message.replaceAll(root,'<root>'),code:error.code??null}}}
 }finally{await ctx.fiber.dispose();await rm(root,{recursive:true,force:true})}
}

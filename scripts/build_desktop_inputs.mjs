/** Reproduce the unmodified rc.3 shell codec, locale, renderer and transport. */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile,writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {resolve,join} from 'node:path';
import {execFileSync} from 'node:child_process';
const options=Object.fromEntries(process.argv.slice(2).reduce((rows,value,index,args)=>{
  if(value.startsWith('--'))rows.push([value.slice(2),args[index+1]]);return rows;
},[]));
assert.ok(options.source&&options.esbuild,'Explicit clean Source checkout and esbuild package required');
const root=resolve(import.meta.dirname,'..'),source=resolve(options.source);
const commit='a4c74a91e06b00fe0b0937bde982170c526cc842';
assert.equal(execFileSync('git',['-C',source,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),commit);
assert.equal(execFileSync('git',['-C',source,'status','--porcelain','--untracked-files=no'],{encoding:'utf8'}).trim(),'');
const esbuild=createRequire(import.meta.url)(resolve(options.esbuild));
assert.equal(esbuild.version,'0.25.12');
const hash=value=>createHash('sha256').update(value).digest('hex');
const inputs=[];
async function publish(path,bytes,original){
  bytes=Buffer.from(bytes);
  if(options.check==='true')assert.deepEqual(await readFile(join(root,path)),bytes,path+' differs from frozen Source');
  else await writeFile(join(root,path),bytes);
  inputs.push({source:original.path,sourceSha256:hash(original.bytes),target:path,sha256:hash(bytes)});
}
for(const [name,target] of [['host-protocol','wire'],['locale','locale']]){
  const path='apps/desktop/src/'+name+'.ts',bytes=await readFile(join(source,path));
  const result=await esbuild.transform(bytes.toString('utf8'),{loader:'ts',format:'cjs',target:'node16.17'});
  await publish('apps/desktop/'+target+'.cjs',result.code,{path,bytes});
}
for(const extension of ['js','html','css']){
  const path='apps/desktop/renderer/plugin-manager.'+extension,bytes=await readFile(join(source,path));
  await publish(path,bytes,{path,bytes});
}
{
  const path='apps/desktop-host/src/index.ts',bytes=await readFile(join(source,path));
  const original=bytes.toString('utf8').replaceAll('\r\n','\n');
  const match=original.match(/const DESKTOP_TRANSPORT_SCRIPT = `([\s\S]*?)`/u);
  assert.ok(match,'Original transport literal missing');
  const script=match[1].replace('${JSON.stringify(DESKTOP_STREAM_PATH)}',JSON.stringify('/.dsh/remote-stream')).replaceAll('\\\\n','\\n')+'\n';
  assert.ok(!script.includes('${'),'Unexpected template expression in transport');
  await publish('apps/desktop-host/transport.js',script,{path,bytes});
}
const manifest={sourceCommit:commit,builder:{name:'esbuild',version:esbuild.version,target:'node16.17',format:'cjs'},
  transportExtraction:'Original template with constant stream path and escaped newline evaluated; no browser application edits',inputs};
const data=JSON.stringify(manifest,null,2)+'\n';
if(options.check==='true')assert.equal(await readFile(join(root,'apps/desktop/source-input.json'),'utf8'),data);
else await writeFile(join(root,'apps/desktop/source-input.json'),data);
console.log(JSON.stringify({status:options.check==='true'?'verified':'built',inputs:inputs.length}));

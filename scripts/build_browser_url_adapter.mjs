/** Rebuild the host URL/PDF capability adapter from pinned development inputs. */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile,writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {dirname,join,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const options=Object.fromEntries(process.argv.slice(2).reduce((rows,value,index,args)=>{
  if(value.startsWith('--'))rows.push([value.slice(2),args[index+1]]);return rows;
},[]));
assert.ok(options.source&&options.esbuild,'Explicit core-js package and esbuild package paths required');
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const source=resolve(options.source),builder=resolve(options.esbuild);
const require=createRequire(import.meta.url),esbuild=require(builder);
const packageValue=JSON.parse(await readFile(join(source,'package.json'),'utf8'));
assert.equal(packageValue.name,'core-js');assert.equal(packageValue.version,'3.49.0');
assert.equal(esbuild.version,'0.25.12');
const npm=JSON.parse(await readFile(join(source,'../npm-input.json'),'utf8'));
assert.equal(npm.version,'3.49.0');
const entry=join(root,'dsh/host/browser_compat/url-entry.cjs');
const result=await esbuild.build({entryPoints:[entry],bundle:true,write:false,metafile:true,platform:'browser',
  format:'iife',target:'chrome108',minify:true,legalComments:'inline',
  banner:{js:'/* Host URL/PDF capabilities: core-js 3.49.0, MIT, Denis Pushkarev. See url.LICENSE.txt and url-input.json. */'},
  plugins:[{name:'pinned-core-js-url',setup(build){
    build.onResolve({filter:/^core-js\//},args=>({path:join(source,args.path.slice('core-js/'.length)+'.js')}));
    // The outer capability predicate owns selection. Force the full parser in
    // this bundle, rather than core-js's unrelated native URL feature tests.
    build.onLoad({filter:/[/\\]internals[/\\]url-constructor-detection\.js$/},()=>({contents:'module.exports = false;',loader:'js'}));
  }}]});
const hash=value=>createHash('sha256').update(value).digest('hex');
const inputs=[];
for(const name of Object.keys(result.metafile.inputs).sort()){
  const path=resolve(name),data=await readFile(path);
  inputs.push({path:path===entry?'url-entry.cjs':relative(source,path).replaceAll('\\','/'),
    sha256:hash(path===entry?Buffer.from(data.toString('utf8').replaceAll('\r\n','\n')):data)});
}
const output=result.outputFiles[0].contents;
const manifest={schema:1,package:'core-js',version:packageValue.version,license:'MIT',
  source:'https://github.com/zloirock/core-js/tree/v3.49.0',npm,
  build:{esbuild:esbuild.version,target:'chrome108',format:'iife',minify:true,
    override:'internals/url-constructor-detection.js exports false; runtime predicate selects the fallback'},
  inputs,output:{path:'url.js',sha256:hash(output),bytes:output.length},
  licenseSha256:hash(await readFile(join(source,'LICENSE')))};
const directory=join(root,'dsh/host/browser_compat');
if(options.check==='true'){
  assert.deepEqual(await readFile(join(directory,'url.js')),Buffer.from(output));
  assert.deepEqual(JSON.parse(await readFile(join(directory,'url-input.json'),'utf8')),manifest);
  assert.deepEqual(await readFile(join(directory,'url.LICENSE.txt')),await readFile(join(source,'LICENSE')));
}else{
  await writeFile(join(directory,'url.js'),output);
  await writeFile(join(directory,'url.LICENSE.txt'),await readFile(join(source,'LICENSE')));
  await writeFile(join(directory,'url-input.json'),JSON.stringify(manifest,null,2)+'\n','utf8');
}
console.log(JSON.stringify({passed:true,check:options.check==='true',...manifest.output,inputs:inputs.length}));

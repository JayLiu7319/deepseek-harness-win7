'use strict';
// Real Node16/Python3.8 pipe, cancellation and Windows process-tree ownership.
const assert=require('node:assert/strict');
const {resolve,join}=require('node:path');
const {mkdir,writeFile}=require('node:fs/promises');
const root=resolve(__dirname,'../..');
const options=Object.fromEntries(process.argv.slice(2).reduce((rows,value,index,args)=>{
  if(value.startsWith('--'))rows.push([value.slice(2),args[index+1]]);return rows;
},[]));
assert.ok(options.output&&options.python,'Explicit fresh output and Python interpreter required');
const {DesktopHostProcess}=require(join(options['shell-dir']?resolve(options['shell-dir']):join(root,'apps/desktop'),'host-process.cjs'));
const output=resolve(options.output),report={versions:process.versions,checks:[]};
const hostOptions={python:resolve(options.python),root:options.root?resolve(options.root):root,home:join(output,'home'),profile:join(output,'profile')};
let host;
async function read(response){const chunks=[];for await(const chunk of response.body)chunks.push(chunk);return Buffer.concat(chunks);}
async function run(){
  await mkdir(output,{recursive:true});
  try{
    host=new DesktopHostProcess(hostOptions);
    report.ready=await host.start();assert.equal(report.ready.protocolVersion,3);
    const index=await host.fetch({url:'dsh-app://app/index.html'});
    const html=(await read(index)).toString('utf8');
    assert.equal(index.status,200);assert.ok(html.includes('__DSH_TRANSPORT__'));report.checks.push('original-index');
    const heads=await Promise.all(Array.from({length:12},()=>host.fetch({url:'dsh-app://app/index.html',method:'HEAD'})));
    for(const row of heads){assert.equal(row.status,200);assert.equal((await read(row)).length,0);}
    report.checks.push('interleaved-12-heads');
    const body=JSON.stringify({type:'client-request',rpcId:'pipe',method:'settings/describe',payload:{args:{}}});
    const rpc=await host.fetch({url:'dsh-app://app/api/settings/describe',method:'POST',headers:[['content-type','application/json']],body});
    const settings=JSON.parse((await read(rpc)).toString('utf8'));
    assert.equal(settings.result.ok,true);assert.ok(settings.result.value.namespaces.length);report.checks.push('actual-typert-rpc');
    const upload=await host.fetch({url:'dsh-app://app/api/missing',method:'POST',headers:[['content-type','application/json']],body:Buffer.alloc(2*1024*1024,32)});
    assert.equal(upload.status,404);await read(upload);report.checks.push('2MiB-request-with-64KiB-frames');
    const controller=new AbortController();
    const stream=await host.fetch({url:'dsh-app://app/.dsh/remote-stream',method:'POST',headers:[['content-type','application/json']],
      body:JSON.stringify({endpoint:'workspace/follow',payload:{args:{}}}),signal:controller.signal});
    assert.equal(stream.status,200);
    const first=await new Promise((resolve,reject)=>{stream.body.once('data',resolve);stream.body.once('error',reject);});
    assert.equal(JSON.parse(first.toString('utf8').trim()).type,'baseline');
    controller.abort();assert.equal(stream.body.destroyed,true);report.checks.push('live-stream-baseline-and-abort');
    const invalid=await host.fetch({url:'dsh-app://evil/'});assert.equal(invalid.status,403);await read(invalid);
    report.checks.push('unowned-origin-rejection');
    assert.equal(host.pending.size,0);report.checks.push('no-pending-streams');
    const killed=host;
    killed.terminate();report.killedExit=await killed.exit;assert.notEqual(report.killedExit,0);
    host=new DesktopHostProcess(hostOptions);
    await host.start();const cold=await host.fetch({url:'dsh-app://app/index.html',method:'HEAD'});
    assert.equal(cold.status,200);await read(cold);report.checks.push('forced-process-tree-exit-releases-profile');
    report.exit=await host.stop();assert.equal(report.exit,0);report.checks.push('EOF-normal-shutdown');
    report.status='qualified';
  }catch(error){report.status='rejected';report.failure=error.stack;process.exitCode=1;}
  finally{
    report.logs=host?.logs;
    await host?.stop().catch(()=>{});
    await writeFile(join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify({status:report.status,checks:report.checks,failure:report.failure}));
  }
}
run().catch(error=>{console.error(error);process.exitCode=1;});

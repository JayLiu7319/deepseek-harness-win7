'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {EventEmitter}=require('node:events');
const {resolve}=require('node:path');
const protection=resolve(__dirname,'../../apps/desktop/stdio.cjs');
const {protectStdio}=require(protection);
const stream=new EventEmitter();protectStdio([stream]);
stream.emit('error',Object.assign(new Error('closed'),{code:'EPIPE'}));
const unrelated=Object.assign(new Error('unrelated failure'),{code:'EIO'});
assert.throws(()=>stream.emit('error',unrelated),error=>error===unrelated);
const code=`
  require(${JSON.stringify(protection)}).protectStdio();
  for(const name of ['stdout','stderr'])process[name].on('error',error=>process.send({phase:'pipe-error',stream:name,code:error.code}));
  process.send({phase:'ready',node:process.versions.node});
  process.once('message',()=>{
    for(let i=0;i<20;i++){console.warn('closed diagnostic '+i);console.log('closed output '+i);}
    setTimeout(()=>{process.send({phase:'continued'});process.disconnect();},200);
  });`;
const child=spawn(process.argv[2],['-e',code],{windowsHide:true,
  env:{...process.env,ELECTRON_RUN_AS_NODE:'1'},stdio:['ignore','pipe','pipe','ipc']});
const timer=setTimeout(()=>{child.kill();throw new Error('Closed pipe child deadline');},10000);
const observations=[];
child.on('message',message=>{
  observations.push(message);
  if(message.phase==='ready'){
    child.stdout.destroy();child.stderr.destroy();
    // Let Windows observe that both readers have closed before writing.
    setTimeout(()=>child.send('write'),200);
  }
});
child.on('error',error=>{throw error;});
child.on('exit',(code,signal)=>{
  clearTimeout(timer);assert.equal(code,0);assert.equal(signal,null);
  assert.equal(observations[0].phase,'ready');
  assert.equal(observations[observations.length-1].phase,'continued');
  for(const name of ['stdout','stderr'])assert.ok(observations.some(row=>row.phase==='pipe-error'&&row.stream===name&&row.code==='EPIPE'));
  assert.match(observations[0].node,/^16\./);
  console.log(JSON.stringify({status:'qualified',checks:['actual-closed-stdout','actual-closed-stderr','unrelated-error-rethrown'],observations}));
});

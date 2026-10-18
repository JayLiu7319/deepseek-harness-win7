'use strict';
// Owned HTTPS publication rehearsal using a real Standard installer. The key is
// ephemeral and never embedded in a release. Actual public/LAN deployment is a
// separate operation requiring the operator's address, CA and permanent key.
const fs=require('node:fs/promises');
const {createReadStream}=require('node:fs');
const https=require('node:https');
const {createHash,generateKeyPairSync,sign}=require('node:crypto');
const {spawn}=require('node:child_process');
const {join,resolve,dirname}=require('node:path');
const assert=require('node:assert/strict');
const {Win7Updater,installerHandoff}=require('../apps/desktop/updates.cjs');
const options=Object.fromEntries(process.argv.slice(2).reduce((rows,value,i,all)=>{if(value.startsWith('--'))rows.push([value.slice(2),all[i+1]]);return rows;},[]));
async function execute(binary,args,env,log){
  const child=spawn(binary,args,{windowsHide:true,env,stdio:['ignore','pipe','pipe']});let stdout='',stderr='';
  child.stdout.on('data',data=>stdout+=data.toString());child.stderr.on('data',data=>stderr+=data.toString());
  const timer=setTimeout(()=>child.kill(),180000);
  const code=await new Promise((done,reject)=>{child.once('error',reject);child.once('exit',done);});clearTimeout(timer);
  await fs.writeFile(log,JSON.stringify({binary,args,exitCode:code,stdout,stderr},null,2)+'\n',{flag:'wx'});return {code,stdout,stderr,pid:child.pid};
}
async function client(){
  assert.equal(process.versions.node,'16.17.1');
  const config=JSON.parse(await fs.readFile(options.config,'utf8'));
  const updater=new Win7Updater({config,currentVersion:'0.1.5-rc.2',temp:options.output});
  if(options.expect==='untrusted'){
    await assert.rejects(updater.checkForUpdates(),/self signed certificate/);
    await fs.writeFile(join(options.output,'client.json'),JSON.stringify({status:'passed',check:'reject-untrusted-private-CA',versions:process.versions})+'\n');return;
  }
  assert.equal((await updater.checkForUpdates()).isUpdateAvailable,true);
  await updater.downloadUpdate();
  const bytes=await fs.readFile(updater.download.file);assert.equal(createHash('sha256').update(bytes).digest('hex'),options.sha256);
  // Exercise the actual PowerShell handoff rejection before any UAC launch.
  const ended=await execute('cmd.exe',['/c','exit','0'],process.env,join(options.output,'exited-parent.json'));
  const failure=installerHandoff(updater.download.file,'0'.repeat(64),ended.pid,join(options.output,'tampered-handoff.log'));
  const rejected=await execute(failure.binary,failure.args,process.env,join(options.output,'handoff-process.json'));
  assert.equal(rejected.code,1);assert.match(await fs.readFile(join(options.output,'tampered-handoff.log'),'utf8'),/Downloaded installer changed before launch/);
  await fs.writeFile(join(options.output,'client.json'),JSON.stringify({status:'passed',versions:process.versions,
    checks:['actual-explicit-private-CA','independent-ed25519-envelope','actual-installer-HTTPS-download-and-SHA','actual-PowerShell-handoff-rejects-changed-bytes'],
    downloadedInstaller:updater.download.file,sha256:options.sha256,installationExecuted:false},null,2)+'\n');
}
async function main(){
  if(options.client)return client();
  for(const name of ['installer','electron','output'])assert.ok(options[name],name);
  const output=resolve(options.output);await fs.mkdir(output);
  const installer=resolve(options.installer),identity=await fs.readFile(installer),sha256=createHash('sha256').update(identity).digest('hex');
  const filename=installer.split(/[\\/]/).pop();assert.match(filename,/^dsh-desktop-standard-setup-v0\.1\.5-rc\.3-(x64|x86)\.exe$/);
  const architecture=filename.endsWith('-x86.exe')?'x86':'x64';
  const keys=generateKeyPairSync('ed25519'),tls=join(__dirname,'../tests/fixtures/tls');let envelope;
  const server=https.createServer({key:await fs.readFile(join(tls,'localhost-key.pem')),cert:await fs.readFile(join(tls,'localhost-cert.pem'))},(request,response)=>{
    if(request.url==='/feed.json'){response.setHeader('content-type','application/json');response.end(envelope);}
    else if(request.url==='/'+filename){response.setHeader('content-length',identity.length);createReadStream(installer).pipe(response);}
    else{response.writeHead(404);response.end();}
  });
  const report={status:'running',scope:'Local HTTPS publication rehearsal; not an operator LAN/public feed',installer,sha256,architecture,installationExecuted:false};
  try{
    await new Promise(done=>server.listen(0,'127.0.0.1',done));const base='https://127.0.0.1:'+server.address().port,now=Date.now();
    const payload=Buffer.from(JSON.stringify({schemaVersion:1,channel:'win7-electron22',version:'0.1.5-rc.3',architecture,electron:'22.3.27',python:'3.8.10',publishedAt:now-1000,expiresAt:now+3600000,artifact:{url:base+'/'+filename,bytes:identity.length,sha256}}));
    envelope=Buffer.from(JSON.stringify({payload:payload.toString('base64'),signature:sign(null,payload,keys.privateKey).toString('base64')}));
    await fs.writeFile(join(output,'signed-feed.json'),envelope);
    const configuration=join(output,'configuration.json');await fs.writeFile(configuration,JSON.stringify({schemaVersion:1,channel:'win7-electron22',manifestUrl:base+'/feed.json',publicKey:keys.publicKey.export({type:'spki',format:'pem'})},null,2));
    for(const mode of ['untrusted','trusted']){
      const folder=join(output,mode);await fs.mkdir(folder);const env={...process.env,ELECTRON_RUN_AS_NODE:'1'};delete env.NODE_TLS_REJECT_UNAUTHORIZED;delete env.NODE_EXTRA_CA_CERTS;
      if(mode==='trusted'){
        const config=JSON.parse(await fs.readFile(configuration,'utf8'));config.caCertificate=await fs.readFile(join(tls,'localhost-cert.pem'),'utf8');
        await fs.writeFile(configuration,JSON.stringify(config,null,2));
      }
      const result=await execute(resolve(options.electron),[__filename,'--client','true','--expect',mode,'--config',configuration,'--output',folder,'--sha256',sha256],env,join(output,mode+'-process.json'));
      assert.equal(result.code,0,result.stderr);report[mode]=JSON.parse(await fs.readFile(join(folder,'client.json'),'utf8'));
    }
    report.status='passed';
  }catch(error){report.status='failed';report.failure=error.stack;process.exitCode=1;}
  finally{await new Promise(done=>server.close(done));await fs.writeFile(join(output,'report.json'),JSON.stringify(report,null,2)+'\n');}
  console.log(JSON.stringify({status:report.status,architecture,sha256,failure:report.failure}));
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});

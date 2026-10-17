'use strict';
// Release operator tool. The private Ed25519 key stays outside the repository.
const {readFile,writeFile,stat}=require('node:fs/promises');
const {createHash,createPrivateKey,createPublicKey,sign}=require('node:crypto');
const {basename}=require('node:path');
const {signedRelease,configuration}=require('../apps/desktop/updates.cjs');
async function main(){
  const args=process.argv.slice(2);
  if(args.length%2)throw new Error('Arguments require --name value pairs');
  const options={};for(let i=0;i<args.length;i+=2){if(!args[i].startsWith('--')||args[i] in options)throw new Error('Invalid or duplicate argument');options[args[i]]=args[i+1];}
  const required=['--installer','--version','--artifact-url','--manifest-url','--private-key','--output'];
  const architecture=options['--architecture']||'x64';delete options['--architecture'];
  if(!['x64','x86'].includes(architecture))throw new Error('Unsupported installer architecture');
  if(Object.keys(options).sort().join('\0')!==required.sort().join('\0'))throw new Error('Required: '+required.join(' '));
  const key=createPrivateKey(await readFile(options['--private-key']));
  if(key.asymmetricKeyType!=='ed25519')throw new Error('External Ed25519 private key required');
  const file=options['--installer'];
  if(basename(file)!=='dsh-desktop-standard-setup-v'+options['--version']+'-'+architecture+'.exe')throw new Error('Select the exact built Win7 Standard installer');
  const metadata=await stat(file);if(!metadata.isFile()||metadata.size>1024**3)throw new Error('Invalid installer file');
  const hash=createHash('sha256');for await(const chunk of require('node:fs').createReadStream(file))hash.update(chunk);
  const now=Date.now(),release={schemaVersion:1,channel:'win7-electron22',version:options['--version'],architecture,electron:'22.3.27',python:'3.8.10',publishedAt:now,expiresAt:now+30*86400000,
    artifact:{url:options['--artifact-url'],bytes:metadata.size,sha256:hash.digest('hex')}};
  const payload=Buffer.from(JSON.stringify(release));const envelope=Buffer.from(JSON.stringify({payload:payload.toString('base64'),signature:sign(null,payload,key).toString('base64')})+'\n');
  const config=configuration({schemaVersion:1,channel:'win7-electron22',manifestUrl:options['--manifest-url'],publicKey:createPublicKey(key).export({format:'pem',type:'spki'})});
  signedRelease(envelope,config,'0.0.0',now,architecture);
  await writeFile(options['--output'],envelope,{flag:'wx'});
  process.stdout.write(JSON.stringify({output:options['--output'],version:release.version,bytes:release.artifact.bytes,sha256:release.artifact.sha256})+'\n');
}
main().catch(error=>{process.stderr.write(error.message+'\n');process.exitCode=1;});

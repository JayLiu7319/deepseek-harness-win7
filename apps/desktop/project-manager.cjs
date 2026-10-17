'use strict';
const {spawn}=require('node:child_process');
const {DesktopHostProcess}=require('./host-process.cjs');
class DesktopProjectManager{
  constructor(options){this.options=options;this.tail=Promise.resolve();}
  async start(recover=true){
    if(recover)await this.command('recover');
    this.host=new DesktopHostProcess(this.options);await this.host.start();return this.host;
  }
  command(operation,value,name){
    const {python,root,profile,home}=this.options;
    return new Promise((resolve,reject)=>{
      const args=['-m','dsh.host.desktop.plugins','--profile-dir',profile,'--home',home,'--operation',operation];
      if(value!==undefined)args.push('--value',value);if(name!==undefined)args.push('--name',name);
      const child=spawn(python,args,{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
      let stdout='',stderr='',size=0;
      const timer=setTimeout(()=>{child.kill();reject(new Error('Desktop package transaction timed out'));},120000);
      for(const [stream,add] of [[child.stdout,text=>{stdout+=text;}],[child.stderr,text=>{stderr+=text;}]]){
        stream.on('data',chunk=>{size+=chunk.length;if(size>1024*1024){child.kill();reject(new Error('Desktop package diagnostics exceeded limit'));}else add(chunk.toString('utf8'));});
      }
      child.once('error',error=>{clearTimeout(timer);reject(error);});
      child.once('exit',code=>{
        clearTimeout(timer);
        if(code!==0){reject(new Error(stderr.trim()||'Desktop package operation failed'));return;}
        try{resolve(JSON.parse(stdout));}catch(error){reject(error);}
      });
    });
  }
  list(){return this.command('list');}
  mutate(operation,value,name){
    const job=this.tail.then(async()=>{
      const previous=await this.list();
      await this.host.stop();
      try{
        await this.command(operation,value,name);
        await this.start(false);
        await this.command('commit');
      }catch(error){
        await this.host?.stop().catch(()=>{});
        try{await this.start();}
        catch(rollbackError){throw new Error(error.message+'; recovery failed: '+rollbackError.message);}
        throw error;
      }
      return {previous,current:await this.list()};
    });
    this.tail=job.catch(()=>{});return job;
  }
  async close(){await this.tail;await this.host?.stop();}
}
module.exports={DesktopProjectManager};

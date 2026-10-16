/** Replay captured detached Session prefixes with the exact observed clock reads. */
export function sessionRuntimeCase(api:any,test:any,decode:(value:any)=>any) {
 const outcome=(run:()=>any)=>{try{return {outcome:'value',value:run()??null}}catch(e:any){return {outcome:'error',name:e.name,message:e.message,...(e.cause?{cause:e.cause.message}:{})}}}
 if(test.operation==='function')return outcome(()=>api[test.name](...decode(test.args)))
 function timed(clock:number[],run:()=>any){let index=0;const now=Date.now;Date.now=()=>{if(index>=clock.length)throw new Error('recorded Session clock exhausted');return clock[index++]!};try{return outcome(run)}finally{Date.now=now}}
 let session:any
 const hasOwn=Object.hasOwn
 if(test.fault)Object.hasOwn=(value:any,key:any)=>{if(value?.op==='replace')throw test.fault.nativeError?new Error(test.fault.message):test.fault.message;return hasOwn(value,key)}
 let last:any
 try{last=timed(test.constructor.clock,()=>{session=api.Session[test.constructor.method](...decode(test.constructor.args));return null})}
 finally{Object.hasOwn=hasOwn}
 if(!session)return {last}
 for(const action of test.actions)last=timed(action.clock,()=>session[action.method](...decode(action.args)))
 return {last,state:{header:session.header,firstLiveSeq:session.firstLiveSeq,inheritedEventCount:session.inheritedEventCount,seq:session.seq,events:session.snapshotEvents()}}
}

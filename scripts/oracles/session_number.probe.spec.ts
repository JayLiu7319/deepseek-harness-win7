import {it} from 'vitest'
import {Session} from '@deepseek-ai/dsh-session'
import {writeFileSync} from 'node:fs'
import {execFileSync} from 'node:child_process'

it('observes actual public Session header and seed number boundaries',()=>{
  const pin='a66e4702047846cdaa10c66c9d3df3951f5ea70d'
  if(process.version!=='v22.22.2'||execFileSync('git',['-C','reference','rev-parse','HEAD'],{encoding:'utf8'}).trim()!==pin
    ||execFileSync('git',['-C','reference','status','--porcelain'],{encoding:'utf8'}).trim())throw new Error('Pinned clean Source required')
  const rows:any[]=[]
  for(const field of ['version','createdAt','seedLength','delegationDepth','seq','time']){
    for(const [label,number] of [['whole',field==='version'||field==='seq'?0:1],['negative-zero',-0],
      ['fraction',0.5],['negative',-1],['boolean',false],['unsafe',9007199254740992],['nan',NaN],['infinite',Infinity]] as const){
      const header:any={id:'s',version:0,createdAt:1,isSeeded:false}
      const event:any={type:'session/end-seed',seq:0,time:1,data:{}}
      if(field==='seq'||field==='time')event[field]=number
      else header[field]=number
      const row:any={name:field+'/'+label}
      try{
        const session=Session.create('s' as any,[event],header)
        row.header=session.header
        row.events=session.snapshotEvents()
        row.accepted=true
      }catch(error:any){row.error={name:error.name,message:error.message};row.accepted=false}
      rows.push(row)
    }
  }
  for(const action of ['unknown-field','header-mutation','nested-header-mutation','shallow-copy','deep-copy']){
    const header:any={id:'s',version:0,createdAt:1,isSeeded:false,extra:{nested:[1,2]}}
    const session=Session.create('s' as any,[],header)
    const row:any={name:action}
    if(action==='header-mutation'){
      try{(session.header as any).createdAt=9;row.mutationAccepted=true}catch{row.mutationAccepted=false}
    }else if(action==='nested-header-mutation'){
      try{(session.header as any).extra.nested.push(3);row.mutationAccepted=true}catch{row.mutationAccepted=false}
    }else if(action==='shallow-copy'||action==='deep-copy'){
      const clone:any=action==='shallow-copy'?{...session.header}:structuredClone(session.header)
      try{clone.createdAt=9;row.topMutationAccepted=true}catch{row.topMutationAccepted=false}
      try{clone.extra.nested.push(3);row.nestedMutationAccepted=true}catch{row.nestedMutationAccepted=false}
      row.clone=clone
    }
    row.header=session.header
    row.input=header
    rows.push(row)
  }
  writeFileSync(process.env.DSH_SESSION_NUMBER_SOURCE_OUTPUT!,JSON.stringify({sourceCommit:pin,node:process.version,rows},null,2)+'\n',{encoding:'utf8',flag:'wx'})
})

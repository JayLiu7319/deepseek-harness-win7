"""Current handle ownership counterpart to the pinned Source observations."""
import asyncio,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dsh.cordis.context import Context
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.core.abort import AbortController
from dsh.session.jsonl_backend_current import CurrentJsonlSessionPersistencePlugin

async def observe():
 rows=[]
 for mode in ['reuse','mutated-release','reserved-write','cancel-wait','revision']:
  with tempfile.TemporaryDirectory() as root:
   ctx=Context()
   try:
    await ctx.plugin(CurrentSessionPlugin)
    await ctx.plugin(CurrentJsonlSessionPersistencePlugin,dict(root=root,compression='none'))
    p=ctx.get('sessionPersistence');sid='s'
    initial=await p.create(dict(id=sid,version=3,createdAt=1,delegationDepth=0,isSeeded=False))
    await initial.append([dict(type='turn/start',seq=0,time=1,data=dict(turn=1)),dict(type='turn/end',seq=1,time=2,data=dict(turn=1,reason=dict(kind='completed')))])
    await initial.close()
    first=await p.open(sid,'write');exact=(await first.read())['events']
    if mode=='revision':
     before=await p.stat(sid)
     await first.append([dict(type='turn/start',seq=2,time=3,data=dict(turn=2))])
     after=await p.stat(sid)
     rows.append(dict(mode=mode,changed=before['revision']!=after['revision'],types=[e['type'] for e in (await first.read())['events']]))
    elif mode=='reserved-write':
     rejected=False
     try:await p.open(sid,'write')
     except ValueError:rejected=True
     reader=await p.open(sid,'read')
     rows.append(dict(mode=mode,rejected=rejected,physical=len((await reader.read())['events'])))
     await reader.close()
    elif mode=='cancel-wait':
     controller=AbortController();reason=ValueError('cancel observer');controller.abort(reason)
     cancelled=False
     try:await p.open(sid,'write',dict(signal=controller.signal))
     except ValueError as error:cancelled=error is reason
     await first.close();second=await p.open(sid,'write')
     rows.append(dict(mode=mode,cancelled=cancelled,types=[e['type'] for e in (await second.read())['events']]))
     await second.close()
    else:
     if mode=='mutated-release':exact.append(dict(type='turn/start',seq=2,time=3,data=dict(turn=2)))
     await first.close();second=await p.open(sid,'write')
     rows.append(dict(mode=mode,same=second is first,types=[e['type'] for e in (await second.read())['events']]))
     await second.close()
    await first.close()
   finally:await ctx.fiber.dispose()
 return rows
if __name__=='__main__':Path(sys.argv[1]).write_text(json.dumps(asyncio.run(observe()),indent=2)+'\n',encoding='utf-8')

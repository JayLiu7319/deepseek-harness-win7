import asyncio,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dsh.cordis.context import Context
from dsh.core.session.current_session import CurrentSessionPlugin as SessionPlugin
from dsh.session.jsonl_backend_current import CurrentJsonlSessionPersistencePlugin as JsonlSessionPersistencePlugin
MODES=['lazy','duplicate','cursor','legacy','unknown','cold-adopt','materialize','invalid-read']
def event(seq=0,kind='session/end-seed',data=None):return dict(seq=seq,type=kind,time=seq+1,data={} if data is None else data)
async def observe():
 rows=[]
 for mode in MODES:
  with tempfile.TemporaryDirectory() as root:
   ctx=Context()
   async def mount():
    await ctx.plugin(SessionPlugin);await ctx.plugin(JsonlSessionPersistencePlugin,{'root':root,'compression':'none'});return ctx.get('sessionPersistence')
   try:
    p=await mount();meta=dict(id='s',version=3,createdAt=1,isSeeded=False);writer=await p.create(meta)
    async def read():
     h=await p.open('s','read')
     try:return dict(await h.read(),meta=h.header)
     finally:await h.close()
    if mode=='lazy':
     meta['createdAt']=20;before=len(await p.list());await writer.append([event()]);rows.append(dict(mode=mode,before=before,createdAt=(await read())['meta']['createdAt']))
    elif mode=='duplicate':
     rejected=False
     try:await p.create(dict(meta,cwd=root))
     except ValueError:rejected=True
     rows.append(dict(mode=mode,rejected=rejected,physical=len(await p.list())))
    elif mode=='cursor':
     rejected=0
     for events in [[event(1)],[event(),event(2)]]:
      try:await writer.append(events)
      except ValueError:rejected+=1
     await writer.append([event()])
     try:await writer.append([event()])
     except ValueError:rejected+=1
     rows.append(dict(mode=mode,rejected=rejected,seqs=[e['seq'] for e in (await read())['events']]))
    elif mode=='legacy':
     rejected=0
     for ev in [event(0,'mode/set'),event(0,'request/header-delta'),event(0,'request/header',{'reason':'fallback'})]:
      try:await writer.append([ev])
      except ValueError:rejected+=1
     rows.append(dict(mode=mode,rejected=rejected,physical=len(await p.list())))
    elif mode=='unknown':
     rejected=0
     try:await writer.append([event(0,'future/plugin')])
     except ValueError:rejected+=1
     rows.append(dict(mode=mode,rejected=rejected,physical=len(await p.list())))
    elif mode=='cold-adopt':
     await writer.append([event(0,'turn/start',{'turn':1})]);await ctx.fiber.dispose();ctx=Context();p=await mount()
     writer=await p.open('s','write');await writer.append([event(1)]);rows.append(dict(mode=mode,types=[e['type'] for e in (await read())['events']]))
    elif mode=='materialize':
     await writer.flush();await writer.flush();rows.append(dict(mode=mode,events=len((await read())['events']),physical=len(await p.list())))
    else:
     ev=event(0,'turn/start',{'turn':1});ev['time']='bad';rejected=0
     try:await writer.append([ev])
     except ValueError:rejected+=1
     rows.append(dict(mode=mode,rejected=rejected,physical=len((await read())['events'])))
   finally:await ctx.fiber.dispose()
 return rows
if __name__=='__main__':Path(sys.argv[1]).write_text(json.dumps(asyncio.run(observe()),indent=2)+'\n',encoding='utf-8')

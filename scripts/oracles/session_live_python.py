import asyncio
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dsh.cordis.context import Context
from dsh.core.session.current_session import CurrentSessionPlugin as SessionPlugin
from dsh.session.jsonl_backend_current import CurrentJsonlSessionPersistencePlugin as JsonlSessionPersistencePlugin

def turn(session,n=1):
    session.append('turn/start',{'turn':n})
    session.append('turn/end',{'turn':n,'reason':{'kind':'completed'}})
async def observe():
    rows=[]
    for mode in ['unload','preexisting','reload-open','collision']:
        with tempfile.TemporaryDirectory() as root:
            ctx=Context()
            try:
                await ctx.plugin(SessionPlugin)
                session=None
                if mode=='preexisting':
                    session=ctx.get('sessions').create('s');turn(session)
                fiber=await ctx.plugin(JsonlSessionPersistencePlugin,{'root':root,'compression':'none'})
                if session is None: session=ctx.get('sessions').create('s')
                writer=await ctx.get('sessionPersistence').create(session.header)
                if mode=='preexisting':await writer.append(session.snapshotEvents())
                if mode=='reload-open': session.append('turn/start',{'turn':1})
                elif mode!='preexisting': turn(session)
                if mode in ['unload','reload-open']:
                    await fiber.dispose()
                    fiber=await ctx.plugin(JsonlSessionPersistencePlugin,{'root':root,'compression':'none'})
                    writer=await ctx.get('sessionPersistence').open(session.id,'write')
                if mode=='reload-open': session.append('turn/end',{'turn':1,'reason':{'kind':'completed'}})
                await session.flush();await session.flush()
                rejected=False
                if mode=='collision':
                    await ctx.fiber.dispose()
                    ctx=Context();await ctx.plugin(SessionPlugin)
                    await ctx.plugin(JsonlSessionPersistencePlugin,{'root':root,'compression':'none'})
                    session=ctx.get('sessions').create('s');turn(session,2)
                    try: await ctx.get('sessionPersistence').create(session.header)
                    except ValueError: rejected=True
                reader=await ctx.get('sessionPersistence').open('s','read')
                physical=await reader.read()
                await reader.close()
                rows.append(dict(mode=mode,rejected=rejected,events=[{k:e[k] for k in ['type','seq','data']} for e in physical['events']]))
            finally: await ctx.fiber.dispose()
    return rows
if __name__=='__main__':
    Path(sys.argv[1]).write_text(json.dumps(asyncio.run(observe()),indent=2)+'\n',encoding='utf-8')

"""Replay the Source-observed detached Session API prefixes."""
from unittest.mock import patch
from dsh.core.session.current_session import CurrentSession
from dsh.core.session.json import UNDEFINED
from dsh.core.session import current,current_surface,current_request_header
from dsh.cordis.errors import ThrownValueError


def outcome(run):
    try:
        value=run()
        return dict(outcome='value',value=None if value is UNDEFINED else value)
    except Exception as error:
        result=dict(outcome='error',name=getattr(error,'name','TypeError' if isinstance(error,TypeError) else 'Error'),message=str(error))
        if hasattr(error,'cause'):result['cause']=str(error.cause)
        return result


def execute(test,decode):
    if test['operation']=='function':
        name=test['name'];args=decode(test['args'])
        if name=='isSurfaceEligibleType':return outcome(lambda:args[0] in current.SURFACE_EVENT_TYPES)
        if name in ('isSurfaceEvent','isAppendSurfaceEvent','isReplacementSurfaceEvent'):
            def check():
                event=args[0]
                eligible=event.get('type') in current.SURFACE_EVENT_TYPES and event.get('surfaceOp',UNDEFINED) is not UNDEFINED
                return eligible and (name=='isSurfaceEvent' or (event.get('surfaceOp')=='append')==(name=='isAppendSurfaceEvent'))
            return outcome(check)
        provider=next(module for module in (current,current_surface,current_request_header) if hasattr(module,name))
        return outcome(lambda:getattr(provider,name)(*args))
    constructor=test['constructor'];args=decode(constructor['args'])
    if len(args)>1 and args[1] is UNDEFINED:args[1]=None
    clocks=iter(constructor['clock'])
    holder=[]
    def create():
        if constructor['method']=='create':session=CurrentSession.create(*args)
        else:
            if len(args)<5:args.append('snapshot')
            if args[4] is UNDEFINED:args[4]='snapshot'
            session=CurrentSession.from_restore(*args)
        holder.append(session)
    original=current_surface.CurrentSurfaceManager.validate_next
    def validate(manager,event):
        if test.get('fault') and isinstance(event.get('surfaceOp'),dict):
            fault=test['fault']
            raise ValueError(fault['message']) if fault['nativeError'] else ThrownValueError(fault['message'])
        return original(manager,event)
    with patch.object(CurrentSession,'_event_time',lambda self:next(clocks)),patch.object(current_surface.CurrentSurfaceManager,'validate_next',validate):
        last=outcome(create)
    if not holder:return dict(last=last)
    session=holder[0]
    for action in test['actions']:
        clocks=iter(action['clock']);args=decode(action['args'])
        def invoke():
            if action['method']=='append':return session.append(args[0],args[1],opts=args[2] if len(args)>2 else None)
            if action['method']=='snapshotEvents':
                args[:]=[0 if index==0 and value is UNDEFINED else None if value is UNDEFINED else value for index,value in enumerate(args)]
            return getattr(session,action['method'])(*args)
        with patch.object(CurrentSession,'_event_time',lambda self:next(clocks)):
            last=outcome(invoke)
    return dict(last=last,state=dict(header=session.header.to_dict(),firstLiveSeq=session.firstLiveSeq,
        inheritedEventCount=session.inheritedEventCount,seq=session.seq,events=session.snapshotEvents()))

"""Durable attribution for adjacent Agent messages and runtime settlement notices."""
from dsh.llm.message import create_user_message
from dsh.cordis.utils import js_to_string
from dsh.subagent.internal import initial_prompt as withContinuableReturnGuidance


def createAgentMessage(sender,content):
    return create_user_message(dict(content=[dict(type='text',text='Agent %s sent a message: ' % sender.id)]+list(content),
        source=dict(kind='agent-message',form='relay',senderSessionId=sender.id)))


def settlementSummary(child_id,reason):
    endings={'completed':'finished and will do no further work unless you send it more.',
             'aborted':'was stopped before it finished.','max-tokens':'ran out of room before it finished.',
             'refusal':'declined the task.','error':'failed before it finished.'}
    return 'Background subagent %s %s' % (child_id,endings.get(reason,'ended abnormally (%s) before it finished.' % js_to_string(reason)))


def createSettlementMessage(child_id,terminal):
    summary=settlementSummary(child_id,terminal['stopReason'])
    encoded=summary.encode('utf-16-le',errors='surrogatepass')
    short=summary if len(encoded)<=240 else encoded[:238].decode('utf-16-le',errors='surrogatepass')+'\u2026'
    closing=([dict(type='text',text='Its closing message:')]+list(terminal['output']) if 'output' in terminal
             else [dict(type='text',text='It left no closing message.')])
    return create_user_message(dict(content=[dict(type='text',text=summary)]+closing,
        source=dict(kind='subagent-settled',form='notice',summary=short,senderSessionId=child_id)))

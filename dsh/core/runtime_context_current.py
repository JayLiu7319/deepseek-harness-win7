"""rc.3 durable system-prompt and runtime-context surface decisions."""
from dsh.core.runtime_context import SOURCE, CLEARED, _UNSET, is_owned
from dsh.core.session.current import SURFACE_EVENT_TYPES
from dsh.llm.message import create_system_message, create_user_message


def text_of(message):
    content = message['content']
    if len(content) == 1 and isinstance(content[0], dict) and content[0].get('type') == 'text':
        return content[0].get('text')
    return None


class SystemPromptProjection:
    def __init__(self, session):
        self.session = session

    def project(self, rendered, input):
        nodes = []
        for seq in self.session.surface.nodes:
            event = self.session.eventAt(seq)
            if event is not None and event['type'] == 'system/message':
                message = event['data']['message']
                nodes.append(dict(seq=seq, text='' if not message['content'] else text_of(message)))
        if not nodes:
            return [dict(message=create_system_message(rendered, SOURCE), intent=dict(surfaceOp='append'))]
        head = nodes[0]
        latest = next((node for node in reversed(nodes) if node['text'] != ''), head)
        if not input['inHistory'] or input['startsSeries'] or not rendered:
            updates = [self._replace(node['seq'], '') for node in nodes[1:] if node['text'] != '']
            if head['text'] != rendered:
                updates.append(self._replace(head['seq'], rendered))
            return updates
        if latest['text'] == rendered:
            return []
        return [dict(message=create_system_message(rendered, SOURCE), intent=dict(surfaceOp='append'))]

    @staticmethod
    def _replace(seq, text):
        return dict(message=create_system_message(text, SOURCE), intent=dict(
            surfaceOp=dict(op='replace', startSeq=seq, endSeq=seq), sourceEventSeqs=[seq]))


class RuntimeContextProjection:
    def __init__(self, ctx, session):
        self.session, self._retained_state = session, _UNSET
        surface = set(session.surface.nodes)
        for event in reversed(session.snapshotEvents()):
            if event['type'] != 'user/message' or not is_owned(event['data']):
                continue
            if self._retained_state is _UNSET:
                self._retained_state = None
            if event['seq'] in surface:
                self._retained_state = dict(seq=event['seq'], text=text_of(event['data']))
                break
        ctx.on('session/event', self._on_event)

    def _on_event(self, subject, event):
        if subject is not self.session:
            return
        if event['type'] == 'user/message' and is_owned(event['data']):
            self._retained_state = dict(seq=event['seq'], text=text_of(event['data']))
        elif (isinstance(self._retained_state, dict) and event['type'] in SURFACE_EVENT_TYPES
              and isinstance(event.get('surfaceOp'), dict)
              and self._retained_state['seq'] in event.get('sourceEventSeqs', [])):
            self._retained_state = None

    def project(self, current, sections):
        if self._retained_state is _UNSET and not current:
            return None
        snapshot = current if current else CLEARED
        if isinstance(self._retained_state, dict) and self._retained_state['text'] == snapshot:
            return None
        source = dict(kind='plugin', plugin=SOURCE)
        if sections:
            source.update(form='snapshot', sections=sections)
        return create_user_message(dict(content=[dict(type='text', text=snapshot)], source=source))

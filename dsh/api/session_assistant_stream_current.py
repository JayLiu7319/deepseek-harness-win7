"""Process-local Assistant attempt baseline for reconnecting Session followers."""
from dsh.llm.assistant_stream import AssistantStreamAccumulator


class SessionAssistantStreamAccumulator:
    def __init__(self):
        self.active, self.revision, self.value, self.dirty = None, 0, dict(revision=0), False

    def accept(self, frame, durable_cursor):
        if frame['type'] == 'start' and frame['revision'] == 1 and self.revision != 0:
            self.active, self.revision = None, 0
        if frame['revision'] != self.revision + 1:
            self.active, self.revision, self.dirty = None, frame['revision'], True
            return
        self.revision = frame['revision']
        if frame['type'] == 'start':
            self.active = dict(attemptId=frame['attemptId'], startedAfterSeq=durable_cursor, turn=frame['turn'], step=frame['step'],
                stream=AssistantStreamAccumulator(), nextIndex=0)
        elif frame['type'] == 'chunk':
            attempt = self.active
            if attempt is None or attempt['attemptId'] != frame['attemptId'] or frame['index'] != attempt['nextIndex']:
                self.active = None
            else:
                attempt['stream'].push(dict(time=frame['time'], chunk=frame['chunk']))
                attempt['nextIndex'] += 1
        elif frame['type'] == 'end':
            self.active = None
        self.dirty = True

    def snapshot(self):
        if not self.dirty:
            return self.value
        self.value = dict(revision=self.revision)
        if self.active is not None:
            self.value['activeAttempt'] = dict(self.active, stream=self.active['stream'].snapshot())
        self.dirty = False
        return self.value

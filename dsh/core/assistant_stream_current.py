"""Process-local rc.3 attempt frames backed by one immutable compact stream."""
import time

from dsh.llm.assistant_stream import AssistantStreamAccumulator
from dsh.llm.assembler import BlockAssembler


class AssistantStreamAttempt:
    def __init__(self, session_id, attempt, next_revision, turn, step, emit):
        self.attemptId = '%s:%s' % (session_id, attempt)
        self.next_revision, self.turn, self.step, self.emit = next_revision, turn, step, emit
        self.accumulator, self.assembler = AssistantStreamAccumulator(), BlockAssembler()
        self.index, self.ended = 0, False

    def _frame(self, kind, **data):
        self.emit(dict(type=kind, attemptId=self.attemptId, revision=self.next_revision(), **data))

    def start(self):
        self._frame('start', turn=self.turn, step=self.step)

    def push(self, chunk):
        timed = self.accumulator.push(dict(time=int(time.time() * 1000), chunk=chunk))
        self.assembler.push(timed['chunk'])
        index = self.index
        self.index += 1
        self._frame('chunk', index=index, time=timed['time'], chunk=timed['chunk'])

    def settle(self, event_type, append):
        try:
            seq = append()
        except BaseException:
            self.abandon()
            raise
        self.ended = True
        self._frame('end', index=self.index, outcome=dict(kind='committed', eventType=event_type, seq=seq))

    def abandon(self):
        self.ended = True
        self._frame('end', index=self.index, outcome=dict(kind='abandoned'))

    @property
    def stream(self):
        return list(self.accumulator.snapshot())

    def blocks(self):
        return self.assembler.blocks()

    def interruptedBlocks(self):
        return self.assembler.interruptedBlocks()

    @property
    def usage(self):
        return self.assembler.usage

    @property
    def finish(self):
        return self.assembler.finish

    @property
    def replayState(self):
        return self.assembler.replayState

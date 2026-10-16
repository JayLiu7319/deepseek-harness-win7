"""Current control replacement frames driven by the durable Inbox projection."""
import asyncio


def queue_items_from_inbox(inbox):
    result = []
    for target in ('next-turn', 'next-step'):
        for message in inbox[target]:
            source = message['source']
            item = dict(id=message['id'], placement='queued' if target == 'next-turn' else 'steering' if source['kind'] == 'user' else 'context',
                message=dict(id=message['id'], content=message['content']))
            if source['kind'] == 'user' and 'rpcId' in source:
                item['rpcId'] = source['rpcId']
            result.append(item)
    return result


class CurrentSessionControl:
    def __init__(self, ctx):
        self.ctx, self.streams = ctx, set()
        def changed(session, key, value, seq):
            self.broadcast(dict(type='projection', sessionId=session.id, key=key, value=value, seq=seq))
            if key == 'inbox':
                agent = ctx.get('agents').get(session.id)
                if agent is not None and agent.session is session:
                    self.broadcast(dict(type='queue', sessionId=session.id, items=queue_items_from_inbox(value)))
        ctx.get('sessionProjections').onChanged(changed)
        ctx.inject(['jobs'], lambda child: child.get('jobs').onJobsChanged(self.jobs_changed))
        ctx.on('session/created', self.created)
        ctx.effect(lambda: self.close)

    def broadcast(self, frame):
        for queue in self.streams:
            queue.put_nowait(frame)

    def close(self):
        for queue in self.streams:
            queue.put_nowait(None)
        self.streams.clear()

    def jobs(self, agent):
        service = self.ctx.get('jobs')
        return [{key: row[key] for key in ('id', 'kind', 'label', 'status', 'detail', 'startedAt', 'finishedAt') if key in row}
            for row in service.list(agent)] if service is not None else []

    def created(self, session):
        jobs = self.jobs(self.ctx.get('agents').get(session.id))
        if jobs:
            self.broadcast(dict(type='jobs', sessionId=session.id, jobs=jobs))

    def jobs_changed(self, owner):
        if owner is not None:
            self.broadcast(dict(type='jobs', sessionId=owner.id, jobs=self.jobs(owner)))
        else:
            for session in self.ctx.get('sessions').list():
                self.broadcast(dict(type='jobs', sessionId=session.id, jobs=self.jobs(self.ctx.get('agents').get(session.id))))

    def baseline(self):
        sessions, queues, jobs = self.ctx.get('sessions').list(), {}, {}
        for session in sessions:
            agent = self.ctx.get('agents').get(session.id)
            queues[session.id] = queue_items_from_inbox({'next-turn': agent.inbox.nextTurn, 'next-step': agent.inbox.nextStep}) if agent is not None and agent.session is session else []
            jobs[session.id] = self.jobs(agent)
        projections = {session.id: self.ctx.get('sessionProjections').snapshot(session) for session in sessions}
        return dict(queues=queues, jobs=jobs, projections=projections)

    async def control(self, signal):
        signal.throwIfAborted()
        queue = asyncio.Queue()
        self.streams.add(queue)
        release = signal.add_listener('abort', lambda *_: queue.put_nowait(None))
        try:
            yield dict(type='baseline', value=self.baseline())
            while not signal.aborted:
                frame = await queue.get()
                if frame is None:
                    # Source teardown drains frames accepted before closure.
                    while not queue.empty() and not signal.aborted:
                        pending = queue.get_nowait()
                        if pending is not None:
                            yield pending
                    return
                yield frame
        finally:
            release()
            self.streams.discard(queue)

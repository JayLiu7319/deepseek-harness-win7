"""Scoped model adapters for continuation delivery, interruption and reports."""
from dsh.cordis.plugin import Plugin
from dsh.subagent.canonical_tools import register, object_schema, text, agent_of
from dsh.subagent.internal import mark_adjacent_message


class ToolSubagentControl(Plugin):
    id = 'tool-subagent-control'
    inject = ['tools', 'subagents']

    def apply(self, ctx):
        async def send(args, execution):
            parent = agent_of(execution)
            identity = await ctx.get('subagents').sendMessage(parent, args['agent_id'], text(args['message']),
                dict(signal=execution.signal))
            return dict(messageId=identity)
        register(ctx, 'send_message', 'Send a message to a direct continuable child by its agent id. If you are a resident continuable child, '
                 'you may also target your direct parent. If the target is still working, the message steers its nearest step; '
                 'if it is idle, the message starts a turn. This call returns no answer from the agent — only confirmation '
                 'that the message was delivered. A failure means the message was NOT delivered.',
                 dict(agent_id={'type': 'string', 'description': 'The agent id of your direct continuable child, or your direct parent when you are a resident continuable child.'},
                      message={'type': 'string', 'description': 'The message to deliver to the agent.'}), mark_adjacent_message(send),
                 object_schema(dict(messageId={'type': 'string'})), lambda args, _: text('message delivered to agent ' + args['agent_id']))
        async def interrupt(args, execution):
            ctx.get('subagents').interrupt(args['agent_id'], dict(kind='ancestor', agent=agent_of(execution)))
            return dict(accepted=True)
        register(ctx, 'interrupt_agent', "Request cancellation of a background agent's current turn by its agent id. The target may be your direct child or a deeper agent created under you. Only the current turn stops: messages already queued for the agent stay parked until a later send_message, agents it started keep running, and the agent itself stays available for follow-ups. This call returns as soon as the stop request is accepted, so the target may keep running briefly; interrupting an agent that already finished is an accepted no-op.",
                 dict(agent_id={'type': 'string', 'description': 'The agent id of the running agent to interrupt.'}), interrupt, object_schema(dict(accepted={'type': 'boolean'})),
                 lambda args, _: text('interrupt requested for agent ' + args['agent_id']))


class ToolListAgents(Plugin):
    id = 'tool-subagent-list-agents'
    inject = ['tools', 'subagents', 'agents']

    def apply(self, ctx):
        async def execute(args, execution):
            parent = agent_of(execution)
            descendants = args.get('scope', 'children') == 'descendants'
            service = ctx.get('subagents')
            rows = await (service.listDescendants(parent.id, execution.signal) if descendants else service.listChildren(parent.id, execution.signal))
            result = []
            for row in rows:
                position = dict(parent=row['parentId'], depth=row['depth']) if descendants else {}
                if row['kind'] == 'diagnostic':
                    result.append(dict(kind='diagnostic', id=row['id'], reason=row['reason'], **position))
                elif row['mode'] == 'continuable':
                    agent = ctx.get('agents').get(row['id'])
                    status = 'ready' if agent is None else 'running' if agent.status == 'running' else 'idle'
                    result.append(dict(kind='child', id=row['id'], label=row['label'], status=status, **position))
            return result
        def render(args, entries):
            if not entries:
                return text('(no subagents)')
            lines = []
            for entry in entries:
                at = ' parent={} depth={}'.format(entry['parent'], entry['depth']) if args.get('scope') == 'descendants' else ''
                lines.append('{} [{}]{}{}'.format(entry['id'], entry['status'] if entry['kind'] == 'child' else 'diagnostic: ' + entry['reason'],
                    at, ' — ' + entry['label'] if entry['kind'] == 'child' else ''))
            return text('\n'.join(lines))
        common = dict(id={'type': 'string'}, parent={'type': 'string'}, depth={'type': 'number'})
        schema = {'type': 'array', 'items': {'oneOf': [
            object_schema(dict(common, kind={'type': 'string', 'const': 'child'}, label={'type': 'string'}, status={'type': 'string', 'enum': ['running', 'idle', 'ready']}), ['kind', 'id', 'label', 'status']),
            object_schema(dict(common, kind={'type': 'string', 'const': 'diagnostic'}, reason={'type': 'string', 'enum': ['corrupt', 'unsupported', 'unavailable']}), ['kind', 'id', 'reason'])]}}
        register(ctx, 'list_agents', 'List your continuable background subagents by durable id and label. Use it to recall which ones you started, not to poll for completion — you are told when one finishes. Status comes from the live registry: running means the agent is working right now, idle means it is loaded but between turns (it may be waiting on agents it started), and ready means it exists only in storage — resumable, not terminal, and not a result waiting to be collected; a `send_message` steers a running child at its nearest step boundary or starts a turn for an idle or ready child, and a direct child remains a `send_message` candidate in every status. The snapshot is not a delivery promise — `send_message` performs the authoritative check and may still fail. Children that could not be read are reported as diagnostics instead of being silently dropped. Scope `descendants` walks the whole tree below you in stable pre-order, annotating each entry with its durable direct-parent session id and depth. You may use `send_message` only for depth-1 entries; deeper entries are candidates for `interrupt_agent` only.',
                 dict(scope={'type': 'string', 'enum': ['children', 'descendants'],
                            'description': 'children (default) lists direct children only; descendants walks the complete tree below you.'}), execute, schema, render, [])


class ToolSubagentReport(Plugin):
    id = 'tool-subagent-report'
    inject = ['tools', 'subagents', 'systemPrompt']

    def apply(self, ctx):
        delivery = self.config.get('reportDelivery', 'next-step')
        if delivery not in ('quiet', 'next-step'):
            raise ValueError('invalid reportDelivery')
        def install(child_ctx):
            section = child_ctx.get('systemPrompt').section(dict(name='tool:report', order=2900,
                text='Report a self-contained result before finishing, and report partial findings when they change what your parent should do next. Reporting does not end your turn.'))
            async def execute(args, execution):
                identity = ctx.get('subagents').reportFrom(agent_of(execution), text(args['output']), dict(delivery=delivery, signal=execution.signal))
                return dict(messageId=identity)
            try:
                tool = register(child_ctx, 'report', 'Deliver selected content to your direct parent without ending your turn. A failed call may still have arrived; do not blindly repeat it.',
                    dict(output={'type': 'string'}), execute, object_schema(dict(messageId={'type': 'string'})),
                    lambda _, value: text('report accepted by the agent that started you as message ' + value['messageId']))
            except BaseException:
                section()
                raise
            def dispose():
                errors = []
                for remove in (tool, section):
                    try:
                        remove()
                    except Exception as error:
                        errors.append(error)
                if errors:
                    raise RuntimeError('failed to revoke report registrations: ' + '; '.join(str(error) for error in errors))
            return dispose
        ctx.get('subagents').registerContinuableSetup(install)

"""Private identity for the standard adjacent-Agent message adapter."""
import json

from dsh.core.scope import scope_of


def mark_adjacent_message(execute):
    execute._adjacent_agent_message = True
    return execute


def has_adjacent_message(ctx, agent):
    tools = ctx.get('tools')
    tool = tools.get('send_message', scope_of(agent.ctx)) if tools is not None else None
    return tool is not None and getattr(tool.handler, '_adjacent_agent_message', False) is True


def initial_prompt(parent_id, prompt):
    encoded = json.dumps(parent_id, ensure_ascii=False, separators=(',', ':'))
    return list(prompt) + [dict(type='text', text=(
        'Your parent agent id is %s. Before you finish, send your result to that agent with '
        'send_message({ agent_id: %s, message: "<self-contained result>" }). The parent shares '
        'your workspace but does not automatically receive your transcript, tool output, or reasoning. Send '
        'earlier messages as well when a finding changes what the parent should do next; sending a message '
        'does not end your turn.' % (encoded, encoded)))]

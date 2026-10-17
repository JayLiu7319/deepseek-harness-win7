"""Workspace instruction precedence, cache and transaction journeys."""
import copy
import json
from pathlib import Path


def generate():
    cases = []
    base = {'project/.git': dict(type='directory'), 'project/AGENTS.md': dict(content='root instruction')}
    def add(name, files=None, actions=None, **values):
        cases.append(dict(case='instructions/' + name, kind='instructions-current', files=copy.deepcopy(base if files is None else files),
                          actions=actions or [dict(op='step'), dict(op='step')], **values))
    add('baseline')
    add('empty', files={})
    add('global', files=dict(base, **{'home/AGENTS.md': dict(content='global instruction')}))
    add('nested', files=dict(base, **{'project/sub/AGENTS.md': dict(content='nested instruction')}), cwd='project/sub')
    for budget in (0, -1, 1, 80, 300, 500, 1000, 1000.0, 1000.5):
        add('budget-' + str(budget), config=dict(maxBytes=budget))
    for key in ('instructionFileCandidates', 'localInstructionFileCandidates', 'projectRootMarkers'):
        add('empty-config-' + key, config={key: []})
    add('local-dedup', files=dict(base, **{'project/CLAUDE.md': dict(content=' root instruction '),
                                        'project/AGENTS.local.md': dict(content='local instruction')}))
    for name, value in [('replace', dict(content='changed')), ('remove', None), ('unavailable', dict(statError='metadata denied')),
                        ('read-failure', dict(content='changed', readError='read denied')), ('same-version', dict(content='changed', version='v1'))]:
        files = dict(base, **{'project/AGENTS.md': dict(content='root instruction', version='v1')})
        add(name, files=files, actions=[dict(op='step'), dict(op='files', values={'project/AGENTS.md': value}), dict(op='step'), dict(op='step')])
    for error in ('resolveError', 'statError'):
        for code in ('FS_DENIED', 'FS_NOT_FOUND'):
            add('marker-' + error + '-' + code, files={'project/.git': {error: 'marker inaccessible', 'code': code}})
    for carrier in ('reject', 'empty'):
        add('pending-' + carrier, actions=[dict(op='step', **{carrier: True}), dict(op='step', **{carrier: True}), dict(op='step')])
    for name in ('read', 'write', 'edit', 'ignored'):
        add('touch-' + name, files=dict(base, **{'project/sub/AGENTS.md': dict(content='nested instruction')}),
            actions=[dict(op='step'), dict(op='touch', name=name), dict(op='step'), dict(op='step')])
    for error in (False, True):
        add('step-transaction-' + str(error), files=dict(base, **{'project/sub/AGENTS.md': dict(content='nested instruction')}),
            actions=[dict(op='step'), dict(op='step-open'), dict(op='touch', error=error), dict(op='step-end'), dict(op='step')])
    for parent_error in (False, True):
        add('nested-execution-' + str(parent_error), files=dict(base, **{'project/sub/AGENTS.md': dict(content='nested instruction')}),
            actions=[dict(op='step'), dict(op='touch', token='inner', parent='outer'),
                     dict(op='touch', token='outer', name='ignored', error=parent_error), dict(op='step')])
    add('oversize-stream', files=dict(base, **{'project/AGENTS.md': dict(content='small', omitSize=True, chunks=['1234', '5678'])}),
        config=dict(maxSourceBytes=5))
    add('oversize-metadata', config=dict(maxSourceBytes=3))
    add('unavailable-sibling-rollback', files=dict(base, **{'project/CLAUDE.md': dict(content='second')}),
        actions=[dict(op='step'), dict(op='files', values={'project/AGENTS.md': dict(content='new'),
                'project/CLAUDE.md': dict(statError='unavailable')}), dict(op='step'),
                dict(op='files', values={'project/CLAUDE.md': dict(content='second')}), dict(op='step')])
    add('disposed', actions=[dict(op='step'), dict(op='dispose'), dict(op='step')])
    return cases


if __name__ == '__main__':
    Path(__file__).with_name('instructions_current_cases.json').write_text(json.dumps(generate(), indent=2) + '\n', encoding='utf-8')

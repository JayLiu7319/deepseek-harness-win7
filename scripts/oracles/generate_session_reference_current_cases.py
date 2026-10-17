"""Reference budgets, full transcripts, omissions and cancellation inputs."""
import json
from pathlib import Path


def generate():
    rows = []
    def add(name, **values): rows.append(dict(case='session-reference/' + name, kind='session-reference-current', **values))
    add('intact')
    add('empty', references=[])
    add('model-missing', options={})
    add('no-llm', noLlm=True)
    for error in ('NO_ADAPTER', 'INVALID_MODEL', 'ordinary'): add('metadata-' + error, modelError=error)
    add('read-failed', readError=True)
    large = [dict(id='source', cwd='C:/workspace', texts=[dict(text='older ', repeat=100), dict(text='last <😀>\n', repeat=200)])]
    for budget in (1, 150, 220, 500, 1000, 10000):
        for spill in (False, True): add('budget-%s-spill-%s' % (budget, spill), sources=large, config=dict(maxReferenceBytes=budget), spill=spill)
    add('save-failed', sources=large, config=dict(maxReferenceBytes=220), spill=True, spillError=True)
    add('cancelled-save', sources=large, config=dict(maxReferenceBytes=220), spill=True, abortOnSave=True)
    add('cancelled-before', abortBefore=True)
    add('cancelled-empty', abortBefore=True, references=[])
    add('duplicates', sources=large, references=[dict(sessionId='source', label='first <tag>'), dict(sessionId='source', label='second')])
    add('self', references=[dict(sessionId='target')])
    add('invalid', references=[dict(sessionId=1)])
    add('nonobject', references=[None])
    add('limit', references=[dict(sessionId=str(i)) for i in range(4)])
    capacity=[dict(id='source',texts=[dict(text='x',repeat=66000)])]
    add('auto-floor', sources=capacity, modelInfo=dict(context=dict(contextWindow=1000)))
    add('auto-expand', sources=capacity, modelInfo=dict(context=dict(contextWindow=100000)))
    add('auto-zero', sources=capacity, config=dict(referenceContextFraction=0), modelInfo=dict(context=dict(contextWindow=100000)))
    add('assembled-route', sources=capacity, assembled=dict(provider='new-provider',model='large-model'), modelInfo=dict(context=dict(contextWindow=100000)))
    add('assembled-missing-route', sources=large, assembled={})
    add('explicit-skips-metadata', sources=large, config=dict(maxReferenceBytes=300), modelError='ordinary')
    add('multiple-spills', sources=large+[dict(id='second',version=0,texts=[dict(text='other',repeat=1000)])],config=dict(maxReferenceBytes=250),spill=True)
    return rows


if __name__ == '__main__':
    Path(__file__).with_name('session_reference_current_cases.json').write_text(json.dumps(generate(),indent=2)+'\n',encoding='utf-8')

"""Full actual Agent requests, measurements, projection state and compaction."""
import json
from pathlib import Path
from scripts.oracles.generate_agent_machine_current_cases import response
from scripts.oracles.generate_agent_loop_current_cases import action,message


def cases():
    rows=[];view=[action('measure'),action('meterProjections')]
    def add(name,actions,**extra):
        rows.append(dict(case=name,kind='machine-current',meter=True,persistence=True,actions=actions,
            script=[response() for _ in range(10)],**extra))
    send=lambda text:action('followup',message(text))
    for in_history in (False,True):
        for usage in (None,dict(inputTokens=1000,outputTokens=50),dict(inputTokens=1,outputTokens=1,cacheReadTokens=2,cacheWriteTokens=3)):
            extras=dict(systemPromptUpdate='in-history') if in_history else {}
            add('history-%s/usage-%s' % (in_history,len(rows)),view+[send('one'),action('idle')]+view+
                [action('prompt',text='changed prompt'),send('two'),action('idle')]+view+[
                action('measure',header=dict(config=dict(provider='other',model='model'))),
                action('resume')]+view,**extras)
            if usage is not None:
                rows[-1]['script']=[chunks[:-1]+[dict(type='usage',usage=usage),chunks[-1]] for chunks in rows[-1]['script']]
    add('actual-compaction', [send('long context '*2000),action('idle')]+view+[action('compact')]+view+[send('after compact'),action('idle')]+view)
    return rows


if __name__=='__main__':
    Path(__file__).with_name('token_meter_current_cases.json').write_text(json.dumps(cases(),indent=2)+'\n',encoding='utf-8')

"""Input journeys for the complete current Session facade and cold skill catalog."""
import json
from pathlib import Path

cases=[]
def add(name, actions, **values):
    cases.append(dict(case=name,kind='session-facade-current',actions=actions,**values))
catalog=[dict(op='catalog')]
add('catalog-empty',catalog)
add('catalog-failure-isolation',catalog,providers=[dict(id='empty',name='Empty',models=[]),dict(id='bad',name='Bad',error='not available'),dict(id='ok',name='Healthy',models=[dict(id='model',name='Model',description='listed',hidden='omit',reasoning=dict(efforts=[dict(id='high',name='High',description='think',hidden='omit')],defaultEffort='high',internal='omit'))]),dict(id='opaque',name='Opaque',error=dict(throw=False))])
add('catalog-one-resolve-failure-drops-provider',catalog,providers=[dict(id='one',name='One',models=[dict(id='fine',name='Fine'),dict(id='bad',name='Bad',resolveError='model missing')]),dict(id='two',name='Two',models=[dict(id='fine',name='Fine')])])
skills=[dict(name='review',description='Review',whenToUse='Before commit',invocation=dict(modelInvocable=False,userInvocable=True)),dict(name='model-only',description='Hidden',invocation=dict(modelInvocable=True,userInvocable=False))]
for name,values in [('cold',{}),('live',dict(live=True)),('standing',dict(presets=True,preset='minimal')),('fallback',dict(presets=True,standingError=True)),('scoped-live',dict(presets=True,live=True,scopedSkills=True)),('global-live',dict(presets=True,live=True))]:
    add('skills-'+name,[dict(op='skills')],skills=skills,**values)
add('skills-missing',[dict(op='skills')],queryError='missing')
add('skills-query-error',[dict(op='skills')],queryError='disk failed')
add('skills-unprojected',[dict(op='skills')],unprojected=True)
add('skills-no-cwd',[dict(op='skills')],header={})
add('skills-no-registry',[dict(op='skills')],noSkills=True)
add('skills-registry-error',[dict(op='skills')],skillError='scan failed')
add('skills-registry-nonerror',[dict(op='skills')],skillError=dict(throw=dict(problem=True)))
add('skills-admitted-preabort',[dict(op='skills')],aborted=True,skills=skills)
add('inspect-cold',[dict(op='inspect')])
add('inspect-attached',[dict(op='inspect')],live=True)
add('inspect-notfound',[dict(op='inspect')],queryError='missing')
add('upload-resolver-live',[dict(op='resolver')],live=True)
add('upload-resolver-notfound',[dict(op='resolver')],queryError='missing')
add('native-default-available',[dict(op='available')])
add('native-disabled-probe',[dict(op='available')],config=dict(nativeOpen=False))
add('native-open-reveal',[dict(op='open',request=dict(path="C:\\project\\a'b.txt")),dict(op='open',request=dict(path='C:\\project',action='reveal'))])
add('native-empty',[dict(op='open',request=dict(path=''))])
add('native-error',[dict(op='open',request=dict(path='file'))],nativeError='denied')
add('native-nonerror',[dict(op='open',request=dict(path='file'))],nativeError=dict(throw=dict(no=True)))
add('native-abort-during',[dict(op='open',request=dict(path='file'))],nativeError='stopped',nativeAbort=True)
add('native-preabort',[dict(op='open',request=dict(path='file'))],aborted=True)
add('prompt-preabort',[dict(op='prompt')],aborted=True)

if __name__=='__main__':
    Path(__file__).with_name('session_facade_current_cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

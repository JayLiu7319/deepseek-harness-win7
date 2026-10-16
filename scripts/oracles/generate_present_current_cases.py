"""Inputs only: expected observations are frozen from unchanged Source."""
import json
from pathlib import Path

cases=[]
def add(name,**values):cases.append(dict(case=name,kind='present-current',**values))
add('one-file')
add('unicode-binary',calls=[[dict(path='报告.docx',description='Report'),dict(path='/outside/图.png')]])
add('relative-outside',calls=[[dict(path='../outside/result.zip')]])
add('duplicate-paths',calls=[[dict(path='one'),dict(path='one',description='Again')]])
add('repeat-calls',calls=[[dict(path='one')],[dict(path='two')]])
add('nested-owner',nested=True)
add('override',override=True,calls=[[]])
add('post-block',block=True)
for name,values in [('detached',dict(detached=True)),('closed',dict(closed=True)),('no-projection',dict(noBoundary=True)),('no-workspace',dict(noWorkspace=True)),('missing',dict(missing=True,lstatMissing=True)),('lstat-missing-stat-present',dict(lstatMissing=True)),('directory',dict(entryKind='directory')),('symlink',dict(entryKind='symlink')),('race-directory',dict(statKind='directory')),('fs-error',dict(fsError='FS_SANDBOX_DENIED')),('abort-during',dict(abortDuring=True)),('pre-abort',dict(aborted=True))]:add(name,**values)
add('empty',calls=[[]])
add('excess',config=dict(maxFiles=1),calls=[[dict(path='a'),dict(path='b')]])
add('whole-float-limit',config=dict(maxFiles=2.0))
for i,path in enumerate(['','  ','\ufeff','\x85','\u001c','  file  ']):add('whitespace-'+str(i),calls=[[dict(path=path)]])
for i,file in enumerate([{},dict(path=3),dict(path='a',description=1),dict(path='a',extra=True)]):add('invalid-file-'+str(i),calls=[[file]])
Path(__file__).with_name('present_current_cases.json').write_text(json.dumps(cases,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')

"""Inputs for original fully-qualified paths and snapshot registry consumers."""
import json
from pathlib import Path
cases=[]
paths=['','.', '..','relative/path','/','//','///','/work/','/work//','C:','C:work','C:/','C:\\','C:/work/','C:\\work\\','c:relative','\\work','/work','\\\\server','\\\\server\\share','\\\\server\\share\\','\\\\server\\share\\path','//server/share','///server/share','\\\\server\\\\share','\\\\?\\C:\\','\\\\.\\pipe\\name','\\\\?\\UNC\\server\\share\\','1:/work','K:/work','C:\\\\','C:/\\','/\\','\\\\','\\\\\\server\\share']
for platform in ('win32','linux','darwin'):
    for i,path in enumerate(paths):cases.append(dict(case='path-'+platform+'-'+str(i),kind='workspace-current',operation='path',path=path,platform=platform))
cases.append(dict(case='registry-cold-snapshots',kind='workspace-current',actions=[dict(op='view'),dict(op='create',path='b'),dict(op='headers',headers=[dict(id='one',path='a'),dict(id='two',path='b')]),dict(op='attach',path='b',id='two'),dict(op='archive',id='two'),dict(op='reopen'),dict(op='detach',path='b',id='two'),dict(op='reopen')]))
for path in ('.','relative','C:work','\\rooted'):cases.append(dict(case='registry-relative-'+str(len(cases)),kind='workspace-current',actions=[dict(op='relative',path=path)]))
Path(__file__).with_name('workspace_current_cases.json').write_text(json.dumps(cases,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')

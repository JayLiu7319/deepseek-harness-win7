"""Inputs for current file tool visibility, failure reasons and spill ownership."""
import itertools
import json
from pathlib import Path

cases=[]
names=['read','write','edit','glob','grep']
for count in range(6):
    for allowed in itertools.combinations(names,count):cases.append(dict(case='prompt-'+('-'.join(allowed) or 'none'),kind='file-tools-current',operation='prompt',allow=list(allowed)))
for op in ('write','edit'):
    for code in ('FS_NOT_OBSERVED','FS_STALE_VERSION','FS_PERMISSION_DENIED'):
        cases.append(dict(case=op+'-'+code,kind='file-tools-current',operation=op,code=code))
for op in ('glob','grep'):
    for failure in ('launch','provider',None):cases.append(dict(case=op+'-'+(failure or 'spill'),kind='file-tools-current',operation=op,failure=failure))
for replace in (False,True):cases.append(dict(case='image-'+str(replace),kind='file-tools-current',operation='read_image',replaceImage=replace))
Path(__file__).with_name('file_tools_current_cases.json').write_text(json.dumps(cases,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')

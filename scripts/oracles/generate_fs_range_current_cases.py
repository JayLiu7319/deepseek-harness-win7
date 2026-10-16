"""Generate real file range inputs, keeping large fixtures reconstructible."""
import base64
import json
from pathlib import Path

cases=[]
for name,data,repeat in [('empty',b'',1),('binary',bytes(range(256)),1),('text','中文\nline\r\n'.encode('utf-8'),1),('multiple-chunks',b'X',150000)]:
    for index,(offset,length) in enumerate([(0,0),(0,1),(1,7),(7,65540),(300000,8),(len(data)*repeat,1)]):
        cases.append(dict(case='range-'+name+'-'+str(index),kind='fs-range-current',data=base64.b64encode(data).decode(),repeat=repeat,range=dict(offset=offset,length=length)))
for name,values in [('aborted',dict(aborted=True)),('missing',dict(path='missing')),('directory',dict(path='directory'))]:
    cases.append(dict(case='range-'+name,kind='fs-range-current',range=dict(offset=0,length=0),**values))
if __name__=='__main__':
    Path(__file__).with_name('fs_range_current_cases.json').write_text(json.dumps(cases,indent=2)+'\n',encoding='utf-8')

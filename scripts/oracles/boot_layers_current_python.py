"""Current home proxy admission and inserted filesystem path anchoring."""
import os, json, tempfile
from pathlib import Path
from unittest.mock import patch
from dsh.boot.app_boot import load_layered_env, load_optional_patches, load_overlay_patches


def execute(test):
    with tempfile.TemporaryDirectory(prefix='rc3-boot-layers-') as directory:
        root=Path(directory);home=root/'home';project=home if test.get('sameDirectory') else root/'project'
        home.mkdir();project.mkdir(exist_ok=True)
        normalize=lambda value: json.loads(json.dumps(value,ensure_ascii=True).replace(str(root).replace(chr(92),chr(92)*2),'$ROOT').replace(root.as_uri(),'file:///$ROOT').replace(chr(92)*2,'/'))
        if test['operation']=='env':
            for path,key in ((home,'home'),(project,'project')):
                if key in test:(path/'.env').write_text(test[key],encoding='utf-8')
            inherited=dict(test.get('inherited',{}),DSH_HOME=str(home))
            with patch.dict(os.environ,inherited,clear=True):
                try:
                    snapshot=load_layered_env('dsh',str(project),home=str(home))
                    result={'entries':{key:snapshot.get(key) for key in test['names']},'materialized':{key:os.environ.get(key) for key in test['names']}}
                except Exception as error:result={'error':str(error),'materialized':{key:os.environ.get(key) for key in test['names']}}
            return normalize(result)
        file=root/'patches'/'extra.yml';file.parent.mkdir()
        def expand(value):
            if isinstance(value,str):return value.replace('$ABS',str(root/'plugin #100% 中文.py')).replace('$URL',(root/'plugin #100% 中文.py').as_uri())
            if isinstance(value,list):return [expand(x) for x in value]
            if isinstance(value,dict):return {k:expand(v) for k,v in value.items()}
            return value
        file.write_text(json.dumps(expand(test['patches']),ensure_ascii=False),encoding='utf-8')
        load=load_optional_patches if test['operation']=='optional' else load_overlay_patches
        return normalize(load('dsh',str(file)))

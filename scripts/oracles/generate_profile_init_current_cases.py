"""Inputs for launcher prefix ownership and exclusive profile initialization."""
import json
from pathlib import Path
cases=[]
def add(label,operation,**values):cases.append(dict(case=label,kind='profile-init-current',operation=operation,**values))
argv=[['--profile','rescue','--from-default-profile','web'],['--from-default-profile=web','--profile=rescue'],['--profile','rescue','--from-default-profile','headless','--patch','extra.yml','task'],['--profile','rescue','--from-default-profile','web','--dump-config'],['--profile','rescue','--dump-default-config','--from-default-profile=web'],['--profile','rescue','--resume','abc','--from-default-profile','web'],['web','--from-default-profile','web'],['--profile','rescue','--from-default-profile='],['--profile','rescue','--from-default-profile'],['--from-default-profile','web'],['--from-default-profile','web','plugin','--profile','rescue','add','x'],['--from-default-profile','web','web'],['--profile','desktop'],['--profile','Desktop','--dump-config'],['--profile','DESKTOP'],['plugin','--profile','Desktop','add','x'],['plugin','--profile','normal','add','x'],['--profile','rescue','--from-default-profile','web','--dump-config','task'],['--profile','rescue','--from-default-profile','web','--dump-default-config','--patch','x'],['--profile','rescue','--from-default-profile','web','--from-default-profile','sdk'],['--profile','web','--help'],['web','--dump-config'],['--profile','rescue','--','--from-default-profile','web']]
for i,args in enumerate(argv):add('args-'+str(i),'args',argv=args)
for template in ('acp','web','headless','sdk','sdk-minimal'):add('initialize-'+template,'init',template=template)
for name in ('acp','web','headless','sdk','sdk-minimal'):add('reserved-'+name,'init',name=name)
for template in ('unknown','toString','constructor'):add('unknown-'+template,'init',template=template)
for name in ('','..','node_modules','../outside','a/b','a\\b'):add('invalid-'+str(len(cases)),'init',name=name)
add('existing-manifest','init',files={'profiles/rescue/package.json':'{"name":"old","private":true,"dependencies":{"private":"1"}}','profiles/rescue/cordis.patch.yml':'- id: user\n  disabled: true\n'})
add('existing-invalid-manifest','init',files={'profiles/rescue/package.json':'broken json'},invalidManifest=True)
add('existing-empty-directory','init',existingDirectory=True)
add('residual-directory','init',files={'profiles/rescue/cordis.patch.yml':'- id: user\n'})
add('no-copy-local-profile','init',files={'profiles/web/package.json':'{"name":"local","dependencies":{"local":"1"},"dsh":{"profile":{"bundles":["local"]}}}','profiles/web/cordis.patch.yml':'- id: local-only\n'})
Path(__file__).with_name('profile_init_current_cases.json').write_text(json.dumps(cases,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')

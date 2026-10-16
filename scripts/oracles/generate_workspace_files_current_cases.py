"""Input contracts for read previews, workspace-only listing and change generations."""
import json
from pathlib import Path

cases=[]
def add(name,actions,**values):cases.append(dict(case=name,kind='workspace-files-current',actions=actions,**values))
def action(op,**values):return dict(op=op,**values)
add('lookup-cold',[action('lookup')])
add('lookup-live',[action('lookup')],liveHeader=dict(cwd='/live'))
add('lookup-fallback',[action('lookup')],header={})
add('lookup-missing',[action('lookup')],noHeader=True)
add('stat-regular',[action('stat')])
add('stat-unknown-size',[action('stat')],unknownSize=True)
for name,values in [('missing',dict(missing=True)),('directory',dict(entryKind='directory')),('symlink',dict(entryKind='symlink')),('vanished',dict(vanished=True)),('race-kind',dict(statKind='directory')),('resolve',dict(resolveError='FS_SANDBOX_DENIED'))]:
    add('stat-'+name,[action('stat')],**values)
add('stat-empty',[action('stat',path='')])
for name,chunks in [('empty',[]),('terminated',['a\n']),('blank-lines',['\n\n']),('chunks',['ab','c\n','d\n','ef']),('crlf',['one\r\ntwo\r\n']),('nul',['one\0\ntwo']),('unicode',['汉字\n😀\nend'])]:
    add('read-'+name,[action('read'),action('read',range=dict(offset=2,limit=1)),action('read',range=dict(offset=40,limit=1))],chunks=chunks)
add('read-stops-before-next-chunk',[action('read',range=dict(limit=1))],chunks=['a\nb','never-read'],textError='FS_NOT_TEXT')
add('read-backend-refusal',[action('read')],chunks=[],textError='FS_NOT_TEXT')
add('read-other-backend-error',[action('read')],chunks=[],textError='FS_PERMISSION_DENIED')
add('read-page-cap',[action('read')],chunks=['一','二','三'],config=dict(maxBytes=8))
add('read-separator-cap',[action('read')],chunks=['a\nb\n'],config=dict(maxBytes=2))
add('read-skip-large-prefix',[action('read',range=dict(offset=2,limit=1))],chunks=['not retained\nok\nlast'],config=dict(maxBytes=2))
for op,field in [('read','offset'),('read','limit'),('readBytes','offset'),('readBytes','length')]:
    for index,value in enumerate([None,True,False,-1,0,1.5,9007199254740992,2.0]):
        add('range-validation-'+op+'-'+field+'-'+str(index),[action(op,range={field:value})])
add('read-line-limit',[action('read',range=dict(limit=6))],config=dict(maxLines=5))
add('bytes-safe-sum',[action('readBytes',range=dict(offset=9007199254740991,length=1))])
add('bytes-cap',[action('readBytes',range=dict(length=6))],config=dict(maxBytes=5))
add('bytes-windows',[action('readBytes'),action('readBytes',range=dict(offset=2,length=2)),action('readBytes',range=dict(offset=5,length=1)),action('readBytes',range=dict(offset=90,length=1))])
add('bytes-unknown-size',[action('readBytes',range=dict(length=5)),action('readBytes',range=dict(length=6))],unknownSize=True)
add('read-all',[action('readAll')])
add('read-all-stat-cap',[action('readAll')],config=dict(maxFileBytes=4))
add('read-all-growth-cap',[action('readAll')],config=dict(maxFileBytes=4),size=3)
add('read-all-unknown-cap',[action('readAll')],config=dict(maxFileBytes=4),unknownSize=True)
add('read-outside-workspace',[action('read',path='../outside/file.txt'),action('readAll',path='/elsewhere/file')])
for index,relative in enumerate(['','/etc/passwd','\\outside','https://host','C:relative','file:///root','a\0b','../outside.css','sub\\image.png']):
    add('related-posix-'+str(index),[action('readRelated',path='index.html',relative=relative)])
add('related-windows',[action('readRelated',path='docs\\index.html',relative='..\\image.png')],root='C:\\project')
entries=[dict(name='a',type='file',size=2),dict(name='directory',type='directory'),dict(name='z',type='symlink')]
add('list-root',[action('list',path='.')],entryKind='directory',entries=entries)
add('list-child',[action('list',path='sub dir/汉字')],entryKind='directory',entries=entries,config=dict(maxEntries=2))
add('list-outside',[action('list',path='../outside')],entryKind='directory')
add('list-not-directory',[action('list',path='file')])
add('list-symlink',[action('list',path='link')],entryKind='symlink')
add('changes-queued-live-close',[action('change'),action('next'),action('observed',path='../outside',observation=dict(kind='present',version='outside')),action('observed',path='inside',observation=dict(kind='absent')),action('next'),action('close'),action('next')],openingObservations=[dict(path='during-resolve',observation=dict(kind='present',version='v2'))])
add('changes-abort-drops-queued',[action('change'),action('observed',path='inside',observation=dict(kind='present',version='v2')),action('abort'),action('next')])
add('changes-reconnect-independent',[action('change',name='old'),action('observed',path='first',observation=dict(kind='present',version='first')),action('change',name='new'),action('observed',path='second',observation=dict(kind='present',version='second')),action('next',name='old'),action('next',name='new'),action('close'),action('next',name='old'),action('next',name='new')])
add('changes-resolve-failure',[action('change')],resolveError='FS_PERMISSION_DENIED')
add('changes-preabort',[action('abort'),action('change')])
add('integer-overflow',[action('read',range=dict(offset=10**400))])
add('bytes-negative-zero',[action('readBytes',range=dict(offset=-0.0,length=1))])
for index,relative in enumerate(['İ:relative','ı:relative','a١:relative','ſ:relative','K:relative']):
    add('related-unicode-scheme-'+str(index),[action('readRelated',relative=relative)])

if __name__=='__main__':
    Path(__file__).with_name('workspace_files_current_cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

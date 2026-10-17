"""Host/icon inputs; expected observations must be frozen from original Source."""
import json
from pathlib import Path
cases=[]
def add(name,operation='routes',**values):cases.append(dict(case=name,kind='open-in-app-host-current',operation=operation,**values))
apps='/open-in-app/apps';icon='/open-in-app/icon';open_route='/open-in-app/open'
add('lazy-catalog-icon-launch',requests=[dict(path=apps),dict(path=apps),dict(path=icon+'/cursor'),dict(path=icon+'/cursor'),dict(path=open_route),dict(path=apps)])
for rejection in (401,403):add('auth-first-'+str(rejection),rejection=rejection,requests=[dict(path=apps,method='POST'),dict(path=icon+'/cursor'),dict(path=open_route,size=70000),dict(path=apps,rejection=None)])
for route in (apps,icon+'/cursor',open_route):
    for method in ('GET','POST','PUT','HEAD'):
        if method!=('POST' if route==open_route else 'GET'):add('method-'+str(len(cases)),requests=[dict(path=route,method=method)])
for i,headers in enumerate([{}, {'content-type':'text/plain'},{'content-type':'application/json-extra'},{'content-type':' APPLICATION/JSON ; charset=utf-8'},{'content-type':'\ufeffapplication/json\ufeff'}]):add('content-type-'+str(i),requests=[dict(path=open_route,headers=headers)])
for i,text in enumerate(['','{','null','[]','true','42','"body"','{"app":"cursor"}','{"path":"$ROOT/workspace"}','{"app":3,"path":"/"}','{"app":"cursor","path":false}','{"app":"cursor","path":"/","x":NaN}','\ufeff{"app":"cursor","path":"/"}']):add('body-'+str(i),requests=[dict(path=open_route,text=text)])
add('body-unreadable',requests=[dict(path=open_route,unreadable=True)])
for size in (65536,65537,131072):add('body-size-'+str(size),requests=[dict(path=open_route,size=size)])
for i,body in enumerate([dict(app='unknown',path='$ROOT/workspace'),dict(app='vscode',path='$ROOT/workspace'),dict(app='cursor',path=''),dict(app='cursor',path='relative'),dict(app='cursor',path='C:relative'),dict(app='cursor',path='$ROOT/missing'),dict(app='cursor',path='$ROOT/apps/Cursor.app/Contents/Resources/AppIcon.icns'),dict(app='cursor',path='$ROOT/workspace',extra='allowed')]):add('open-validation-'+str(i),requests=[dict(path=open_route,body=body)])
for suffix in ('/unknown','/vscode','/cursor/','/cursor?x=1','/cur%73or','/cursor/../unknown','/%2e/cursor','//cursor','cursor','/图标'):
    add('icon-path-'+str(len(cases)),requests=[dict(path=icon+suffix)])
for outcome in ('failed','missing'):
    add('launch-'+outcome,outcomes=[outcome,'launched'],requests=[dict(path=open_route),dict(path=apps)])
add('refresh-removes-stale',platform='linux',env=dict(XDG_DATA_DIRS=''),resolveFromDisk=True,executables=dict(code='$ROOT/tool.exe'),files={'tool.exe':''},outcomes=['missing'],removeOnLaunch='tool.exe',requests=[dict(path=apps),dict(path=open_route,body=dict(app='vscode',path='$ROOT/workspace')),dict(path=apps)])
# The capability resolver must stop proving the file after deletion. A file
# locator (GitHub Desktop) verifies both artifacts itself during refresh.
add('refresh-removes-file-launcher',platform='win32',env=dict(LOCALAPPDATA='$ROOT/local'),files={'local/GitHubDesktop/app-2.0/GitHubDesktop.exe':'','local/GitHubDesktop/app-2.0/resources/app/cli.js':''},outcomes=['missing'],removeOnLaunch='local/GitHubDesktop/app-2.0/GitHubDesktop.exe',requests=[dict(path=apps),dict(path=open_route,body=dict(app='github',path='$ROOT/workspace')),dict(path=apps)])
add('refresh-evicts-icon-cache',outcomes=['missing','launched'],requests=[dict(path=icon+'/cursor'),dict(path=open_route),dict(path=icon+'/cursor')])
add('cache-null-icon',files={},requests=[dict(path=icon+'/cursor'),dict(path=icon+'/cursor')])
for source in ('process','project-env','user-env'):
    for marker in ('SSH_CONNECTION','SSH_TTY'):
        add('ssh-'+source+'-'+marker,layers=[dict(source=source,values={marker:'present'})],requests=[dict(path=apps),dict(path=icon+'/cursor'),dict(path=open_route)])
for name,settings in [('mac-declared',{}),('mac-fallback',dict(plist='bad JSON')),('mac-declared-missing',dict(plist='{"CFBundleIconFile":"Missing"}')),('mac-no-output',dict(noOutput=True)),('mac-command-failed',dict(commandFailure=True)),('mac-no-icon',dict(files={})),('mac-resolved-iconless',dict(resolved=dict(launch=dict(kind='argv',command='open',args=[]))))]:add(name,'icon',**settings)
for mode in ('success','no-output','failure'):
    add('windows-icon-'+mode,'icon',platform='win32',resolved=dict(launch=dict(kind='argv',command='$ROOT/tool.exe',args=[]),icon=dict(kind='executable',path="$ROOT/a b';&$(literal).exe")),noOutput=mode=='no-output',commandFailure=mode=='failure')
app=dict(id='test',platforms=dict(linux=dict(locators=[],desktopId='test')))
for name,files in [('theme-priority',{'data/applications/test.desktop':'[Desktop Entry]\nIcon=test','data/icons/hicolor/512x512/apps/test.png':'large','data/icons/hicolor/128x128/apps/test.png':'small','data/pixmaps/test.svg':'fallback'}),('scalable',{'data/applications/test.desktop':'[Desktop Entry]\nIcon=test','data/icons/hicolor/scalable/apps/test.svg':'<svg/>'}),('pixmap',{'data/applications/test.desktop':'[Desktop Entry]\nIcon=test','data/pixmaps/test.png':'pixmap'}),('absolute',{'data/applications/test.desktop':'[Desktop Entry]\nIcon=$ROOT/logo.svg','logo.svg':'<svg>absolute</svg>'}),('unsupported',{'data/applications/test.desktop':'[Desktop Entry]\nIcon=$ROOT/logo.icns','logo.icns':'unserved'}),('missing',{'data/applications/test.desktop':'[Desktop Entry]\nIcon=missing'})]:
    add('linux-icon-'+name,'icon',platform='linux',app=app,env=dict(XDG_DATA_HOME='$ROOT/data',XDG_DATA_DIRS=''),files=files,resolved=dict(launch=dict(kind='argv',command='app',args=[])))
Path(__file__).with_name('open_in_app_host_current_cases.json').write_text(json.dumps(cases,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')

"""Inputs only. Freeze expected values separately from unchanged Source output."""
import itertools
import json
from pathlib import Path

cases=[]
def add(name,operation,**values):cases.append(dict(case=name,kind='open-in-app-current',operation=operation,**values))
add('catalog','catalog')
for i,text in enumerate(['','code --new-window','"C:/Program Files/editor.exe" %F','"" bare',' leading','\ufeffeditor','\u0085editor','one\u0085two',"'not-shell-quoted' arg",'"unterminated','\tcode']):add('exec-'+str(i),'exec',text=text)
add('exec-absent','exec')
for i,text in enumerate(['','Exec=ignored\n[Desktop Entry]\nExec=one %F\nIcon=art\nTryExec=check\n[Other]\nExec=ignored','[Desktop Entry]\r\n Exec = one=two \r\nExec=last\r\nTryExec=\r\nIcon=\ufefflogo\ufeff','[desktop entry]\nExec=no','[Desktop Entry]\n#Exec=no\n[Desktop Action Other]\nIcon=no','[Desktop Entry]\nExec=\u0085odd\u0085\n[Desktop Entry]\nTryExec=ok']):add('desktop-'+str(i),'desktop',text=text)
for i,text in enumerate(['','${ROOT}/editor','${EMPTY}/editor','${MISSING}/editor','${ROOT}${MISSING}','~/Applications/App.app','~\\App','${ROOT}/../x','${}/literal','%ROOT%','\ufeff~/file']):add('expand-'+str(i),'expand',text=text,env=dict(ROOT='R',EMPTY=''))
for i,env in enumerate([{},dict(XDG_DATA_HOME='',XDG_DATA_DIRS=''),dict(XDG_DATA_HOME='data',XDG_DATA_DIRS='one::two:'),dict(XDG_DATA_DIRS='C:/one:D:/two'),dict(XDG_DATA_HOME='\ufeff'),dict(XDG_DATA_DIRS=' : ') ]):add('xdg-'+str(i),'xdg',env=env)
add('registry-parser','registry',text='    (Default) REG_SZ orphan\nHKEY_CURRENT_USER\\App\\one.exe\r\n    (默认)    REG_EXPAND_SZ    "%ROOT%/one.exe"  \r\n    Path    REG_SZ    A B C\r\n    Value    REG_DWORD    0x1\r\nHKEY_CURRENT_USER\\App\\two.exe\n    (Standard)    REG_SZ    two.exe\nHKEY_CURRENT_USER\\App\\one.exe\n    (Default)    REG_SZ    replacement\n')
add('registry-blank-values','registry',text='HKCU\\one\n    (Default)    REG_SZ    \n    File name    REG_SZ    one\n    (Not default)    REG_SZ    value\n    Name REG_MULTI_SZ ignored\n')
for i,values in enumerate([['app-2024.1.9','app-2024.1.10','app-2023.9'],['app-02','app-2','app-10','app-1'],['app-a','app-A','app-á','app-_','app--'],['app-２','app-١٠','app-3'],['app-1.10','app-1.2','app-1.01','app-1.1']]):add('numeric-collation-'+str(i),'versions',values=values)
for primary,fallback in itertools.product(('launched','failed','missing'),repeat=2):
    add('launch-'+primary+'-'+fallback,'launch',path="C:/work space/a';$(literal)",resolved=dict(launch=dict(kind='argv',command='primary',args=['--cd={path}/{path}'],env=dict(EXPLICIT_SECRET='adapter'),windowsHide=True),fallbackLaunch=dict(kind='argv',command='fallback',args=['open'])),outcomes=[primary,fallback])
for outcome in ('launched','failed','missing'):add('launch-single-'+outcome,'launch',path='/one two',resolved=dict(launch=dict(kind='argv',command='editor',args=[])),outcomes=[outcome])
def resolved(name,locators,platform='win32',**values):
    add(name,'resolve',app=dict(id='test',platforms={platform:dict(locators=locators)}),platform=platform,**values)
resolved('fixed-icon-present',[dict(kind='fixed',launch=dict(kind='shell-open'),iconPath='${SystemRoot}/explorer.exe')],env=dict(SystemRoot='C:/Windows'))
resolved('fixed-icon-unset',[dict(kind='fixed',launch=dict(kind='shell-open'),iconPath='${SystemRoot}/explorer.exe')])
resolved('mac-app-priority',[dict(kind='app',fsNames=['Absent.app','First.app','Second.app'])],platform='darwin',directories=['apps/First.app','apps/Second.app'])
resolved('mac-app-absent',[dict(kind='app',fsNames=['Absent.app'])],platform='darwin')
resolved('xcode',[dict(kind='xcode')],platform='darwin',directories=['apps/Xcode Beta.app'],commands={'xcode-select':'$ROOT/apps/Xcode Beta.app/Contents/Developer\n'})
resolved('xcode-invalid',[dict(kind='xcode')],platform='darwin',directories=['apps/no-app'],commands={'xcode-select':'$ROOT/apps/no-app/Contents/Developer\n'})
resolved('xcode-command-failed',[dict(kind='xcode')],platform='darwin')
for platform in ('win32','darwin','linux','freebsd'):
    for desktop in (False,True):
        for available in (False,True):
            resolved('cli-'+platform+'-'+str(desktop)+'-'+str(available),[dict(kind='cli',name='editor',args=['--new'],requiresDesktop=desktop)],platform=platform,executables={'editor':'$ROOT/editor'} if available else {})
resolved('linux-desktop-visible',[dict(kind='cli',name='editor',args=[],requiresDesktop=True)],platform='linux',env=dict(DISPLAY=':1'),executables=dict(editor='$ROOT/editor'))
resolved('file-fallback',[dict(kind='file',candidates=['${MISSING}/absent','$ROOT/missing','$ROOT/dir','$ROOT/tool.exe','$ROOT/other.exe'],args=['.'])],files={'tool.exe':'','other.exe':''},directories=['dir'])
resolved('file-none',[dict(kind='file',candidates=['$ROOT/missing','$ROOT/dir'],args=[])],directories=['dir'])
resolved('scan-newest-valid',[dict(kind='scan',root='$ROOT/install',namePrefix='IDE ',relativeLauncher='bin/app.exe',args=[])],files={'install/IDE 2024.1.9/bin/app.exe':'','install/IDE 2024.1.10/bin/app.exe':'','install/IDE 2025.1/no.exe':''})
resolved('scan-missing',[dict(kind='scan',root='$ROOT/none',namePrefix='IDE',relativeLauncher='app.exe',args=[])])
resolved('github-version',[dict(kind='github-desktop',root='$ROOT/GitHub')],files={'GitHub/app-2.9/GitHubDesktop.exe':'','GitHub/app-2.9/resources/app/cli.js':'','GitHub/app-2.10/GitHubDesktop.exe':'','GitHub/app-2.10/resources/app/cli.js':'','GitHub/app-3.0/GitHubDesktop.exe':''})
resolved('github-missing-pair',[dict(kind='github-desktop',root='$ROOT/GitHub')],files={'GitHub/app-3.0/GitHubDesktop.exe':''})
roots=['HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths','HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths','HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall','HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall','HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall']
commands={roots[0]:'HKCU\\App\\EDITOR.EXE\n    (默认) REG_SZ "$ROOT/user.exe"\nHKCU\\App\\missing.exe\n    (Default) REG_EXPAND_SZ %UNSET%/missing.exe\n',roots[1]:'HKLM\\App\\editor.exe\n    (Default) REG_SZ "$ROOT/machine.exe"\n',roots[2]:'HKCU\\Uninstall\\tool\n    DisplayName REG_SZ Tool Personal\n    InstallLocation REG_EXPAND_SZ "%APP_HOME%"\n    DisplayIcon REG_SZ "$ROOT/icon.exe",-2\n',roots[4]:'HKLM\\Uninstall\\fallback\n    DisplayName REG_SZ Tool Other\n    DisplayIcon REG_SZ "$ROOT/fallback.exe",0\n'}
add('registry-view-precedence','registry-view',commands=commands,env=dict(APP_HOME='$ROOT/install'))
for name,loc in [('app-paths',dict(kind='app-paths',exe='editor.EXE',args=[])),('install-relative',dict(kind='install-record',displayNamePrefix='Tool',relativeLauncher='bin/app.exe',args=[])),('install-icon',dict(kind='install-record',displayNamePrefix='Tool',relativeLauncher='missing.exe',args=[])),('install-later-record',dict(kind='install-record',displayNamePrefix='Tool',args=[]))]:
    files={'user.exe':'','machine.exe':'','install/bin/app.exe':'','icon.exe':'','fallback.exe':''}
    if name=='install-later-record':del files['icon.exe']
    resolved(name,[loc],commands=commands,env=dict(APP_HOME='$ROOT/install'),files=files)
resolved('registry-no-files',[dict(kind='app-paths',exe='editor.exe',args=[]),dict(kind='install-record',displayNamePrefix='Tool',args=[])],commands=commands)
for name,text,executables in [('tryexec','[Desktop Entry]\nExec=wrong %F\nTryExec=right',dict(right='$ROOT/right')),('exec','[Desktop Entry]\nExec="editor cli" %F',{'editor cli':'$ROOT/editor'}),('empty-tryexec','[Desktop Entry]\nExec=right\nTryExec=',dict(right='$ROOT/right')),('missing','[Desktop Entry]\nExec=absent',{}),('absolute','[Desktop Entry]\nTryExec=$ROOT/tool.exe',{})]:
    resolved('desktop-'+name,[dict(kind='desktop',desktopId='test',args=['--new'])],platform='linux',files={'data/applications/test.desktop':text,'tool.exe':''},env=dict(XDG_DATA_HOME='$ROOT/data',XDG_DATA_DIRS=''),executables=executables)
resolved('locator-order',[dict(kind='file',candidates=['$ROOT/none'],args=[]),dict(kind='cli',name='first',args=['first']),dict(kind='cli',name='second',args=['second'])],executables=dict(first='$ROOT/first',second='$ROOT/second'))
resolved('ssh-no-probe',[dict(kind='cli',name='editor',args=[])],ssh=True,executables=dict(editor='$ROOT/editor'))
add('all-ssh-no-probe','all',ssh=True)
add('all-unknown-platform','all',platform='freebsd')
Path(__file__).with_name('open_in_app_current_cases.json').write_text(json.dumps(cases,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')

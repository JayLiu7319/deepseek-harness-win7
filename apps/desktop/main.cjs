'use strict';
const {app,BrowserWindow,protocol,ipcMain,Menu,Tray,nativeImage,dialog}=require('electron');
const {join,resolve,extname}=require('node:path');
const {readFile}=require('node:fs/promises');
const {Readable}=require('node:stream');
const {DesktopProjectManager}=require('./project-manager.cjs');
const {resolveDesktopLocale}=require('./locale.cjs');
const {desktopHome}=require('./home.cjs');

protocol.registerSchemesAsPrivileged([{scheme:'dsh-app',privileges:{standard:true,secure:true,supportFetchAPI:true,corsEnabled:false,stream:true}}]);
const development=!app.isPackaged;
const option=name=>{const index=process.argv.indexOf(name);return index<0?undefined:process.argv[index+1];};
if(!development&&process.argv.some(value=>['--root','--python','--home','--test-output'].includes(value)))throw new Error('Development overrides unavailable in packaged Desktop');
const root=development?resolve(option('--root')??join(__dirname,'../..')):join(process.resourcesPath,'harness');
const home=desktopHome(development&&option('--home')||process.env.DSH_HOME,app.getPath('home'));
app.setPath('userData',join(home,'desktop','electron'));
const primary=app.requestSingleInstanceLock();
let mainWindow,pluginWindow,manager,tray,stopping=false,allowQuit=false;
function focus(){
  if(!app.isReady())return;
  if(!mainWindow||mainWindow.isDestroyed())mainWindow=createWindow(false);
  if(mainWindow.isMinimized())mainWindow.restore();mainWindow.show();mainWindow.focus();
}
if(!primary)app.quit();
else app.on('second-instance',focus);
const mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.svg':'image/svg+xml'};
function assertSender(event){
  const frame=event.senderFrame;
  const url=frame&&new URL(frame.url);
  if(!frame||frame!==event.sender.mainFrame||url.protocol!=='dsh-app:'||url.host!=='shell'||url.username||url.password)throw new Error('Desktop IPC from unowned renderer');
}
function createWindow(shell){
  const window=new BrowserWindow({width:shell?900:1280,height:shell?620:840,minWidth:880,minHeight:600,show:false,
    title:shell?'DeepSeek Harness — Desktop Plugins':'DeepSeek Harness',webPreferences:{
      preload:join(__dirname,shell?'preload.cjs':'preload-app.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
  const expected=shell?'shell':'app';
  window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  window.webContents.on('will-navigate',(event,url)=>{try{const parsed=new URL(url);if(parsed.protocol!=='dsh-app:'||parsed.hostname!==expected)event.preventDefault();}catch{event.preventDefault();}});
  window.once('ready-to-show',()=>{if(!window.isDestroyed())window.show();});
  window.on('close',event=>{if(!shell&&!stopping){event.preventDefault();window.hide();}});
  window.loadURL('dsh-app://'+expected+(shell?'/plugin-manager.html':'/index.html')).catch(error=>console.error(error));
  return window;
}
function openPlugins(){if(pluginWindow&&!pluginWindow.isDestroyed()){pluginWindow.show();pluginWindow.focus();}else pluginWindow=createWindow(true);}
async function resource(request){
  const url=new URL(request.url);
  if(url.protocol!=='dsh-app:'||!['app','shell'].includes(url.hostname))return {status:403,headers:[],body:Readable.from([])};
  if(url.hostname==='shell'){
    if(!['GET','HEAD'].includes(request.method))return {status:405,headers:[],body:Readable.from([])};
    let path;try{path=decodeURIComponent(url.pathname);}catch{return {status:400,headers:[],body:Readable.from([])};}
    const allowed=['/plugin-manager.html','/plugin-manager.js','/plugin-manager.css'];
    if(!allowed.includes(path))return {status:404,headers:[],body:Readable.from([])};
    let bytes=await readFile(join(__dirname,'renderer',path.slice(1)));
    if(path==='/plugin-manager.html')bytes=Buffer.from(bytes.toString('utf8').replace('placeholder="@scope/plugin@1.2.3"','placeholder="C:\\plugins\\package.zip"'));
    return {status:200,headers:[['content-type',mime[extname(path)]??'application/octet-stream']],body:Readable.from(request.method==='HEAD'?[]:[bytes])};
  }
  const headers=Object.entries(request.headers??{});
  const uploads=request.uploadData??[];
  const body=uploads.length?(async function*(){
    const {createReadStream}=require('node:fs');
    for(const row of uploads){
      if(row.bytes)yield row.bytes;
      else if(row.file){for await(const data of createReadStream(row.file))yield data;}
      else throw new Error('Unsupported Electron upload body source');
    }
  })():null;
  return manager.host.fetch({url:request.url,method:request.method,headers,body});
}
async function main(){
  if(process.versions.electron!=='22.3.27')throw new Error('Pinned Electron22.3.27 required');
  manager=new DesktopProjectManager({python:development?resolve(option('--python')??join(root,'python.exe')):join(root,'python.exe'),root,home,profile:join(home,'profiles/desktop')});
  await manager.start();
  protocol.registerStreamProtocol('dsh-app',(request,callback)=>{
    resource(request).then(response=>{
      const headers={};for(const [name,value] of response.headers){if(headers[name])headers[name]=[].concat(headers[name],value);else headers[name]=value;}
      callback({statusCode:response.status,headers,data:response.body});
    },error=>{console.error(error);callback({statusCode:500,data:Readable.from(['Desktop request failed'])});});
  });
  const locale=resolveDesktopLocale(app.getLocale());
  locale.messages={...locale.messages,
    pluginManagerDescription:locale.id==='zh-CN'?'安装本地 Python 插件文件夹或 ZIP 包，仅作用于桌面端。':'Install a local Python plugin folder or ZIP package in Desktop.',
    npmPackage:locale.id==='zh-CN'?'插件文件夹或 ZIP 路径':'Plugin folder or ZIP path',
    targetVersion:locale.id==='zh-CN'?'输入 {name} 的升级 ZIP 或文件夹路径':'Enter the upgrade ZIP or folder path for {name}'};
  const register=(channel,handler)=>ipcMain.handle(channel,(event,...args)=>{assertSender(event);return handler(...args);});
  register('dsh-desktop:locale-get',()=>locale);
  register('dsh-desktop:plugins-list',()=>manager.list());
  const mutation=async(operation,value,name)=>{
    if(typeof value!=='string'||!value||value.length>32768||name!==undefined&&typeof name!=='string')throw new Error('Invalid Desktop package input');
    const window=mainWindow;
    if(window&&!window.isDestroyed())await window.loadURL('about:blank');
    try{await manager.mutate(operation,value,name);}
    finally{if(window&&!window.isDestroyed())await window.loadURL('dsh-app://app/index.html');}
  };
  register('dsh-desktop:plugins-add',spec=>mutation('add',spec));
  register('dsh-desktop:plugins-remove',name=>mutation('remove',name));
  register('dsh-desktop:plugins-update',(name,source)=>mutation('upgrade',source,name));
  Menu.setApplicationMenu(Menu.buildFromTemplate([{label:locale.messages.application,submenu:[
    {label:locale.messages.pluginsMenu,accelerator:'CmdOrCtrl+,',click:openPlugins},{type:'separator'},
    {label:locale.id==='zh-CN'?'退出':'Quit',click:()=>app.quit()}]}]));
  mainWindow=createWindow(false);
  const icon=nativeImage.createFromPath(join(__dirname,'tray.png'));
  if(icon.isEmpty())throw new Error('Desktop tray image is missing or invalid');
  tray=new Tray(icon);tray.setToolTip('DeepSeek Harness');tray.on('double-click',focus);
  tray.setContextMenu(Menu.buildFromTemplate([{label:'DeepSeek Harness',click:focus},{label:locale.messages.pluginsMenu,click:openPlugins},
    {type:'separator'},{label:locale.id==='zh-CN'?'退出':'Quit',click:()=>app.quit()}]));
  app.on('activate',focus);
  if(development&&option('--test-output'))await require('./smoke-test.cjs').run({app,mainWindow,openPlugins,
    pluginWindow:()=>pluginWindow,manager,output:resolve(option('--test-output'))});
}
app.on('window-all-closed',()=>{});
app.on('before-quit',event=>{
  if(allowQuit)return;
  event.preventDefault();if(stopping)return;stopping=true;
  Promise.resolve(manager?.close()).catch(error=>console.error(error)).finally(()=>{
    tray?.destroy();allowQuit=true;app.quit();
  });
});
if(primary)app.whenReady().then(main).catch(async error=>{
  console.error(error);
  if(!development||!option('--test-output'))dialog.showErrorBox('DeepSeek Harness',error.message);
  await manager?.close().catch(()=>{});allowQuit=true;app.exit(1);
});

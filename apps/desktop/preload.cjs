'use strict';
const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('dshDesktop',{
  protocolVersion:1,
  locale:()=>ipcRenderer.invoke('dsh-desktop:locale-get'),
  plugins:{
    list:()=>ipcRenderer.invoke('dsh-desktop:plugins-list'),
    add:spec=>ipcRenderer.invoke('dsh-desktop:plugins-add',spec),
    remove:name=>ipcRenderer.invoke('dsh-desktop:plugins-remove',name),
    update:(name,version)=>ipcRenderer.invoke('dsh-desktop:plugins-update',name,version),
  },
  updates:{
    check:()=>ipcRenderer.invoke('dsh-desktop:updates-check'),
    install:()=>ipcRenderer.invoke('dsh-desktop:updates-install'),
    subscribe(listener){
      if(typeof listener!=='function')throw new TypeError('Update listener must be a function');
      const handle=(_event,state)=>listener(state);
      ipcRenderer.on('dsh-desktop:updates-state',handle);
      return ()=>ipcRenderer.off('dsh-desktop:updates-state',handle);
    },
  },
});

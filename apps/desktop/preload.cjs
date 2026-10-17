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
});

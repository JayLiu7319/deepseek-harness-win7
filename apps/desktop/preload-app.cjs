'use strict';
const {contextBridge}=require('electron');
contextBridge.exposeInMainWorld('dshDesktop',{protocolVersion:1});

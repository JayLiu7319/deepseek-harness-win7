'use strict';
const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('dshDesktop',{protocolVersion:1});
window.addEventListener('DOMContentLoaded',async()=>{
  if(location.protocol!=='dsh-app:'||location.hostname!=='app'||window.top!==window)return;
  try{
    const state=await ipcRenderer.invoke('dsh-desktop:environment-get');
    if(!state.limitedShell||localStorage.getItem('dsh-win7-environment-dismissed')==='1')return;
    const chinese=state.locale==='zh-CN',notice=document.createElement('aside');
    notice.id='dsh-win7-environment-notice';notice.setAttribute('role','status');
    Object.assign(notice.style,{position:'fixed',top:'8px',left:'50%',transform:'translateX(-50%)',zIndex:'2147483647',
      padding:'10px 14px',border:'1px solid #82a7de',borderRadius:'8px',background:'#eef5ff',color:'#18314d',font:'14px Segoe UI,sans-serif',maxWidth:'85vw',boxShadow:'0 2px 8px #0002'});
    const text=document.createElement('span');text.textContent=chinese?'基础环境可继续使用；升级 PowerShell 5.1 可改善终端与自动化兼容性。':'Basic use is available. PowerShell 5.1 improves terminal and automation compatibility. ';
    const guide=document.createElement('button');guide.textContent=chinese?'查看离线升级指南':'Offline setup guide';guide.type='button';
    guide.addEventListener('click',()=>{ipcRenderer.invoke('dsh-desktop:setup-guide').catch(()=>{});});
    const close=document.createElement('button');close.textContent='×';close.type='button';close.setAttribute('aria-label',chinese?'关闭环境提示':'Dismiss environment notice');
    close.addEventListener('click',()=>{localStorage.setItem('dsh-win7-environment-dismissed','1');notice.remove();});
    notice.append(text,guide,close);document.body.append(notice);
  }catch(error){console.error('Desktop environment notice:',error);}
},{once:true});

'use strict';
const {execFile}=require('node:child_process');
const {join}=require('node:path');

// PowerShell2 can report its own version without ConvertTo-Json or .NET4.
function desktopEnvironment(run=execFile){
  const script="$v=$PSVersionTable.PSVersion; if($v.Major -gt 5 -or ($v.Major -eq 5 -and $v.Minor -ge 1)){'ready'}else{'limited'}";
  return new Promise(resolve=>run(join(process.env.SystemRoot||'C:\\Windows','System32/WindowsPowerShell/v1.0/powershell.exe'),
    ['-NoProfile','-NonInteractive','-EncodedCommand',Buffer.from(script,'utf16le').toString('base64')],
    {windowsHide:true,timeout:10000,maxBuffer:4096},(error,stdout)=>{
      const status=error?'unknown':String(stdout).trim();
      resolve({limitedShell:status!=='ready',status:['ready','limited'].includes(status)?status:'unknown'});
    }));
}
module.exports={desktopEnvironment};

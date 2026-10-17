'use strict';
// A GUI launched by a short-lived terminal can outlive its inherited log pipes.
// Electron also writes IPC rejection diagnostics through these streams.
function handleBrokenPipe(error){
  if(error.code!=='EPIPE')throw error;
}
function protectStdio(streams=[process.stdout,process.stderr]){
  for(const stream of streams)stream.on('error',handleBrokenPipe);
}
module.exports={protectStdio};

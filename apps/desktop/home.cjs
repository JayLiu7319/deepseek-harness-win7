'use strict';
const {resolve,join}=require('node:path');
function desktopHome(value,userHome){
  value=typeof value==='string'?value.trim():'';
  if(!value)return join(userHome,'.dsh');
  if(value==='~')return userHome;
  if(value.startsWith('~/')||value.startsWith('~\\'))value=join(userHome,value.slice(2));
  return resolve(value);
}
module.exports={desktopHome};

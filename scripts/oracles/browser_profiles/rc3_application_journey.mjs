/** Original UI gestures, with read-only Host observations for postconditions. */
import assert from 'node:assert/strict';
import {join,resolve} from 'node:path';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';

export async function applicationJourney({cdp,click,until,state,phase,snapshot,submit,complete,workspace,runDir}){
  const observed=state.application={};
  // The controlled Host has telemetry disabled; this records local feedback.
  const before=await snapshot();
  await click(cdp,'button[aria-label="Good response"]');
  await until(()=>cdp.evaluate(`!!document.querySelector('[role="dialog"] textarea[aria-label="Feedback details"]')`),'original feedback dialog');
  await click(cdp,'[role="group"][aria-label="Feedback category"] button','Task result');
  await click(cdp,'textarea[aria-label="Feedback details"]');
  const note='RC3_LOCAL_FEEDBACK_'+phase;
  await cdp.call('Input.insertText',{text:note});
  await click(cdp,'[role="dialog"] button','Submit');
  observed.feedback=await until(async()=>{
    const value=await snapshot();
    const records=value.events.filter(event=>event.type==='feedback/message-put'&&event.data.item.note===note);
    return records.length===1&&{event:records[0],requests:value.requests.length};
  },'persisted feedback event');
  assert.equal(observed.feedback.event.data.item.category,'task-result');
  assert.equal(observed.feedback.requests,before.requests.length);
  await until(()=>cdp.evaluate(`!!document.querySelector('button[aria-label="Remove rating"][aria-pressed="true"]')`),'recorded positive rating');
  await click(cdp,'button[aria-label="Remove rating"][aria-pressed="true"]');
  await until(()=>cdp.evaluate(`!document.querySelector('button[aria-label="Remove rating"][aria-pressed="true"]')`),'rating retraction');
  observed.feedbackDelete=await until(async()=>{const value=await snapshot();return value.events.find(event=>
    event.type==='feedback/message-delete'&&event.data.messageId===observed.feedback.event.data.item.messageId);},'authoritative feedback deletion');
  // A real browser file-input selection goes through the original upload Worker
  // and Host receipt. No attachment object or RPC response is fabricated.
  const name='rc3-upload-'+phase+'.txt',body='RC3_UPLOAD_IMMUTABLE_BYTES_'+phase+'\n';
  const path=resolve(join(workspace,name));await writeFile(path,body,'utf8');
  const {root}=await cdp.call('DOM.getDocument');
  const {nodeId}=await cdp.call('DOM.querySelector',{nodeId:root.nodeId,selector:'[data-composer-card] input[type="file"]'});
  assert.ok(nodeId);
  await cdp.evaluate(`window.__rc3FileChanges=[];document.querySelector('[data-composer-card] input[type="file"]').addEventListener('change',event=>window.__rc3FileChanges.push({trusted:event.isTrusted,names:[...event.target.files].map(file=>file.name)}),{once:true})`);
  await cdp.call('DOM.setFileInputFiles',{nodeId,files:[path]});
  observed.uploadCard=await until(()=>cdp.evaluate(`(()=>{const card=[...document.querySelectorAll('[data-composer-card] [title]')].find(n=>n.getAttribute('title')===${JSON.stringify(name)});if(!card)return false;const text=card.textContent;return text.includes('TXT')&&!text.includes('Uploading')&&{text,buttons:[...card.querySelectorAll('button')].map(n=>n.getAttribute('aria-label'))};})()`),'original upload receipt becomes ready');
  observed.fileChanges=await cdp.evaluate('window.__rc3FileChanges');
  assert.deepEqual(observed.fileChanges,[{trusted:true,names:[name]}]);
  await submit('WEB_REOPEN');const after=await complete('WEB_REOPEN');
  const sha256=createHash('sha256').update(body).digest('hex');
  const saved=resolve(join(runDir,'home/attachments/v1/files',sha256.slice(0,2),sha256,name));
  const event=after.events.findLast(event=>event.type==='user/message'&&event.data.content.some(block=>block.type==='file'&&block.attachment.name===name));
  assert.ok(event);assert.deepEqual(event.data.content.find(block=>block.type==='file').attachment,
    {attachmentId:'sha256:'+sha256,name,bytes:Buffer.byteLength(body)});
  await writeFile(path,'CHANGED_ORIGINAL_AFTER_UPLOAD\n','utf8');
  assert.equal(await readFile(saved,'utf8'),body);
  const request=after.requests.findLast(row=>row.request.messages.some(message=>message.content.some(block=>
    block.type==='text'&&block.text.includes('verbatim read-only copy saved at '+JSON.stringify(saved)))));
  assert.ok(request,'The actual next model request must contain the immutable saved-path projection');
  assert.equal(JSON.stringify(request.request).includes('RC3_UPLOAD_IMMUTABLE_BYTES_'),false);
  observed.attachment={event,saved,sha256,sourceChanged:true,savedBytesUnchanged:true};
  observed.uploadRequest=request;
  observed.workers=await cdp.evaluate(`globalThis[Symbol.for('deepseek-win7.host.workers')]?.facts??null`);
  if(observed.workers){assert.equal(observed.workers.activeWorkers,0);assert.equal(observed.workers.activeUrls,0);assert.deepEqual(observed.workers.errors,[]);}
  // Verify the full original settings namespace is available over the actual
  // controller, then open and cancel an editor without using real credentials.
  await click(cdp,'button','Settings');
  await until(()=>cdp.evaluate(`!!document.querySelector('[role="dialog"][aria-modal="true"] nav')`),'settings shell');
  await click(cdp,'[role="dialog"] nav button','Models');
  observed.models=await until(()=>cdp.evaluate(`(()=>{const panel=document.querySelector('[role="dialog"]');const edit=panel?.querySelector('button[aria-label^="Edit DeepSeek"]');return edit&&!edit.disabled&&{text:panel.textContent,edit:edit.getAttribute('aria-label')};})()`),'original provider directory');
  await click(cdp,'button[aria-label^="Edit DeepSeek"]');
  observed.modelEditor=await until(()=>cdp.evaluate(`(()=>{const field=document.querySelector('input[aria-label="Base URL"]');return field&&{baseUrl:field.value,key:!!document.querySelector('input[aria-label="API key"]'),models:[...document.querySelectorAll('input[aria-label^="Model ID "]')].map(n=>n.value)};})()`),'provider editor schema');
  assert.equal(observed.modelEditor.key,true);
  assert.deepEqual(observed.modelEditor.models,['deepseek-flash','deepseek-v4-flash','deepseek-v4-pro','deepseek-v4-flash-vision-exp']);
  await click(cdp,'[role="dialog"] details > summary','Customized settings');
  const previousName=phase==='cold'?'RC3_MODEL_fresh':'DeepSeek-V41-Flash';
  assert.equal(await cdp.evaluate(`document.querySelector('input[aria-label="Display name 1"]').value`),previousName);
  const modelName='RC3_MODEL_'+phase;
  await click(cdp,'input[aria-label="Display name 1"]');
  await cdp.call('Input.dispatchKeyEvent',{type:'keyDown',key:'a',code:'KeyA',windowsVirtualKeyCode:65,modifiers:2});
  await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',key:'a',code:'KeyA',windowsVirtualKeyCode:65,modifiers:2});
  await cdp.call('Input.insertText',{text:modelName});
  await click(cdp,'[role="dialog"] button','Apply');
  observed.updatedModels=await until(async()=>{
    const value=await snapshot();
    return value.deepseekModels?.[0]?.name===modelName&&value.deepseekModels;
  },'actual provider catalog after settings Apply');
  await until(()=>cdp.evaluate(`!document.querySelector('input[aria-label="Display name 1"]')`),'saved provider editor closes');
  await click(cdp,'button[aria-label^="Edit DeepSeek"]');
  observed.reopenedModelName=await until(()=>cdp.evaluate(`document.querySelector('input[aria-label="Display name 1"]')?.value===${JSON.stringify(modelName)}&&${JSON.stringify(modelName)}`),'persisted model editor reopens');
  await click(cdp,'[role="dialog"] button','Cancel');
  await cdp.call('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
  await until(()=>cdp.evaluate(`!document.querySelector('[role="dialog"][aria-modal="true"]')`),'settings closes');
  observed.passed=true;
}

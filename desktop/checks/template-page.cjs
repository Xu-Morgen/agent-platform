const {app}=require('electron'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {Backend}=require('../main/backend.cjs'),{openDesktop}=require('../main/desktop.cjs');
const watchdog=setTimeout(()=>app.exit(1),30000);
app.whenReady().then(async()=>{
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'flow-template-'));
 await fs.cp(path.resolve('samples/template'),dir,{recursive:true});
 const file=path.join(dir,'blocks/text.py');await fs.writeFile(file,(await fs.readFile(file,'utf8')).replace('template-text','copied-text'));
 const backend=new Backend(),window=await openDesktop(backend),run=s=>window.webContents.executeJavaScript(s);
 const wait=e=>run(`new Promise((resolve,reject)=>{const end=Date.now()+6000;const check=()=>{if(${e})resolve();else if(Date.now()>end)reject(new Error('UI timeout'));else setTimeout(check,20)};check()})`);
 try{
  await wait("document.querySelector('#status').textContent.includes('后端已就绪')");
  await run(`location.hash='/services';document.querySelector('#load-path').value=${JSON.stringify(file)};document.querySelector('#load-form').requestSubmit()`);
  await wait("document.querySelector('#load-result').textContent.startsWith('已加载')");await run('flowEditor.refresh()');
  await run(`window.pick=(selector,text)=>{const s=document.querySelector(selector);s.value=[...s.options].find(o=>o.text===text).value;s.dispatchEvent(new Event('change'))};
   document.querySelector('#service-name').value='复制模板页面';document.querySelector('#service-name').dispatchEvent(new Event('input'));
   pick('#flow-input','文本透传 · 输入');pick('#flow-output','文本透传 · 输出');
   document.querySelector('#module-library button').click();document.querySelector('#module-library button').click();
   document.querySelector('[data-node-id=node_1] > div > button').click();document.querySelector('[data-node-id=node_2] > div > button').click();
   pick('[data-node-id=node_2] select[aria-label="来源端口"]','node_1（完整值）');
   document.querySelector('#flow-output-bindings > button').click();pick('#flow-output-bindings select[aria-label="来源端口"]','node_2（完整值）');
   document.querySelector('#flow-example').value=JSON.stringify({text:'复制后的合成样例'});document.querySelector('#flow-example').dispatchEvent(new Event('change'));
   document.querySelector('#instance-save').click();`);
  await wait("document.querySelector('#service-result').textContent.includes('已保存版本')");
  await run("location.hash='/tasks';document.querySelector('#task-service-select').selectedIndex=1;document.querySelector('#task-service-select').dispatchEvent(new Event('change'));document.querySelector('#task-example').click()");
  await wait("document.querySelector('#task-input').value.includes('复制后的合成样例')");
  await run("document.querySelector('#task-form').requestSubmit()");await wait("document.querySelector('#task-result').textContent.includes('复制后的合成样例')");
  assert.match(await run("document.querySelector('#task-status').textContent"),/^completed/);
  console.log('PASS I8-T06: copied/renamed single-file template, real page load/assemble/example/save/call without model environment');
 }finally{await backend.stop();window.destroy();await fs.rm(dir,{recursive:true,force:true});clearTimeout(watchdog);app.quit()}
}).catch(e=>{console.error(e);app.exit(1)});

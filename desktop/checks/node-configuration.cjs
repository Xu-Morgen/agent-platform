const {app} = require('electron');
const assert = require('node:assert/strict');
const {Backend} = require('../main/backend.cjs');
const {openDesktop} = require('../main/desktop.cjs');
const watchdog = setTimeout(()=>app.exit(1),30000);
app.whenReady().then(async()=>{
  const backend=new Backend(), window=await openDesktop(backend);
  const run=s=>window.webContents.executeJavaScript(s);
  const wait=e=>run(`new Promise((resolve,reject)=>{const end=Date.now()+5000;const check=()=>{if(${e})resolve();else if(Date.now()>end)reject(new Error('UI timeout'));else setTimeout(check,20)};check()})`);
  try {
    await wait("document.querySelector('#status').textContent.includes('后端已就绪')");
    await run("location.hash='/services'");
    const environment=await run("window.agentPlatform.createEnvironment({name:'合成环境',connections:[{connectionId:'model',kind:'model',baseUrl:'http://127.0.0.1:9',model:'synthetic'}]})");
    assert.ok(environment.ok);
    await run("document.querySelector('#load-kind').value='package';document.querySelector('#load-path').value='examples/execution/model-package';document.querySelector('#load-form').requestSubmit()");
    await wait("document.querySelector('#load-result').textContent.startsWith('已加载')");await run('flowEditor.refresh()');
    await run("document.querySelector('#module-library button').click();document.querySelector('#module-library button').click()");
    assert.match(await run("document.querySelector('#flow-nodes').textContent"),/无效：尚未配置/);
    await run("document.querySelector('#global-strict').checked=false;document.querySelector('#global-strict').dispatchEvent(new Event('change'))");
    for (let i=1;i<=2;i++) {
      await run(`[...document.querySelectorAll('#flow-nodes button')].find(b=>b.textContent==='配置 node_${i}').click()`);
      await wait("document.querySelector('#node-dialog').open");
      if(i===1){
        await run("document.querySelector('#node-form').requestSubmit()");await wait("document.querySelector('#node-errors').textContent.includes('capabilities.chat')");
      }
      await run(`document.querySelector('[data-field=maxOutputTokens]').value=${i*64};document.querySelector('[data-capability=chat]').selectedIndex=1;document.querySelector('#node-form').requestSubmit()`);
      await wait("!document.querySelector('#node-dialog').open");
    }
    await run("document.querySelector('#draft-save').click()");await wait("document.querySelector('#draft-result').textContent.includes('草稿已保存')");
    const doc=await run("window.agentPlatform.getDraft(document.querySelector('#draft-select').value)");
    assert.equal(doc.data.content.nodeConfigurations.node_1.parameters.maxOutputTokens,64);
    assert.equal(doc.data.content.nodeConfigurations.node_2.parameters.maxOutputTokens,128);
    assert.equal(doc.data.content.nodeConfigurations.node_1.capabilities.chat.environmentId,environment.data.environmentId);
    assert.equal(doc.data.content.nodeConfigurations.node_1.budget.tokenLimit,1024);
    await run("[...document.querySelectorAll('#flow-nodes button')].find(b=>b.textContent==='配置 node_1').click()");
    await wait("document.querySelector('#node-dialog').open");
    await run("document.querySelector('[data-field=maxOutputTokens]').value=256;document.querySelector('#node-close').click()");
    await run("document.querySelector('#draft-save').click()");
    const after=await run("window.agentPlatform.getDraft(document.querySelector('#draft-select').value)");
    assert.equal(after.data.content.nodeConfigurations.node_1.parameters.maxOutputTokens,64);
    console.log('PASS I8-T02: independent package configs, manifest budgets, actual environment binding, field errors and cancel isolation; no model calls');
  } finally {await backend.stop();window.destroy();clearTimeout(watchdog);app.quit()}
}).catch(e=>{console.error(e);app.exit(1)});

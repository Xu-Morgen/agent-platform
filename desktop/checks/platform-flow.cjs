const {app} = require('electron');
const assert = require('node:assert/strict');
const {Backend} = require('../main/backend.cjs');
const {openDesktop} = require('../main/desktop.cjs');
const http=require('node:http'), {once}=require('node:events');
const watchdog = setTimeout(()=>app.exit(1),30000);
app.whenReady().then(async()=>{
  let hold=true, pending, calls=[];
  const respond=res=>res.end(JSON.stringify({choices:[{finish_reason:'stop',message:{role:'assistant',content:'{"text":"M1 协议替身"}'}}],usage:{prompt_tokens:2,completion_tokens:3}}));
  const server=http.createServer(async(req,res)=>{
    if(req.url==='/v1/models'){res.end(JSON.stringify({data:[{id:'synthetic'}]}));return;}
    const chunks=[];for await(const chunk of req)chunks.push(chunk);calls.push(JSON.parse(Buffer.concat(chunks)));
    pending=res;if(!hold)respond(res);
  });server.listen(0,'127.0.0.1');await once(server,'listening');
  const backend=new Backend(), window=await openDesktop(backend);
  const run=s=>window.webContents.executeJavaScript(s);
  const wait=e=>run(`new Promise((resolve,reject)=>{const end=Date.now()+5000;const check=()=>{if(${e})resolve();else if(Date.now()>end)reject(new Error('UI timeout'));else setTimeout(check,20)};check()})`);
  try {
    await wait("document.querySelector('#status').textContent.includes('后端已就绪')");
    await run("location.hash='/services'");
    await run(`location.hash='/environments';document.querySelector('#environment-name').value='M1 页面环境';document.querySelector('#connection-base-url').value='http://127.0.0.1:${server.address().port}/v1';document.querySelector('#connection-base-url').dispatchEvent(new Event('input'));document.querySelector('#connection-models').click()`);
    await wait("document.querySelector('#connection-tool-result').textContent.includes('获取到 1')");
    await run("document.querySelector('#connection-model-select').value='synthetic';document.querySelector('#connection-model-select').dispatchEvent(new Event('change'));document.querySelector('#environment-form').requestSubmit()");
    await wait("document.querySelector('#environment-result').textContent.includes('revision 1')");
    const environment={data:(await run('window.agentPlatform.listEnvironments()')).data[0]};
    await run("location.hash='/services'");
    await run("document.querySelector('#load-kind').value='package';document.querySelector('#load-path').value='samples/template/packages/example';document.querySelector('#load-form').requestSubmit()");
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
    assert.equal(doc.data.content.nodeConfigurations.node_1.budget.tokenLimit,32768);
    await run("[...document.querySelectorAll('#flow-nodes button')].find(b=>b.textContent==='配置 node_1').click()");
    await wait("document.querySelector('#node-dialog').open");
    await run("document.querySelector('[data-field=maxOutputTokens]').value=256;document.querySelector('#node-close').click()");
    await run("document.querySelector('#draft-save').click()");
    const after=await run("window.agentPlatform.getDraft(document.querySelector('#draft-select').value)");
    assert.equal(after.data.content.nodeConfigurations.node_1.parameters.maxOutputTokens,64);
    await run(`window.pick=(selector,text)=>{const s=document.querySelector(selector);s.value=[...s.options].find(o=>o.text===text).value;s.dispatchEvent(new Event('change'))};
      document.querySelector('#service-name').value='版本页面';document.querySelector('#service-name').dispatchEvent(new Event('input'));
      pick('#flow-input','标准模型交互包 · 输入');pick('#flow-output','标准模型交互包 · 输出');
      document.querySelector('[data-node-id=node_1] > div > button').click();
      document.querySelector('[data-node-id=node_2] > div > button').click();
      pick('[data-node-id=node_2] select[aria-label="来源端口"]','node_1（完整值）');
      document.querySelector('#flow-output-bindings > button').click();pick('#flow-output-bindings select[aria-label="来源端口"]','node_2（完整值）');
      document.querySelector('#instance-save').click();`);
    await wait("document.querySelector('#service-result').textContent.includes('已保存版本 1.0')");
    const original=await run("document.querySelector('#service-history li').dataset.instanceId");
    const serviceId=await run("document.querySelector('#service-select').value");
    await run(`location.hash='/tasks';document.querySelector('#task-service-select').value=${JSON.stringify(serviceId)};document.querySelector('#task-input').value=JSON.stringify({text:'M1 在途输入'});document.querySelector('#task-form').requestSubmit()`);
    await wait("document.querySelector('#task-steps').textContent.includes('model.node_1.chat')");
    assert.ok(pending);assert.equal(calls[0].max_completion_tokens,64);
    const busy=await run(`window.agentPlatform.updateEnvironment(${JSON.stringify(environment.data.environmentId)},${JSON.stringify({name:'占用更新',connections:environment.data.connections})})`);
    assert.equal(busy.ok,false);assert.equal(busy.error.code,'ENVIRONMENT_IN_USE');
    await run("location.hash='/services'");
    await run("[...document.querySelectorAll('#flow-nodes button')].find(b=>b.textContent==='配置 node_1').click()");
    await wait("document.querySelector('#node-dialog').open");
    await run("document.querySelector('[data-field=maxOutputTokens]').value=96;document.querySelector('#node-form').requestSubmit()");
    await wait("!document.querySelector('#node-dialog').open");
    await run("document.querySelector('#instance-save').click()");
    await wait("document.querySelector('#service-result').textContent.includes('已保存版本 1.1')");
    await run("document.querySelector('#service-history li button').click()");
    await wait("document.querySelector('#history-view').textContent.includes('只读实例')");
    assert.equal(await run("document.querySelectorAll('#history-view input,#history-view select,#history-view textarea').length"),0);
    assert.match(await run("document.querySelector('#history-view').textContent"),/64/);
    await run("document.querySelector('#service-history li button:nth-of-type(2)').click()");
    await wait("document.querySelector('#history-result').textContent.includes('已复制为草稿')");
    await run("document.querySelector('#service-history li button:nth-of-type(3)').click()");
    await wait("document.querySelector('#history-result').textContent.includes('已回退 1.0')");
    assert.ok((await run("document.querySelector('#service-current').textContent")).includes(original));
    hold=false;respond(pending);
    await wait("document.querySelector('#task-status').textContent.startsWith('completed')");
    await wait("document.querySelector('#task-result').textContent.includes('M1 协议替身')");
    assert.ok((await run("document.querySelector('#task-status').textContent")).includes(original));
    assert.equal(calls[1].max_completion_tokens,128);
    assert.match(await run("document.querySelector('#task-usage').textContent"),/loop 2/);
    await run("document.querySelector('#module-library button').click();document.querySelector('#instance-save').click()");
    await wait("document.querySelector('#flow-issues').textContent.includes('node_3')");
    assert.equal(await run("document.querySelectorAll('#service-history li').length"),2);
    console.log('PASS I8-T08: fresh session page environment/model discovery, template package node configs, save/run, inflight immutable version, env lock, history copy/rollback and errors; local HTTP substitute');
  } finally {await backend.stop();window.destroy();server.closeAllConnections();server.close();clearTimeout(watchdog);app.quit()}
}).catch(e=>{console.error(e);app.exit(1)});

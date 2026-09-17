const { app } = require('electron');
const { Backend } = require('../main/backend.cjs');
const { openDesktop } = require('../main/desktop.cjs');
const http = require('node:http');
const path = require('node:path');
const fs = require('node:fs/promises');
const os = require('node:os');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const watchdog = setTimeout(() => app.exit(1), 20000);
app.whenReady().then(async () => {
  let response;
  const server = http.createServer((req, res) => { req.resume(); response = res; });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const backend = new Backend();
  const window = await openDesktop(backend);
  const run = script => window.webContents.executeJavaScript(script);
  const wait = expression => run(`new Promise((resolve,reject)=>{const end=Date.now()+7000;const check=()=>{if(${expression}) resolve(); else if(Date.now()>end) reject(new Error('UI timeout')); else setTimeout(check,20);};check();})`);
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'platform-cancel-'));
  let passed = false;
  try {
    await run('window.agentPlatform.health()');
    const env = await run(`window.agentPlatform.createEnvironment(${JSON.stringify({name:'取消替身',connections:[{connectionId:'model',kind:'model',model:'synthetic',baseUrl:`http://127.0.0.1:${server.address().port}`,timeoutSeconds:2}]})})`);
    assert.ok(env.ok);
    await run(`window.agentPlatform.loadDefinition(${JSON.stringify({kind:'package',path:path.resolve(__dirname,'../../examples/execution/model-package')})})`);
    await fs.cp(path.resolve(__dirname,'../../examples/execution/model-instance'), dir, {recursive:true});
    const definition = JSON.parse(await fs.readFile(path.join(dir,'instance.json'),'utf8'));
    definition.environmentRefs = [env.data.environmentId]; definition.capabilityBindings[0].environmentId = env.data.environmentId;
    await fs.writeFile(path.join(dir,'instance.json'),JSON.stringify(definition));
    const loaded = await run(`window.agentPlatform.loadDefinition(${JSON.stringify({kind:'instance',path:dir})})`);
    assert.ok(loaded.ok, JSON.stringify(loaded));
    const saved = await run(`window.agentPlatform.createService(${JSON.stringify({name:'页面取消',definitionLoadId:loaded.data.loadId,definition:loaded.data.definition})})`);
    assert.ok(saved.ok);
    await run(`refreshServices(${JSON.stringify(saved.data.serviceId)})`);
    for (const mode of ['success','timeout']) {
      response = null;
      const previousId = await run("document.querySelector('#task-run-id').value");
      await run("document.querySelector('#task-input').value=JSON.stringify({text:'合成'});document.querySelector('#task-form').requestSubmit()");
      await wait(`document.querySelector('#task-run-id').value !== ${JSON.stringify(previousId)}`);
      await wait("document.querySelector('#task-steps').textContent.includes('model.assistant.chat')");
      assert.ok(response);
      await run("document.querySelector('#task-cancel').click()");
      await wait("document.querySelector('#task-cancel-status').textContent.includes('等待当前模型传输结束')");
      assert.equal(await run("document.querySelector('#task-result').textContent"), '');
      if (mode === 'success') {
        response.end(JSON.stringify({done:true,done_reason:'stop',message:{role:'assistant',content:'{"text":"合成"}'},prompt_eval_count:2,eval_count:3}));
        await wait("document.querySelector('#task-cancel-status').textContent==='已取消'");
        assert.match(await run("document.querySelector('#task-status').textContent"), /^cancelled/);
        assert.match(await run("document.querySelector('#task-usage').textContent"), /任务总量.*token 5/);
        assert.match(await run("document.querySelector('#task-usage').textContent"), /包 assistant.*token 5/);
      } else {
        await wait("document.querySelector('#task-status').textContent.startsWith('failed')");
        assert.match(await run("document.querySelector('#task-error').textContent"), /MODEL_TIMEOUT.*上游请求超时/);
        assert.match(await run("document.querySelector('#task-cancel-status').textContent"), /取消等待失败/);
      }
    }
    passed = true;
    console.log('I4-T11 PASS: real cancel button shows waiting then cancelled/failed; original timeout retained; real local/global usage displayed');
  } catch (error) { console.error(error); } finally {
    await backend.stop(); window.destroy(); server.closeAllConnections(); server.close(); await fs.rm(dir,{recursive:true,force:true}); clearTimeout(watchdog); app.exit(passed ? 0 : 1);
  }
}).catch(error => { console.error(error); app.exit(1); });

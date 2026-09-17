const { app } = require('electron');
const assert = require('node:assert/strict');
const http = require('node:http');
const { once } = require('node:events');
const { Backend } = require('../main/backend.cjs');
const { openDesktop } = require('../main/desktop.cjs');
const watchdog = setTimeout(() => app.exit(1), 30000);
app.whenReady().then(async () => {
  let mode = 'ok';
  let calls = 0;
  const server = http.createServer(async (request, response) => {
    calls++;
    assert.equal(request.headers.authorization, 'Bearer synthetic-key');
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    if (mode === 'delay') await new Promise(resolve => setTimeout(resolve, 200));
    if (mode === 'auth') {
      response.writeHead(401, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ error: 'synthetic-key' }));
      return;
    }
    response.setHeader('Content-Type', 'application/json');
    if (request.url === '/v1/models') response.end(JSON.stringify({ data: [{ id: 'test-model' }] }));
    else {
      assert.equal(request.url, '/v1/chat/completions');
      const body = JSON.parse(Buffer.concat(chunks));
      assert.equal(body.model, 'test-model');
      assert.equal(body.max_completion_tokens, 256);
      response.end(JSON.stringify({ choices: [{ finish_reason: 'stop', message: { role: 'assistant', content: '{"ok":true}' } }],
        usage: { prompt_tokens: 9, completion_tokens: 4 } }));
    }
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const backend = new Backend();
  const window = await openDesktop(backend);
  const run = script => window.webContents.executeJavaScript(script);
  const wait = expression => run(`new Promise((resolve,reject)=>{const end=Date.now()+6000;const check=()=>{if(${expression}) resolve(); else if(Date.now()>end) reject(new Error('UI timeout')); else setTimeout(check,20);};check();})`);
  const result = "document.querySelector('#connection-tool-result').textContent";
  try {
    assert.ok((await run('window.agentPlatform.health()')).ok);
    await run('refreshEnvironments()');
    await run(`location.hash='/environments'; document.querySelector('#connection-base-url').value='http://127.0.0.1:${server.address().port}/v1'; document.querySelector('#connection-base-url').dispatchEvent(new Event('input')); document.querySelector('#environment-credential').value='synthetic-key'; document.querySelector('#environment-credential').dispatchEvent(new Event('input')); document.querySelector('#environment-name').value='诊断环境'`);
    assert.equal(await run("document.querySelector('#environment-connections')"), null);
    await run("document.querySelector('#environment-form').requestSubmit()");
    await wait("document.querySelector('#environment-result').textContent.includes('请先获取模型')");
    assert.equal(calls, 0);
    await run("document.querySelector('#connection-models').click()");
    await wait(`${result}.includes('获取到 1')`);
    assert.equal(await run("document.querySelector('#connection-model-select').value"), '');
    assert.deepEqual(await run('window.agentPlatform.listEnvironments().then(r=>r.data)'), []);
    await run("document.querySelector('#connection-model-select').value='test-model'; document.querySelector('#connection-model-select').dispatchEvent(new Event('change')); document.querySelector('#connection-test').click()");
    await wait(`${result}.includes('测试通过')`);
    await run("document.querySelector('#environment-form').requestSubmit()");
    await wait("document.querySelector('#environment-result').textContent.includes('revision 1')");
    const saved = await run('window.agentPlatform.listEnvironments().then(r=>r.data[0])');
    assert.equal(saved.connections[0].connectionId, 'model');
    assert.equal(saved.connections[0].model, 'test-model');
    assert.ok(saved.connections[0].credentialRef);
    assert.equal(await run("document.querySelector('#environment-credential').value"), '');
    await run("document.querySelector('#connection-test').click()");
    await wait(`${result}.includes('测试通过')`);
    mode = 'auth';
    await run("document.querySelector('#connection-test').click()");
    await wait(`${result}.includes('HTTP 401')`);
    assert.ok(!(await run(result)).includes('synthetic-key'));
    mode = 'delay';
    const before = calls;
    await run("document.querySelector('#connection-models').click()");
    while (calls === before) await new Promise(resolve => setTimeout(resolve, 10));
    await run("document.querySelector('#connection-base-url').value='https://api.deepseek.com'; document.querySelector('#connection-base-url').dispatchEvent(new Event('input'))");
    await new Promise(resolve => setTimeout(resolve, 300));
    assert.equal(await run("document.querySelector('#connection-model-select').value"), '');
    assert.equal(await run("document.querySelector('#connection-model-select').disabled"), true);
    assert.equal(await run("document.querySelector('#connection-test').disabled"), true);
    console.log('PASS: real Electron draft discovery, dropdown model selection, inference, saved key reuse, HTTP error and stale response');
  } finally {
    await backend.stop(); window.destroy(); server.closeAllConnections(); server.close(); clearTimeout(watchdog); app.quit();
  }
}).catch(error => { console.error(error); app.exit(1); });

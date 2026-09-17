// 真实 Electron 主入口退出；模型为本地阻塞 HTTP 替身。
const { app, BrowserWindow } = require('electron');
const { backend } = require('../main/index.cjs');
const { Backend } = require('../main/backend.cjs');
const http = require('node:http');
const path = require('node:path');
const fs = require('node:fs/promises');
const os = require('node:os');
const assert = require('node:assert/strict');
const { once } = require('node:events');
let requestStarted, transportClosed;
const started = new Promise(r => { requestStarted = r; });
const closed = new Promise(r => { transportClosed = r; });
const server = http.createServer((req, res) => { req.resume(); res.on('close', transportClosed); requestStarted(); });
const watchdog = setTimeout(() => app.exit(1), 15000);
app.whenReady().then(async () => {
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const ready = await backend.start();
  const api = async (url, body) => {
    const response = await fetch(ready.address + '/api/v1' + url, {method: 'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const value = await response.json(); assert.ok(response.ok, JSON.stringify(value)); return value;
  };
  const env = await api('/environments', {name:'退出替身',connections:[{connectionId:'model',kind:'model',model:'synthetic',baseUrl:`http://127.0.0.1:${server.address().port}`,timeoutSeconds:60}]});
  await api('/registry/load', {kind:'package',path:path.resolve(__dirname,'../../examples/execution/model-package')});
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'platform-exit-'));
  await fs.cp(path.resolve(__dirname,'../../examples/execution/model-instance'), directory, {recursive:true});
  const source = JSON.parse(await fs.readFile(path.join(directory,'instance.json'), 'utf8'));
  source.environmentRefs = [env.environmentId]; source.capabilityBindings[0].environmentId = env.environmentId;
  await fs.writeFile(path.join(directory,'instance.json'), JSON.stringify(source));
  const loaded = await api('/registry/load', {kind:'instance',path:directory});
  await fs.rm(directory, {recursive:true,force:true});
  const definition = loaded.definition;
  definition.environmentRefs = [env.environmentId]; definition.capabilityBindings[0].environmentId = env.environmentId;
  definition.budget.strictTokenLimit = false;
  const svc = await api('/services', {name:'退出样例',definitionLoadId:loaded.loadId,definition});
  const run = await api('/runs', {serviceId:svc.serviceId,input:{text:'合成'}});
  await started;
  const queued = await api('/runs', {serviceId:svc.serviceId,input:{text:'排队'}});
  const before = Date.now();
  // before-quit 会等待 backend.stop；在真实退出前验收新进程内存清空。
  app.on('will-quit', event => {
    event.preventDefault();
    (async () => {
      await closed;
      assert.ok(Date.now() - before < 2000, '退出不应等待 60 秒模型超时');
      assert.equal(backend.child.exitCode, 0);
      const fresh = new Backend();
      const next = await fresh.start();
      for (const id of [run.runId, queued.runId]) assert.equal((await fetch(next.address + '/api/v1/runs/' + id)).status, 404);
      await fresh.stop(); server.close(); clearTimeout(watchdog);
      console.log('I4-T10 PASS: real window close aborts local model connection, clean backend exit <2s; restarted run IDs 404');
      app.exit(0);
    })().catch(error => { console.error(error); app.exit(1); });
  });
  for (const window of BrowserWindow.getAllWindows()) window.close();
}).catch(error => { console.error(error); app.exit(1); });

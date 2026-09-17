// 真实 Electron 主入口退出；模型为本地阻塞 HTTP 替身。
const { app, BrowserWindow } = require('electron');
const { backend } = require('../main/index.cjs');
const { Backend } = require('../main/backend.cjs');
const http = require('node:http');
const path = require('node:path');
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
  const pkg=await api('/catalog/load',{kind:'package',path:path.resolve(__dirname,'../../examples/execution/model-package')});
  const binding=source=>[{target:[],source}];
  const flow={name:'新版退出',inputContract:pkg.inputContract,outputContract:pkg.outputContract,
    flow:[{kind:'package',nodeId:'generate',artifactRef:pkg.resourceId,inputs:binding({kind:'input',path:[]})}],
    output:binding({kind:'node',nodeId:'generate',path:[]}),nodeConfigurations:{generate:{parameters:{maxOutputTokens:64},budget:{loopLimit:1,tokenLimit:1024},capabilities:{chat:{kind:'model',environmentId:env.environmentId,connectionId:'model'}}}},budget:{loopLimit:1,tokenLimit:1024,strictTokenLimit:false}};
  const svc=await api('/services',{name:'新版退出',flow});
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
      console.log('I8-T08 PASS: real window close aborts local model connection, clean backend exit <2s; restarted run IDs 404');
      app.exit(0);
    })().catch(error => { console.error(error); app.exit(1); });
  });
  for (const window of BrowserWindow.getAllWindows()) window.close();
}).catch(error => { console.error(error); app.exit(1); });

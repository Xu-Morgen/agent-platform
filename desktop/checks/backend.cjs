const { app } = require('electron');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const { Backend } = require('../main/backend.cjs');
const { createWindow } = require('../main/window.cjs');
const { openDesktop } = require('../main/desktop.cjs');
const watchdog = setTimeout(() => app.exit(1), 20000);
app.whenReady().then(async () => {
  const window = await createWindow();
  const backend = new Backend();
  try {
    const first = backend.start();
    assert.equal(first, backend.start());
    const ready = await first;
    assert.ok(ready.pid > 0);
    assert.equal((await (await fetch(`${ready.address}/api/v1/health`)).json()).status, 'ready');
    const failed = new Backend({ python: '/missing/python' });
    await assert.rejects(failed.start(), /解释器路径/);
    const failedWindow = await openDesktop(failed);
    await failedWindow.webContents.executeJavaScript('window.agentPlatform.health()');
    assert.match(await failedWindow.webContents.executeJavaScript('document.querySelector("#status").textContent'), /启动失败.*解释器路径/);
    failedWindow.close();
    console.log('T07 PASS: Electron owns one backend, ready + health, visible startup failure');
  } finally {
    const exited = once(backend.child, 'exit');
    backend.child.kill();
    await exited;
    clearTimeout(watchdog);
    window.close();
    app.quit();
  }
}).catch((error) => { console.error(error); app.exit(1); });

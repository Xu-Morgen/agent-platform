const { app } = require('electron');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const { Backend } = require('../main/backend.cjs');
const { openDesktop } = require('../main/desktop.cjs');
const watchdog = setTimeout(() => app.exit(1), 20000);
app.whenReady().then(async () => {
  const backend = new Backend();
  const window = await openDesktop(backend);
  try {
    const health = await window.webContents.executeJavaScript('window.agentPlatform.health()');
    assert.equal(health.ok, true);
    assert.equal(health.data.status, 'ready');
    assert.equal(await window.webContents.executeJavaScript('typeof window.agentPlatform.createEnvironment'), 'function');
    const pid = backend.child.pid;
    const loaded = once(window.webContents, 'did-finish-load');
    window.reload();
    await loaded;
    assert.equal((await window.webContents.executeJavaScript('window.agentPlatform.health()')).ok, true);
    assert.equal(backend.child.pid, pid);
    console.log('T08 PASS: real preload health bridge, page refresh retains backend PID');
  } finally {
    const exited = once(backend.child, 'exit');
    backend.child.kill();
    await exited;
    assert.equal((await window.webContents.executeJavaScript('window.agentPlatform.health()')).error.code, 'BACKEND_UNAVAILABLE');
    clearTimeout(watchdog);
    window.close();
    app.quit();
  }
}).catch((error) => { console.error(error); app.exit(1); });

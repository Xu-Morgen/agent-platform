const { app } = require('electron');
const assert = require('node:assert/strict');
const { once } = require('node:events');
const { Backend } = require('../main/backend.cjs');
const { openDesktop } = require('../main/desktop.cjs');
const watchdog = setTimeout(() => app.exit(1), 30000);
app.whenReady().then(async () => {
  const backend = new Backend();
  const window = await openDesktop(backend);
  const run = script => window.webContents.executeJavaScript(script);
  const wait = route => run(`new Promise((resolve, reject) => {
    const end = Date.now() + 5000;
    const check = () => {
      if (location.hash === '#/${route}' && document.querySelector('[data-page="${route}"]').hidden === false) resolve();
      else if (Date.now() > end) reject(new Error('Route timeout'));
      else setTimeout(check, 20);
    }; check();
  })`);
  try {
    assert.ok((await run('window.agentPlatform.health()')).ok);
    await wait('overview');
    for (const route of ['environments', 'services', 'tasks']) {
      await run(`document.querySelector('nav a[href="#/${route}"]').click()`);
      await wait(route);
      assert.ok((await run('window.agentPlatform.listServices()')).ok);
      assert.equal(await run("document.querySelectorAll('[data-page]:not([hidden])').length"), 1);
      assert.equal(await run("document.querySelector('nav [aria-current=page]').hash"), `#/${route}`);
    }
    await run("document.querySelector('#task-input').value = '{\"draft\":true}'; history.back()");
    await wait('services');
    await run('history.forward()');
    await wait('tasks');
    assert.equal(await run("document.querySelector('#task-input').value"), '{"draft":true}');
    const loaded = once(window.webContents, 'did-finish-load');
    window.reload();
    await loaded;
    await wait('tasks');
    assert.equal(await run("document.querySelector('#task-service-select').checkVisibility()"), true);
    await run("location.hash = '/missing'");
    await wait('overview');
    console.log('PASS: navigation, single visible page, back/forward, draft retention, reload and unknown route');
  } finally {
    await backend.stop(); window.destroy(); clearTimeout(watchdog); app.quit();
  }
}).catch(error => { console.error(error); app.exit(1); });

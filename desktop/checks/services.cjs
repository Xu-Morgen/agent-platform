const { app } = require('electron');
const assert = require('node:assert/strict');
const path = require('node:path');
const { Backend } = require('../main/backend.cjs');
const { openDesktop } = require('../main/desktop.cjs');
const watchdog = setTimeout(() => app.exit(1), 30000);
app.whenReady().then(async () => {
  const backend = new Backend();
  const window = await openDesktop(backend);
  const run = script => window.webContents.executeJavaScript(script);
  const wait = expression => run(`new Promise((resolve,reject)=>{const end=Date.now()+5000;const check=()=>{if(${expression}) resolve(); else if(Date.now()>end) reject(new Error('UI timeout')); else setTimeout(check,20);};check();})`);
  try {
    await run('window.agentPlatform.health()');
    for (const [kind, name] of [['block','block'],['package','package'],['package','second'],['instance','instance']]) {
      const directory = path.resolve(__dirname, '../../examples/configuration', name);
      await run(`document.querySelector('#load-kind').value=${JSON.stringify(kind)};document.querySelector('#load-path').value=${JSON.stringify(directory)};document.querySelector('#load-result').textContent='';document.querySelector('#load-form').requestSubmit()`);
      await wait("document.querySelector('#load-result').textContent.startsWith('已加载')");
    }
    assert.equal(await run("JSON.parse(document.querySelector('#service-definition').value).budget.loopLimit"), 4);
    await run("document.querySelector('#service-name').value='页面服务';document.querySelector('#service-form').requestSubmit()");
    await wait("document.querySelector('#service-result').textContent.includes('已保存版本 1.0')");
    assert.match(await run("document.querySelector('#service-current').textContent"), /svc_/);
    await run("const value=JSON.parse(document.querySelector('#service-definition').value);value.configRefs[0].values.loopLimit=3;document.querySelector('#service-definition').value=JSON.stringify(value);document.querySelector('#service-form').requestSubmit()");
    await wait("document.querySelector('#service-result').textContent.includes('已保存版本 1.1')");
    await run("const invalid=JSON.parse(document.querySelector('#service-definition').value);invalid.configRefs[0].values.loopLimit='bad';document.querySelector('#service-definition').value=JSON.stringify(invalid);document.querySelector('#service-form').requestSubmit()");
    await wait("document.querySelector('#service-result').textContent.includes('loopLimit')");
    console.log('I2-T09 PASS: real page loads two packages/configs, saves/edits, shows stable ID and field error');
    const original = await run("document.querySelector('#service-history button').dataset.instanceId");
    await run("document.querySelector('#service-history button').click()");
    await wait("document.querySelector('#history-result').textContent.includes('版本 1.0')");
    assert.ok((await run("document.querySelector('#service-current').textContent")).includes(original));
    assert.equal(await run("document.querySelectorAll('#service-history button').length"), 2);
    await backend.stop();
    const fresh = new Backend();
    const freshWindow = await openDesktop(fresh);
    try {
      await freshWindow.webContents.executeJavaScript('window.agentPlatform.health()');
      await freshWindow.webContents.executeJavaScript('refreshServices()');
      assert.equal(await freshWindow.webContents.executeJavaScript("document.querySelector('#service-select').options.length"), 1);
      assert.equal(await freshWindow.webContents.executeJavaScript("document.querySelectorAll('#service-history button').length"), 0);
    } finally { await fresh.stop(); freshWindow.destroy(); }
    console.log('I2-T11 PASS: real history button selects original A; fresh backend/window has no old history');
  } finally { await backend.stop(); window.destroy(); clearTimeout(watchdog); app.quit(); }
}).catch(error => { console.error(error); app.exit(1); });

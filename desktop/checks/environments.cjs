const { app } = require('electron');
const assert = require('node:assert/strict');
const { Backend } = require('../main/backend.cjs');
const { openDesktop } = require('../main/desktop.cjs');
const watchdog = setTimeout(() => app.exit(1), 20000);
app.whenReady().then(async () => {
  const backend = new Backend();
  const window = await openDesktop(backend);
  const run = script => window.webContents.executeJavaScript(script);
  try {
    await run('window.agentPlatform.health()');
    await run('refreshEnvironments()');
    await run(`connectionEditor.load([{connectionId:'deepseek',kind:'model',baseUrl:'https://api.deepseek.com',modelAdapter:'openai-chat',outputTokenParameter:'max_tokens',model:'saved-model',credential:'synthetic-secret'}])`);
    await run(`document.querySelector('#environment-name').value = '页面合成环境'; document.querySelector('#environment-credential').value = 'synthetic-secret'; document.querySelector('#environment-form').requestSubmit()`);
    await run(`new Promise((resolve, reject) => { const end = Date.now()+5000; const check=()=> { if (document.querySelector('#environment-result').textContent.includes('revision 1')) resolve(); else if(Date.now()>end) reject(new Error('create timeout')); else setTimeout(check,20); }; check(); })`);
    assert.equal(await run("document.querySelector('#environment-credential').value"), '');
    assert.equal(await run("document.querySelector('#environment-credential').type"), 'password');
    const saved = await run('window.agentPlatform.listEnvironments().then(r => r.data[0])');
    assert.equal(saved.connections[0].connectionId, 'deepseek');
    assert.ok(saved.connections[0].credentialRef);
    await run(`document.querySelector('#environment-name').value = '已修改'; document.querySelector('#environment-form').requestSubmit()`);
    await run(`new Promise((resolve, reject) => { const end=Date.now()+5000; const check=()=> { if(document.querySelector('#environment-result').textContent.includes('revision 2')) resolve(); else if(Date.now()>end) reject(new Error('update timeout')); else setTimeout(check,20); }; check(); })`);
    await run(`document.querySelector('#connection-base-url').value='invalid'; document.querySelector('#connection-base-url').dispatchEvent(new Event('input'))`);
    assert.equal(await run("document.querySelector('#connection-base-url').checkValidity()"), false);
    assert.equal(await run("document.querySelector('#connection-model-select').disabled"), true);
    console.log('I2-T03 PASS: real Electron form create/edit, password cleared, field error displayed');
  } finally { await backend.stop(); window.destroy(); clearTimeout(watchdog); app.quit(); }
}).catch(error => { console.error(error); app.exit(1); });

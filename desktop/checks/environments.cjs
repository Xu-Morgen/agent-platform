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
    await run(`document.querySelector('#environment-name').value = '页面合成环境'; document.querySelector('#environment-credential').value = 'synthetic-secret'; document.querySelector('#environment-form').requestSubmit()`);
    await run(`new Promise((resolve, reject) => { const end = Date.now()+5000; const check=()=> { if (document.querySelector('#environment-result').textContent.includes('revision 1')) resolve(); else if(Date.now()>end) reject(new Error('create timeout')); else setTimeout(check,20); }; check(); })`);
    assert.equal(await run("document.querySelector('#environment-credential').value"), '');
    assert.equal(await run("document.querySelector('#environment-credential').type"), 'password');
    await run(`document.querySelector('#environment-name').value = '已修改'; document.querySelector('#environment-form').requestSubmit()`);
    await run(`new Promise((resolve, reject) => { const end=Date.now()+5000; const check=()=> { if(document.querySelector('#environment-result').textContent.includes('revision 2')) resolve(); else if(Date.now()>end) reject(new Error('update timeout')); else setTimeout(check,20); }; check(); })`);
    await run(`const data=JSON.parse(document.querySelector('#environment-connections').value); data[0].baseUrl='invalid'; document.querySelector('#environment-connections').value=JSON.stringify(data); document.querySelector('#environment-form').requestSubmit()`);
    await run(`new Promise((resolve,reject)=> { const end=Date.now()+5000; const check=()=>{ if(document.querySelector('#environment-result').textContent.includes('baseUrl')) resolve(); else if(Date.now()>end) reject(new Error('error timeout')); else setTimeout(check,20); };check(); })`);
    console.log('I2-T03 PASS: real Electron form create/edit, password cleared, field error displayed');
  } finally { await backend.stop(); window.destroy(); clearTimeout(watchdog); app.quit(); }
}).catch(error => { console.error(error); app.exit(1); });

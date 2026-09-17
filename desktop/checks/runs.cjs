const { app } = require('electron');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const os = require('node:os');
const { once } = require('node:events');
const { Backend } = require('../main/backend.cjs');
const { openDesktop } = require('../main/desktop.cjs');
const watchdog = setTimeout(() => app.exit(1), 30000);
app.whenReady().then(async () => {
  const backend = new Backend();
  const window = await openDesktop(backend);
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'platform-runs-'));
  const run = script => window.webContents.executeJavaScript(script);
  const wait = expression => run(`new Promise((resolve,reject)=>{const end=Date.now()+7000;const check=()=>{if(${expression}) resolve(); else if(Date.now()>end) reject(new Error('UI timeout: '+${JSON.stringify(expression)})); else setTimeout(check,20);};check();})`);
  try {
    await run('window.agentPlatform.health()');
    for (const [kind, name] of [['block','block'],['package','package'],['package','second']]) {
      const result = await run(`window.agentPlatform.loadDefinition(${JSON.stringify({kind,path:path.resolve(__dirname,'../../examples/configuration',name)})})`);
      assert.ok(result.ok);
    }
    await fs.cp(path.resolve(__dirname,'../../examples/configuration/instance'), directory, {recursive:true});
    const workflow = path.join(directory, 'workflow.py');
    await fs.writeFile(workflow, (await fs.readFile(workflow,'utf8')).replace("'text': state.text", "'text': 42 if state.text == 'fail' else state.text"));
    const loaded = await run(`window.agentPlatform.loadDefinition(${JSON.stringify({kind:'instance',path:directory})})`);
    assert.ok(loaded.ok);
    const saved = await run(`window.agentPlatform.createService(${JSON.stringify({name:'任务页面合成',definitionLoadId:loaded.data.loadId,definition:loaded.data.definition})})`);
    assert.ok(saved.ok);
    await run(`refreshServices(${JSON.stringify(saved.data.serviceId)})`);
    await run("document.querySelector('#task-example').click()");
    await wait("document.querySelector('#task-input').value.includes('合成输入')");
    await run("document.querySelector('#task-form').requestSubmit()");
    await wait("document.querySelector('#task-result').textContent.includes('合成输入')");
    assert.match(await run("document.querySelector('#task-status').textContent"), /^completed/);
    const runId = await run("document.querySelector('#task-run-id').value");
    assert.match(await run("document.querySelector('#task-steps').textContent"), /nodes.identity/);
    const reloaded = once(window.webContents, 'did-finish-load');
    window.reload(); await reloaded;
    await run('window.agentPlatform.health()');
    await run(`document.querySelector('#task-run-id').value=${JSON.stringify(runId)};document.querySelector('#task-query-form').requestSubmit()`);
    await wait("document.querySelector('#task-result').textContent.includes('合成输入')");
    await run(`refreshServices(${JSON.stringify(saved.data.serviceId)})`);
    await run("document.querySelector('#task-input').value=JSON.stringify({text:'fail'});document.querySelector('#task-form').requestSubmit()");
    await wait("document.querySelector('#task-status').textContent.startsWith('failed')");
    assert.match(await run("document.querySelector('#task-error').textContent"), /nodes.identity.output/);
    assert.match(await run("document.querySelector('#task-steps').textContent"), /OUTPUT_VALIDATION_ERROR/);
    assert.equal(await run("document.querySelector('#task-result').textContent"), '');
    await run("document.querySelector('#task-input').value=JSON.stringify({text:42});document.querySelector('#task-form').requestSubmit()");
    await wait("document.querySelector('#task-error').textContent.includes('runs.input')");
    await run("document.querySelector('#task-run-id').value='missing';document.querySelector('#task-query-form').requestSubmit()");
    await wait("document.querySelector('#task-error').textContent.includes('RECORD_NOT_FOUND')");
    console.log('I3-T13 PASS: real Electron page submit/result, node failure/stage, refresh/query by runId, invalid input and 404');
  } finally {
    await backend.stop(); window.destroy(); await fs.rm(directory,{recursive:true,force:true}); clearTimeout(watchdog); app.quit();
  }
}).catch(error => { console.error(error); app.exit(1); });

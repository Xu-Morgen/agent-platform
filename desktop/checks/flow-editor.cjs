const {app} = require('electron');
const assert = require('node:assert/strict');
const {Backend} = require('../main/backend.cjs');
const {openDesktop} = require('../main/desktop.cjs');
const watchdog = setTimeout(() => app.exit(1),30000);
app.whenReady().then(async () => {
  const backend = new Backend(); const window = await openDesktop(backend);
  const run = script => window.webContents.executeJavaScript(script);
  const wait = expression => run(`new Promise((resolve,reject)=>{const end=Date.now()+6000;const check=()=>{if(${expression})resolve();else if(Date.now()>end)reject(new Error('UI timeout: '+${JSON.stringify(expression)}));else setTimeout(check,20)};check()})`);
  const select = async (selector, index) => run(`{const s=document.querySelector(${JSON.stringify(selector)});s.selectedIndex=${index};s.dispatchEvent(new Event('change'));}`);
  const click = selector => run(`document.querySelector(${JSON.stringify(selector)}).click()`);
  try {
    await wait("document.querySelector('#status').textContent.includes('后端已就绪')");
    await run("location.hash='/services'");
    for (const file of ['rename','condition']) {
      await run(`document.querySelector('#load-path').value='examples/flows/blocks/${file}.py';document.querySelector('#load-result').textContent='';document.querySelector('#load-form').requestSubmit()`);
      await wait("document.querySelector('#load-result').textContent.startsWith('已加载')");
      await run('flowEditor.refresh()');
    }
    await run("document.querySelector('#service-name').value='顺序页面';document.querySelector('#service-name').dispatchEvent(new Event('input'))");
    // 通过契约标签选择输入及输出，所有节点/接线都由真实页面控件创建。
    await run("{const s=document.querySelector('#flow-input');s.value=[...s.options].find(o=>o.text==='字段转换 · 输入').value;s.dispatchEvent(new Event('change'))}");
    await run("{const s=document.querySelector('#flow-output');s.value=[...s.options].find(o=>o.text==='非空条件 · 输出').value;s.dispatchEvent(new Event('change'))}");
    await run("[...document.querySelectorAll('#module-library button')].find(b=>b.textContent==='插入 非空条件').click()");
    await click('#flow-nodes fieldset > div > button');
    const invalid = await run('flowEditor.validate()');
    assert.equal(invalid.data.valid,false);
    assert.match(await run("document.querySelector('#flow-issues').textContent"),/node_1/);
    await run("[...document.querySelectorAll('#module-library button')].find(b=>b.textContent==='插入 字段转换').click()");
    await click('#flow-nodes fieldset:nth-child(2) > button'); // 上移转换块
    await click('#flow-nodes fieldset:first-child > div > button');
    await select('#flow-nodes fieldset:nth-child(2) .binding-row select[aria-label="来源端口"]',3); // node_2 整值
    await click('#flow-output-bindings > button');
    await run("{const s=document.querySelector('#flow-output-bindings select[aria-label=\"来源端口\"]');s.value=[...s.options].find(o=>o.text==='node_1（完整值）').value;s.dispatchEvent(new Event('change'))}");
    const valid = await run('flowEditor.validate()'); assert.equal(valid.data.valid,true,JSON.stringify(valid));
    await click('#draft-save'); await wait("document.querySelector('#draft-result').textContent.includes('草稿已保存')");
    const id = await run("document.querySelector('#draft-select').value");
    await click('#draft-new'); assert.equal(await run("document.querySelectorAll('#flow-nodes fieldset').length"),0);
    await run(`document.querySelector('#draft-select').value=${JSON.stringify(id)};document.querySelector('#draft-select').dispatchEvent(new Event('change'))`);
    await wait("document.querySelectorAll('#flow-nodes fieldset').length===2");
    assert.equal((await run('flowEditor.validate()')).data.valid,true);
    await click('#flow-nodes fieldset:first-child > button:nth-of-type(3)');
    assert.equal((await run('flowEditor.validate()')).data.valid,false);
    await click('#draft-save'); await wait("document.querySelector('#draft-result').textContent.includes('草稿已保存')");
    console.log('PASS I8-T01: real Electron two blocks, incompatible wiring, explicit converter, prior output, reorder/delete and incomplete draft');
  } finally { await backend.stop();window.destroy();clearTimeout(watchdog);app.quit(); }
}).catch(error=>{console.error(error);app.exit(1)});

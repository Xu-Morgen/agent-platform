// 轻量桥接验收：真实注册函数 + preload，使用本地替身传输，不启动 Electron。
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const Module = require('node:module');
const handlers = new Map();
const pageURL = pathToFileURL(path.resolve(__dirname, '../renderer/index.html')).href;
const frame = {url: pageURL};
const event = {senderFrame: frame, sender: {mainFrame: frame}};
let api, request;
const electron = {
  ipcMain: {removeHandler: name => handlers.delete(name), handle: (name, fn) => handlers.set(name, fn)},
  ipcRenderer: {invoke: (name, ...args) => handlers.get(name)(event, ...args)},
  contextBridge: {exposeInMainWorld: (_, value) => {api = value;}},
};
const original = Module._load;
Module._load = function(name, ...args) { return name === 'electron' ? electron : original.call(this, name, ...args); };
const {registerConfigurationBridge} = require('../main/ipc.cjs');
Module._load = original;
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname, '../preload/index.cjs'), 'utf8'), {require: () => electron});
global.fetch = async (url, options) => { request = {url, ...options}; return {ok: true, json: async () => ({valid: true, issues: []})}; };
registerConfigurationBridge({address: 'http://local'});
(async () => {
  const calls = [
    ['loadResource', [{kind:'block',path:'sample.py'}], 'POST', '/catalog/load'],
    ['listResources', [], 'GET', '/catalog'],
    ['getResource', ['a:b'], 'GET', '/catalog/a%3Ab'],
    ['validateFlowPorts', [{}], 'POST', '/flows/validate-ports'],
    ['validateFlowNode', [{}], 'POST', '/flows/validate-node'],
    ['createDraft', [{content:{}}], 'POST', '/drafts'],
    ['listDrafts', [], 'GET', '/drafts'],
    ['getDraft', ['draft_1'], 'GET', '/drafts/draft_1'],
    ['updateDraft', ['draft_1',{content:{name:'draft'}}], 'PUT', '/drafts/draft_1'],
    ['validateDraft', ['draft_1'], 'POST', '/drafts/draft_1/validate'],
    ['validateFlow', [{content:{}}], 'POST', '/flows/validate'],
  ];
  for (const [name, args, method, route] of calls) {
    assert.equal((await api[name](...args)).ok, true);
    assert.equal(request.url, 'http://local/api/v1' + route);
    assert.equal(request.method, method);
    const body = args.find(value => typeof value === 'object');
    if (body) assert.deepEqual(JSON.parse(request.body), body);
  }
  assert.equal((await handlers.get('platform:validateFlow')({senderFrame:{url:'https://untrusted'},sender:{mainFrame:frame}}, {})).ok, false);
  console.log('flow bridge: OK (11 preload/IPC routes and sender boundary)');
})().catch(error => { console.error(error); process.exitCode = 1; });

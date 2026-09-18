const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function setup() {
  const listeners = new Map();
  const document = {activeElement: null, addEventListener(type, handler) {
    const handlers = listeners.get(type) || [];
    handlers.push(handler);listeners.set(type, handlers);
  }};
  const context = vm.createContext({document, setTimeout, clearTimeout});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../desktop/renderer/input-events.js'), 'utf8'), context);
  const api = vm.runInContext('inputEvents', context);
  function field() {
    const handlers = new Map();
    return {value: '', matches: () => true, addEventListener(type, handler) {
      const items = handlers.get(type) || [];
      items.push(handler);handlers.set(type, items);
    }, emit(type, extra = {}) {
      const event = {target: this, ...extra};
      for (const handler of listeners.get(type) || []) handler(event);
      for (const handler of handlers.get(type) || []) handler(event);
    }};
  }
  return {api, document, field, listeners};
}
const tick = () => new Promise(resolve => setTimeout(resolve, 10));

test('拼音期间不更新业务，确认汉字只更新一次，普通输入继续生效', () => {
  const {api, field, listeners} = setup();
  const input = field(), values = [];
  api.onInput(input, () => values.push(input.value));
  input.emit('compositionstart');
  input.value = 'zhong';input.emit('input', {isComposing: true});
  assert.deepEqual(values, []);
  input.value = '中';input.emit('compositionend');input.emit('input');
  assert.deepEqual(values, ['中']);
  input.value = '中文';input.emit('input');
  assert.deepEqual(values, ['中', '中文']);
  assert.equal(listeners.has('keydown'), false);
});

test('编辑中的节点保留到失焦再重绘，异步刷新不能覆盖输入', async () => {
  const {api, document, field} = setup();
  const input = field(), root = {contains: element => element === input};
  document.activeElement = input;input.value = '正在编辑';
  api.setValue(input, '旧值');assert.equal(input.value, '正在编辑');
  let renders = 0;
  const render = () => { if (!api.defer('render', render, root)) renders++; };
  render();assert.equal(renders, 0);
  document.activeElement = null;input.emit('focusout');await tick();
  assert.equal(renders, 1);
});

test('输入法确认回车不提交表单，确认结束后允许提交', async () => {
  const {field} = setup();const input = field();let prevented = 0;
  const submit = () => input.emit('submit', {
    preventDefault: () => prevented++, stopImmediatePropagation() {},
  });
  input.emit('compositionstart');submit();
  input.emit('compositionend');submit();
  assert.equal(prevented, 2);
  await tick();submit();assert.equal(prevented, 2);
});

test('失焦取消拼音时不会永久阻塞刷新和提交', async () => {
  const {api, field} = setup();const input = field();let renders = 0;
  input.emit('compositionstart');
  api.defer('render', () => renders++);
  input.emit('focusout');await tick();
  assert.equal(renders, 1);
  input.emit('submit', {preventDefault() {assert.fail('提交被阻塞');}, stopImmediatePropagation() {}});
});

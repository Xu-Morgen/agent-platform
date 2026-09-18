// 保留浏览器的输入法按键处理；业务更新只读取已确认的文本。
const inputEvents = (() => {
  const composing = new Set();
  const pending = new Map();
  let settling = false, flushTimer;
  const editable = element => element?.matches?.('input, textarea, [contenteditable="true"]');
  function flushLater() {
    clearTimeout(flushTimer);
    flushTimer = setTimeout(() => {
      settling = false;
      if (composing.size) return;
      const actions = [...pending.values()];pending.clear();
      for (const action of actions) action();
    }, 0);
  }
  document.addEventListener('compositionstart', event => {
    if (editable(event.target)) composing.add(event.target);
  }, true);
  document.addEventListener('compositionend', event => {
    composing.delete(event.target);settling = true;flushLater();
  }, true);
  document.addEventListener('focusout', event => {
    composing.delete(event.target);
    flushLater();
  }, true);
  document.addEventListener('submit', event => {
    if (composing.size || settling) {
      event.preventDefault();event.stopImmediatePropagation();
    }
  }, true);
  function onInput(element, update) {
    let lastValue = element.value;
    const commit = event => {
      if (event.isComposing || composing.has(element) || element.value === lastValue) return;
      lastValue = element.value;update(event);
    };
    element.addEventListener('compositionstart', () => { lastValue = element.value; });
    element.addEventListener('input', commit);
    element.addEventListener('compositionend', commit);
  }
  function defer(key, action, editingRoot) {
    const focused = document.activeElement;
    if (composing.size || settling || (editingRoot?.contains(focused) && editable(focused))) {
      pending.set(key, action);return true;
    }
    return false;
  }
  function setValue(element, value) {
    const text = String(value ?? '');
    if (element !== document.activeElement && !composing.has(element) && element.value !== text) element.value = text;
  }
  return {onInput, defer, setValue};
})();

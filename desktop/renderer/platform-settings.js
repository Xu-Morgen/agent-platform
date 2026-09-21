// 保存值只用于下次启动；当前消费者数由后端返回，页面不推断即时生效。
(() => {
  const input = document.querySelector('#settings-concurrency');
  const save = document.querySelector('#settings-save');
  const refresh = document.querySelector('#platform-settings-refresh');
  const result = document.querySelector('#platform-settings-result');
  let loaded = false;
  let busy = false;
  let persistent = false;

  function controls() {
    input.disabled = busy || !loaded || !persistent;
    save.disabled = input.disabled;
    refresh.disabled = busy;
  }
  function show(value) {
    loaded = true;
    persistent = value.persistent;
    input.value = value.runConcurrency;
    document.querySelector('#settings-active').textContent = value.activeRunConcurrency;
    document.querySelector('#settings-saved').textContent = value.runConcurrency;
    document.querySelector('#settings-restart').hidden = !value.restartRequired || !persistent;
    document.querySelector('#settings-memory').hidden = persistent;
  }
  async function load() {
    if (busy) return;
    busy = true;
    controls();
    result.textContent = '正在读取平台设置…';
    try {
      const response = await window.agentPlatform.platformSettings();
      if (!response.ok) throw new Error(response.error.message);
      show(response.data);
      result.textContent = '';
    } catch (error) {
      loaded = false;
      result.textContent = `读取失败：${error.message}`;
    } finally {
      busy = false;
      controls();
    }
  }
  document.querySelector('#platform-settings-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !loaded || !persistent || !input.reportValidity()) return;
    const runConcurrency = input.valueAsNumber;
    busy = true;
    controls();
    result.textContent = '正在保存…';
    try {
      const response = await window.agentPlatform.savePlatformSettings({ runConcurrency });
      if (!response.ok) throw new Error(response.error.message);
      show(response.data);
      result.textContent = response.data.restartRequired
        ? '已保存，重启应用后生效。当前并发数保持不变。'
        : '已保存，与当前生效值一致，无需重启。';
    } catch (error) {
      result.textContent = `保存失败：${error.message}`;
    } finally {
      busy = false;
      controls();
    }
  });
  refresh.addEventListener('click', load);
  window.platformSettings = { refresh: load };
})();

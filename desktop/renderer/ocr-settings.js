(() => {
  const root = document.querySelector('#ocr-settings');
  const status = document.querySelector('#ocr-status');
  const details = document.querySelector('#ocr-details');
  const select = document.querySelector('#ocr-model');
  let busy = false;
  let models = [];
  const api = window.agentPlatform;
  async function checked(promise) {
    const response = await promise;
    if (!response.ok) throw new Error(response.error.message);
    return response.data;
  }
  function show() {
    const model = models.find(item => item.modelId === select.value);
    details.textContent = model ? `${model.manifest.name} · ${model.status === 'ready' ? '就绪' : '不可用'}\n${model.modelId}\n${(model.sizeBytes / 1048576).toFixed(1)} MiB · ${model.manifest.adapter}\n来源：${model.manifest.source}\n修订：${model.manifest.revision}${model.error ? `\n${model.error}` : ''}` : '';
  }
  async function load() {
    const [items, choice] = await Promise.all([checked(api.ocrModels()), checked(api.ocrSelection())]);
    models = items;
    select.replaceChildren(new Option('未选择', ''));
    for (const model of models) {
      const option = new Option(`${model.manifest.name} · ${model.modelId.slice(4, 16)} · ${model.status === 'ready' ? '就绪' : '不可用'}`, model.modelId);
      select.add(option);
    }
    select.value = choice.modelId || '';
    show();
  }
  async function action(operation) {
    if (busy) return;
    busy = true;
    root.querySelectorAll('button,input,select').forEach(item => { item.disabled = true; });
    try { await operation(); } catch (error) { status.textContent = `操作失败：${error.message}`; }
    finally {
      busy = false;
      root.querySelectorAll('button,input,select').forEach(item => { item.disabled = false; });
    }
  }
  async function job(promise) {
    let value = await checked(promise);
    while (value.status === 'running') {
      status.textContent = value.progress;
      await new Promise(resolve => setTimeout(resolve, 500));
      value = await checked(api.ocrJob(value.jobId));
    }
    await load();
    if (value.status === 'failed') throw new Error(value.error);
    if (value.diagnostic) {
      const d = value.diagnostic;
      status.textContent = `验证通过：${d.recognizedText}；加载 ${d.loadSeconds.toFixed(3)} 秒，推理 ${d.inferenceSeconds.toFixed(3)} 秒，进程峰值 ${(d.peakMemoryBytes / 1048576).toFixed(1)} MiB。`;
    } else status.textContent = 'OCR 模型组合已导入并通过运行检查，请选择并保存默认模型。';
  }
  document.querySelector('#ocr-refresh').onclick = () => action(async () => { await load(); status.textContent = models.length ? '模型列表已刷新。' : '暂无模型，请导入含 ocr.json 的本地模型目录。'; });
  document.querySelector('#ocr-browse').onclick = () => action(async () => {
    const value = await checked(api.selectResourcePath('ocr'));
    if (value.path) document.querySelector('#ocr-directory').value = value.path;
  });
  document.querySelector('#ocr-import').onclick = () => action(() => job(api.importOCR({ directory: document.querySelector('#ocr-directory').value.trim() })));
  document.querySelector('#ocr-check').onclick = () => action(async () => {
    if (!select.value) throw new Error('请先选择模型');
    await job(api.checkOCR(select.value));
  });
  document.querySelector('#ocr-select').onclick = () => action(async () => {
    await checked(api.selectOCR({ modelId: select.value || null }));
    status.textContent = '默认选择已保存，对新任务立即生效。';
  });
  select.onchange = show;
  window.ocrSettings = { refresh: () => action(load) };
})();

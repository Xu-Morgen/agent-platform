// 表单持有连接草稿；地址和凭据变化使已获取的模型列表失效。
const connectionEditor = (() => {
  const target = document.querySelector('#connection-tool-select');
  const base = document.querySelector('#connection-base-url');
  const credential = document.querySelector('#environment-credential');
  const models = document.querySelector('#connection-model-select');
  const result = document.querySelector('#connection-tool-result');
  const getButton = document.querySelector('#connection-models');
  const testButton = document.querySelector('#connection-test');
  let drafts = [];
  let generation = 0;
  let busy = false;
  const current = () => drafts[Number(target.value)];
  function buttons() {
    getButton.disabled = busy || !base.value.trim();
    testButton.disabled = busy || !models.value;
  }
  function invalidate() {
    generation++;
    models.replaceChildren(new Option('请先获取模型', ''));
    models.disabled = true;
    result.textContent = '';
    buttons();
  }
  function show() {
    invalidate();
    const value = current();
    base.value = value.baseUrl;
    credential.value = value.credential || '';
    if (value.model) {
      models.replaceChildren(new Option(value.model + '（当前配置）', value.model));
      models.disabled = false;
    }
    buttons();
  }
  function load(connections) {
    drafts = structuredClone(connections || []);
    if (!drafts.some(c => c.kind === 'model')) {
      let id = 'model';
      for (let suffix = 2; drafts.some(c => c.connectionId === id); suffix++) id = `model${suffix}`;
      drafts.push({connectionId: id, kind: 'model', modelAdapter: 'openai-chat', baseUrl: '',
        outputTokenParameter: 'max_completion_tokens', jsonMode: true, timeoutSeconds: 180});
    }
    target.replaceChildren();
    drafts.forEach((c, index) => { if (c.kind === 'model') target.add(new Option(c.connectionId, String(index))); });
    document.querySelector('#connection-target-label').hidden = target.options.length < 2;
    show();
  }
  function read() {
    if (!base.reportValidity() || !base.value.trim()) throw new Error('请填写有效的 Base URL');
    const connection = {...current()};
    if (connection.credential) delete connection.credentialRef;
    else delete connection.credential;
    return connection;
  }
  base.addEventListener('input', () => {
    const value = current();
    value.baseUrl = base.value.trim();
    delete value.model;
    // 地址变化后不能将旧地址的已存凭据发送给新地址。
    delete value.credentialRef;
    try {
      const url = new URL(value.baseUrl);
      if (url.hostname === 'api.deepseek.com') {
        value.modelAdapter = 'openai-chat';
        value.outputTokenParameter = 'max_tokens';
      } else if (url.port === '11434') value.modelAdapter = 'ollama-chat';
      else {
        value.modelAdapter = 'openai-chat';
        value.outputTokenParameter = 'max_completion_tokens';
      }
    } catch { /* URL 输入过程中由表单校验提示。 */ }
    invalidate();
  });
  credential.addEventListener('input', () => {
    current().credential = credential.value;
    delete current().model;
    invalidate();
  });
  target.addEventListener('change', show);
  models.addEventListener('change', () => {
    generation++;
    current().model = models.value;
    result.textContent = '';
    buttons();
  });
  async function diagnose(action) {
    if (busy) return;
    if (action === 'models') { delete current().model; invalidate(); }
    const version = ++generation;
    busy = true;
    buttons();
    result.textContent = action === 'models' ? '正在获取模型…' : '正在测试连接…';
    try {
      const connection = read();
      if (action === 'test' && !connection.model) throw new Error('请先获取并选择模型');
      const response = action === 'models'
        ? await window.agentPlatform.connectionModels({connection})
        : await window.agentPlatform.testConnection({connection, maxOutputTokens: 256});
      if (version !== generation) return;
      if (!response.ok) {
        const error = response.error;
        const status = error.details?.httpStatus;
        const hint = {401: '请检查 API Key。', 402: '请检查账户余额。', 403: '请检查访问权限。',
          404: '请检查 Base URL 是否支持模型列表及推理接口。', 429: '请求受限，请稍后重试。'}[status] || '';
        result.textContent = `${error.message}${status ? `（HTTP ${status}）` : ''} ${hint}`;
        return;
      }
      if (action === 'models') {
        models.replaceChildren(new Option('请选择模型', ''));
        for (const model of response.data.models) models.add(new Option(model, model));
        models.disabled = response.data.models.length === 0;
        result.textContent = response.data.models.length ? `获取到 ${response.data.models.length} 个模型，请从下拉列表选择。` : '未获取到可用模型，请检查地址、凭据或服务商配置。';
      } else result.textContent = `测试通过，耗时 ${response.data.elapsedMs} ms；输入 token ${response.data.usage.inputTokens ?? '未知'}，输出 token ${response.data.usage.outputTokens ?? '未知'}。`;
    } catch (error) {
      if (version === generation) result.textContent = ['请填写有效的 Base URL', '请先获取并选择模型'].includes(error.message)
        ? error.message : '连接请求失败，请检查后端状态。';
    } finally { busy = false; buttons(); }
  }
  getButton.addEventListener('click', () => diagnose('models'));
  testButton.addEventListener('click', () => diagnose('test'));
  return {load, connections() {
    read();
    if (drafts.some(c => c.kind === 'model' && !c.model)) throw new Error('请先获取模型，并从下拉列表选择后保存');
    return drafts.map(c => {
      const value = {...c};
      if (value.credential) delete value.credentialRef;
      else delete value.credential;
      return value;
    });
  }};
})();

// 环境保存连接；模型供包使用，API 供通用块使用。
const connectionEditor = (() => {
  const $ = id => document.getElementById(id);
  const target = $('connection-tool-select'), kind = $('connection-kind');
  const base = $('connection-base-url'), timeout = $('connection-timeout');
  const credential = $('environment-credential'), models = $('connection-model-select');
  const result = $('connection-tool-result'), getButton = $('connection-models'), testButton = $('connection-test');
  let drafts = [], generation = 0, busy = false;
  const current = () => drafts[Number(target.value)];
  const modelConnection = () => current()?.kind === 'model';
  function renderConnections() {
    const list = $('connection-list');
    list.replaceChildren();
    $('connection-count').textContent = drafts.length;
    drafts.forEach((connection, index) => {
      const item = document.createElement('button');
      item.type = 'button'; item.className = 'connection-item'; item.dataset.kind = connection.kind;
      item.setAttribute('aria-pressed', String(index === Number(target.value)));
      const icon = document.createElement('span'); icon.className = 'connection-icon';
      icon.textContent = connection.kind === 'model' ? '✦' : '↗'; icon.setAttribute('aria-hidden', 'true');
      const title = document.createElement('strong'); title.textContent = connection.connectionId;
      const detail = document.createElement('small');
      detail.textContent = (connection.kind === 'model' ? '模型 · ' : 'API · ') + (connection.baseUrl || '待填写地址');
      item.append(icon, title, detail);
      item.onclick = () => { target.value = String(index); show(); $('connection-list').children[index].focus({preventScroll:true}); };
      list.append(item);
    });
  }
  function buttons() {
    getButton.disabled = busy || !modelConnection() || !base.value.trim();
    testButton.disabled = busy || !modelConnection() || !models.value;
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
    renderConnections();
    $('connection-detail-title').textContent = value.connectionId;
    $('connection-detail-kind').textContent = modelConnection() ? '模型连接 · 供业务包使用' : 'API 连接 · 供通用块使用';
    $('base-url-hint').textContent = modelConnection() ? '填写模型服务的 Base URL，然后获取可用模型。' : '填写外部服务的 Base URL；具体请求路径在通用块节点中配置。';
    base.placeholder = modelConnection() ? 'https://api.deepseek.com' : 'https://api.example.com';
    credential.type = 'password';
    $('credential-toggle').textContent = '显示';
    $('credential-toggle').setAttribute('aria-label', '显示 API Key');
    $('credential-toggle').setAttribute('aria-pressed', 'false');
    kind.value = value.kind;
    base.value = value.baseUrl;
    timeout.value = value.timeoutSeconds;
    credential.value = value.credential || '';
    $('model-connection-fields').hidden = !modelConnection();
    $('api-connection-hint').hidden = modelConnection();
    models.required = modelConnection();
    if (modelConnection() && value.model) {
      models.replaceChildren(new Option(value.model + '（当前配置）', value.model));
      models.disabled = false;
    }
    buttons();
  }
  function refreshTarget(selected = 0) {
    target.replaceChildren();
    drafts.forEach((c, index) => target.add(new Option(`${c.connectionId} · ${c.kind === 'model' ? '模型' : 'API'}`, String(index))));
    target.value = String(selected);
    $('connection-remove').disabled = drafts.length === 1;
    show();
  }
  function create(connectionKind) {
    let id = connectionKind;
    for (let suffix = 2; drafts.some(c => c.connectionId === id); suffix++) id = `${connectionKind}${suffix}`;
    return {connectionId: id, kind: connectionKind, baseUrl: '', timeoutSeconds: connectionKind === 'model' ? 180 : 60,
      ...(connectionKind === 'model' ? {outputTokenParameter:'max_completion_tokens', jsonMode:true} : {})};
  }
  function load(connections) {
    drafts = structuredClone(connections || []);
    if (!drafts.length) drafts.push(create('model'));
    refreshTarget();
  }
  function read() {
    if (!base.reportValidity() || !base.value.trim()) throw new Error('请填写有效的 Base URL');
    if (!timeout.reportValidity()) throw new Error('请填写有效的超时时间');
    const connection = {...current()};
    if (connection.credential) delete connection.credentialRef;
    else delete connection.credential;
    return connection;
  }
  for (const connectionKind of ['model', 'api']) $('connection-add-' + connectionKind).onclick = () => {
    drafts.push(create(connectionKind)); refreshTarget(drafts.length - 1);
  };
  $('connection-remove').onclick = () => {
    if (drafts.length > 1) { drafts.splice(Number(target.value), 1); refreshTarget(); }
  };
  kind.onchange = () => {
    const value = current();
    drafts[Number(target.value)] = {connectionId:value.connectionId, kind:kind.value,
      baseUrl:value.baseUrl, timeoutSeconds:value.timeoutSeconds,
      ...(kind.value === 'model' ? {outputTokenParameter:'max_completion_tokens', jsonMode:true} : {})};
    refreshTarget(Number(target.value));
  };
  inputEvents.onInput(base, () => {
    const value = current();
    value.baseUrl = base.value.trim();
    delete value.model;
    delete value.credentialRef;
    if (modelConnection()) {
      try { value.outputTokenParameter = new URL(value.baseUrl).hostname === 'api.deepseek.com' ? 'max_tokens' : 'max_completion_tokens'; }
      catch { /* 表单负责提示尚未完成的 URL。 */ }
    }
    invalidate();
    renderConnections();
  });
  timeout.addEventListener('input', () => { current().timeoutSeconds = Number(timeout.value); generation++; result.textContent = ''; });
  inputEvents.onInput(credential, () => {
    current().credential = credential.value;
    delete current().model;
    invalidate();
  });
  target.addEventListener('change', show);
  $('credential-toggle').onclick = () => {
    const visible = credential.type === 'password';
    credential.type = visible ? 'text' : 'password';
    $('credential-toggle').textContent = visible ? '隐藏' : '显示';
    $('credential-toggle').setAttribute('aria-label', visible ? '隐藏 API Key' : '显示 API Key');
    $('credential-toggle').setAttribute('aria-pressed', String(visible));
  };
  models.addEventListener('change', () => {
    generation++; current().model = models.value; result.textContent = ''; buttons();
  });
  async function diagnose(action) {
    if (busy || !modelConnection()) return;
    if (action === 'models') { delete current().model; invalidate(); }
    const version = ++generation;
    busy = true; buttons();
    result.textContent = action === 'models' ? '正在获取模型…' : '正在测试连接…';
    try {
      const connection = read();
      if (action === 'test' && !connection.model) throw new Error('请先获取并选择模型');
      const response = action === 'models'
        ? await window.agentPlatform.connectionModels({connection})
        : await window.agentPlatform.testConnection({connection, maxOutputTokens:256});
      if (version !== generation) return;
      if (!response.ok) {
        const error = response.error, status = error.details?.httpStatus;
        const hint = {401:'请检查 API Key。',402:'请检查账户余额。',403:'请检查访问权限。',
          404:'请检查 Base URL 是否支持模型列表及推理接口。',429:'请求受限，请稍后重试。'}[status] || '';
        result.textContent = `${error.message}${status ? `（HTTP ${status}）` : ''} ${hint}`;
        return;
      }
      if (action === 'models') {
        models.replaceChildren(new Option('请选择模型', ''));
        for (const model of response.data.models) models.add(new Option(model, model));
        models.disabled = response.data.models.length === 0;
        result.textContent = response.data.models.length ? `获取到 ${response.data.models.length} 个模型，请从下拉列表选择。` : '未获取到可用模型，请检查连接配置。';
      } else result.textContent = `测试通过，耗时 ${response.data.elapsedMs} ms；输入 token ${response.data.usage.inputTokens ?? '未知'}，输出 token ${response.data.usage.outputTokens ?? '未知'}。`;
    } catch (error) {
      if (version === generation) result.textContent = ['请填写有效的 Base URL','请填写有效的超时时间','请先获取并选择模型'].includes(error.message)
        ? error.message : '连接请求失败，请检查后端状态。';
    } finally { busy = false; buttons(); }
  }
  getButton.addEventListener('click', () => diagnose('models'));
  testButton.addEventListener('click', () => diagnose('test'));
  return {load, connections() {
    read();
    if (drafts.some(c => c.kind === 'model' && !c.model)) throw new Error('请先获取模型，并从下拉列表选择后保存');
    if (drafts.some(c => !c.baseUrl.trim())) throw new Error('请填写所有连接的 Base URL，或移除未使用的连接');
    return drafts.map(c => {
      const value = {...c};
      if (value.credential) delete value.credentialRef;
      else delete value.credential;
      return value;
    });
  }};
})();

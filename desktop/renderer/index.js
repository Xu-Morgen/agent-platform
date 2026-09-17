const status = document.querySelector('#status');
const healthButton = document.querySelector('#health');

async function refreshHealth() {
  healthButton.disabled = true;
  status.textContent = '后端启动中…';
  try {
    const result = await window.agentPlatform.health();
    if (!result.ok) {
      status.textContent = `${result.error.code === 'STARTUP_ERROR' ? '启动失败' : '健康检查失败'}：${result.error.message}`;
      return;
    }
    backendAddress = result.address;
    status.textContent = `后端已就绪：${result.address}`;
    healthButton.disabled = false;
    await refreshEnvironments();
    await refreshServices();
  } catch {
    status.textContent = '桌面请求桥不可用';
  }
}
healthButton.addEventListener('click', refreshHealth);
refreshHealth();

const environmentSelect = document.querySelector('#environment-select');
const environmentResult = document.querySelector('#environment-result');
let environments = [];
function errorText(error) {
  return `${error.message}${error.fieldPath ? '（' + error.fieldPath.join('.') + '）' : ''}`;
}
function editEnvironment() {
  const value = environments.find(item => item.environmentId === environmentSelect.value);
  document.querySelector('#environment-name').value = value?.name || '';
  connectionEditor.load(value?.connections);
  const occupied = value?.activeRunIds || [];
  document.querySelector('#environment-form button[type=submit]').disabled = occupied.length > 0;
  environmentResult.textContent = occupied.length ? `环境被任务占用：${occupied.join('、')}` : value ? `环境 ${value.environmentId} · revision ${value.revision}；凭据 ********（仅显示引用）` : '';
}
async function refreshEnvironments(selected = environmentSelect.value) {
  const result = await window.agentPlatform.listEnvironments();
  if (!result.ok) { environmentResult.textContent = errorText(result.error); return; }
  environments = result.data;
  const choices = document.querySelector('#service-environment');
  choices.replaceChildren(new Option('无环境', ''));
  for (const item of environments) choices.add(new Option(item.name, item.environmentId));
  environmentSelect.replaceChildren(new Option('新建环境', ''));
  for (const item of environments) environmentSelect.add(new Option(item.name, item.environmentId));
  environmentSelect.value = selected;
  editEnvironment();
}
environmentSelect.addEventListener('change', editEnvironment);
document.querySelector('#environment-refresh').addEventListener('click', () => refreshEnvironments());
document.querySelector('#environment-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.submitter;
  if (button) button.disabled = true;
  try {
    const connections = connectionEditor.connections();
    const body = { name: document.querySelector('#environment-name').value, connections };
    const result = environmentSelect.value
      ? await window.agentPlatform.updateEnvironment(environmentSelect.value, body)
      : await window.agentPlatform.createEnvironment(body);
    if (!result.ok) { environmentResult.textContent = errorText(result.error); return; }
    await refreshEnvironments(result.data.environmentId);
  } catch (error) {
    environmentResult.textContent = error instanceof SyntaxError ? 'connections：JSON 格式无效' : error.message;
  } finally { if (button) button.disabled = false; }
});
editEnvironment();

const serviceSelect = document.querySelector('#service-select');
const taskServiceSelect = document.querySelector('#task-service-select');
const definitionSelect = document.querySelector('#definition-select');
const serviceResult = document.querySelector('#service-result');
const definitionEditor = document.querySelector('#service-definition');
const definitions = new Map();
let services = [];
let backendAddress = '';
function showDefinition(value) {
  definitionEditor.value = JSON.stringify(value.definition, null, 2);
  showBudgetFields(value.definition);
  document.querySelector('#service-schemas').textContent = JSON.stringify(value.schemas, null, 2);
  document.querySelector('#budget-defaults').textContent = `全局预算默认值（各包绑定上限之和，可在下方修改）：${JSON.stringify(value.budgetDefaults || value.definition.budget)}`;
}
function rememberDefinition(value) {
  if (!definitions.has(value.loadId)) definitionSelect.add(new Option(value.id || value.definition.definitionId, value.loadId));
  definitions.set(value.loadId, value);
  definitionSelect.value = value.loadId;
  showDefinition(value);
}
definitionSelect.addEventListener('change', () => showDefinition(definitions.get(definitionSelect.value)));
document.querySelector('#load-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.submitter;
  if (button) button.disabled = true;
  try {
    const result = await window.agentPlatform.loadDefinition({ kind: document.querySelector('#load-kind').value, path: document.querySelector('#load-path').value });
    document.querySelector('#load-result').textContent = result.ok ? `已加载 ${result.data.id}` : errorText(result.error);
    if (result.ok) {
      const item = document.createElement('li');
      item.textContent = `${result.data.kind} · ${result.data.id} ${result.data.version || ''}`;
      document.querySelector('#loaded-artifacts').append(item);
      if (result.data.kind === 'instance') rememberDefinition(result.data);
    }
  } finally { if (button) button.disabled = false; }
});
async function editService() {
  serviceResult.textContent = '';
  const selected = services.find(value => value.serviceId === serviceSelect.value);
  document.querySelector('#service-name').value = selected?.name || '';
  document.querySelector('#service-current').textContent = selected
    ? `稳定服务：${selected.serviceId} · Schema 地址：${backendAddress}/api/v1/services/${selected.serviceId}/schema · 当前版本 ${selected.current.version} · ${selected.activeInstanceId}` : '保存后生成稳定服务标识';
  document.querySelector('#service-history').replaceChildren();
  if (!selected) return;
  const result = await window.agentPlatform.serviceSchema(selected.serviceId);
  if (!result.ok) { serviceResult.textContent = errorText(result.error); return; }
  const value = result.data;
  rememberDefinition({ loadId: value.definitionLoadId, definition: value.definition,
    schemas: { input: value.input, output: value.output, ...value.configurationSchemas },
    budgetDefaults: value.definition.budget });
  await refreshHistory();
}
async function refreshServices(selected = serviceSelect.value) {
  const result = await window.agentPlatform.listServices();
  if (!result.ok) { serviceResult.textContent = errorText(result.error); return; }
  services = result.data;
  updateTaskServices(taskServiceSelect.value || selected);
  serviceSelect.replaceChildren(new Option('新建服务', ''));
  for (const item of services) serviceSelect.add(new Option(item.name, item.serviceId));
  serviceSelect.value = selected;
  await editService();
}
function updateTaskServices(selected = taskServiceSelect.value) {
  taskServiceSelect.replaceChildren(new Option('请选择服务', ''));
  for (const item of services) taskServiceSelect.add(new Option(`${item.name} · ${item.current.version}`, item.serviceId));
  taskServiceSelect.value = selected;
}
document.querySelector('#task-service-refresh').addEventListener('click', async () => {
  const result = await window.agentPlatform.listServices();
  if (!result.ok) { taskError.textContent = taskFailure(result.error); return; }
  services = result.data;
  updateTaskServices();
  taskError.textContent = '';
});
serviceSelect.addEventListener('change', () => {
  taskServiceSelect.value = serviceSelect.value;
  editService();
});
document.querySelector('#service-refresh').addEventListener('click', () => refreshServices());
document.querySelector('#bind-environment').addEventListener('click', () => {
  try {
    const value = JSON.parse(definitionEditor.value);
    const id = document.querySelector('#service-environment').value;
    if (id) value.environmentRefs = [...new Set([...value.environmentRefs, id])];
    definitionEditor.value = JSON.stringify(value, null, 2);
    serviceResult.textContent = '环境引用已加入；连接能力绑定请在 capabilityBindings 填写 environmentId 和 connectionId。';
  } catch { serviceResult.textContent = 'definition：请先加载有效实例 JSON'; }
});
document.querySelector('#service-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.submitter;
  if (button) button.disabled = true;
  try {
    const body = { name: document.querySelector('#service-name').value, definitionLoadId: definitionSelect.value, definition: JSON.parse(definitionEditor.value) };
    const result = serviceSelect.value ? await window.agentPlatform.saveServiceVersion(serviceSelect.value, body) : await window.agentPlatform.createService(body);
    if (!result.ok) { serviceResult.textContent = errorText(result.error); return; }
    await refreshServices(result.data.serviceId);
    serviceResult.textContent = `已保存版本 ${result.data.current.version}（${result.data.current.changeKind}），立即生效`;
  } catch { serviceResult.textContent = 'definition：JSON 格式无效或请求无法完成'; }
  finally { if (button) button.disabled = false; }
});

async function refreshHistory() {
  const result = await window.agentPlatform.serviceHistory(serviceSelect.value);
  const target = document.querySelector('#history-result');
  if (!result.ok) { target.textContent = errorText(result.error); return; }
  const list = document.querySelector('#service-history');
  list.replaceChildren();
  const current = services.find(value => value.serviceId === serviceSelect.value);
  for (const value of result.data) {
    const item = document.createElement('li');
    const text = document.createElement('span');
    text.textContent = `${value.version} · revision ${value.revision} · ${value.changeKind} · ${value.instanceId} `;
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.instanceId = value.instanceId;
    button.disabled = value.instanceId === current.activeInstanceId;
    button.textContent = button.disabled ? '当前版本' : '选用此历史版本';
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        const response = await window.agentPlatform.activateService(current.serviceId, value.instanceId);
        if (!response.ok) { target.textContent = errorText(response.error); button.disabled = false; return; }
        await refreshServices(current.serviceId);
        target.textContent = `已选用原历史实例 ${value.instanceId}，版本 ${value.version}`;
      } catch { target.textContent = '回退请求无法完成'; button.disabled = false; }
    });
    item.append(text, button);
    list.append(item);
  }
}


const taskStatus = document.querySelector('#task-status');
const taskError = document.querySelector('#task-error');
let taskPollTimer;
let taskQueryGeneration = 0;
function taskFailure(error) {
  return `${error.code} · ${error.stage}：${errorText(error)}`;
}
function schemaExample(schema, root = schema) {
  if (schema.$ref) return schemaExample(root.$defs?.[schema.$ref.split('/').pop()] || {}, root);
  if ('default' in schema) return schema.default;
  if (schema.examples?.length) return schema.examples[0];
  if (schema.enum?.length) return schema.enum[0];
  if (schema.type === 'object') return Object.fromEntries((schema.required || []).map(key => [key, schemaExample(schema.properties[key], root)]));
  if (schema.type === 'array') return [];
  if (schema.type === 'boolean') return false;
  if (schema.type === 'integer' || schema.type === 'number') return schema.minimum ?? 0;
  return '合成输入';
}
document.querySelector('#task-example').addEventListener('click', async () => {
  if (!taskServiceSelect.value) { taskError.textContent = '请先选择已保存的服务'; return; }
  const response = await window.agentPlatform.serviceSchema(taskServiceSelect.value);
  if (!response.ok) { taskError.textContent = taskFailure(response.error); return; }
  document.querySelector('#task-input').value = JSON.stringify(response.data.examples[0] || schemaExample(response.data.input), null, 2);
  taskError.textContent = '样例可编辑，提交时由服务契约校验。';
});
async function pollTask(runId, generation) {
  const response = await window.agentPlatform.getRun(runId);
  if (generation !== taskQueryGeneration) return;
  if (!response.ok) { taskError.textContent = taskFailure(response.error); taskStatus.textContent = '查询失败'; return; }
  const run = response.data;
  taskStatus.textContent = `${run.status} · ${run.runId} · 实际版本 ${run.version} · ${run.instanceId}`;
  taskError.textContent = run.error ? taskFailure(run.error) : '';
  document.querySelector('#task-cancel').disabled = !['queued', 'running'].includes(run.status) || run.cancelRequested;
  document.querySelector('#task-cancel-status').textContent = run.cancelRequested
    ? (run.status === 'failed' ? '取消等待失败，请查看原始错误' : run.status === 'cancelled' ? '已取消'
      : run.cancelPhase === 'waiting_transport' ? '取消已受理，等待当前模型传输结束' : '取消已受理，等待停止执行') : '';
  showUsage(run.usage);
  const steps = document.querySelector('#task-steps');
  steps.replaceChildren();
  for (const step of run.steps) {
    const item = document.createElement('li');
    item.textContent = `${step.stepId} · ${step.status} · 尝试 ${step.attempt}${step.packageBindingId ? ' · 包 ' + step.packageBindingId : ''}${step.error ? ' · ' + taskFailure(step.error) : ''}`;
    if (Object.keys(step.usage).length) item.textContent += ` · 用量 ${JSON.stringify(step.usage)}`;
    steps.append(item);
  }
  if (run.status === 'completed') {
    const result = await window.agentPlatform.getRunResult(runId);
    if (generation !== taskQueryGeneration) return;
    if (result.ok) document.querySelector('#task-result').textContent = JSON.stringify(result.data.result, null, 2);
    else taskError.textContent = taskFailure(result.error);
  } else if (run.status === 'queued' || run.status === 'running') {
    taskPollTimer = setTimeout(() => pollTask(runId, generation), 500);
  }
}
function watchTask(runId) {
  clearTimeout(taskPollTimer);
  const generation = ++taskQueryGeneration;
  document.querySelector('#task-run-id').value = runId;
  document.querySelector('#task-result').textContent = '';
  document.querySelector('#task-steps').replaceChildren();
  taskError.textContent = '';
  document.querySelector('#task-usage').textContent = '';
  document.querySelector('#task-cancel').disabled = true;
  document.querySelector('#task-cancel-status').textContent = '';
  taskStatus.textContent = '查询中…';
  return pollTask(runId, generation);
}
document.querySelector('#task-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.querySelector('#task-submit');
  button.disabled = true;
  try {
    const selected = services.find(value => value.serviceId === taskServiceSelect.value);
    if (!selected) { taskError.textContent = '请先选择已保存的服务'; return; }
    const input = JSON.parse(document.querySelector('#task-input').value);
    const response = await window.agentPlatform.submitRun({ serviceId: selected.serviceId, expectedInstanceId: selected.activeInstanceId, input });
    if (!response.ok) { taskError.textContent = taskFailure(response.error); return; }
    await watchTask(response.data.runId);
  } catch (error) {
    taskError.textContent = error instanceof SyntaxError ? '任务输入：JSON 格式无效' : '任务请求失败';
  } finally { button.disabled = false; }
});
document.querySelector('#task-query-form').addEventListener('submit', event => {
  event.preventDefault();
  watchTask(document.querySelector('#task-run-id').value.trim());
});
window.addEventListener('beforeunload', () => { clearTimeout(taskPollTimer); taskQueryGeneration++; });

function showBudgetFields(definition) {
  const target = document.querySelector('#budget-fields');
  target.replaceChildren();
  const budgets = [{scope: 'global', name: '任务总量', values: definition.budget}];
  for (const binding of definition.packageBindings) {
    const scope = 'packages.' + binding.bindingId;
    const values = Object.assign({}, ...definition.configRefs.filter(c => c.scope === scope).map(c => c.values));
    budgets.push({scope, name: '包 ' + binding.bindingId, values});
  }
  for (const budget of budgets) {
    for (const key of ['loopLimit', 'tokenLimit', ...(budget.scope === 'global' ? ['strictTokenLimit'] : [])]) {
      const label = document.createElement('label');
      label.textContent = `${budget.name} · ${{loopLimit:'loop 上限',tokenLimit:'token 上限',strictTokenLimit:'严格 token 限额'}[key]} `;
      const input = document.createElement('input');
      input.dataset.scope = budget.scope;
      input.dataset.budgetKey = key;
      input.type = key === 'strictTokenLimit' ? 'checkbox' : 'number';
      if (input.type === 'checkbox') input.checked = budget.values[key] ?? true;
      else { input.min = '1'; input.step = '1'; input.required = true; input.value = budget.values[key]; }
      input.addEventListener('change', () => {
        try {
          const current = JSON.parse(definitionEditor.value);
          const value = input.type === 'checkbox' ? input.checked : Number(input.value);
          if (budget.scope === 'global') current.budget[key] = value;
          else {
            const configs = current.configRefs.filter(c => c.scope === budget.scope);
            const config = configs.find(c => key in c.values) || configs[0];
            config.values[key] = value;
          }
          definitionEditor.value = JSON.stringify(current, null, 2);
        } catch { serviceResult.textContent = '请先修正实例配置 JSON'; }
      });
      label.append(input); target.append(label);
    }
  }
}
definitionEditor.addEventListener('change', () => {
  try { showBudgetFields(JSON.parse(definitionEditor.value)); }
  catch { serviceResult.textContent = '实例配置 JSON 无效'; }
});
function showUsage(usage) {
  const qualities = {exact: '精确', upper_bound: '上界', estimated: '估算', unsupported: '未知'};
  const lines = [];
  const bindings = new Set([...Object.keys(usage.loops?.bindings || {}), ...Object.keys(usage.tokens?.bindings || {})]);
  for (const binding of [null, ...bindings]) {
    const loop = binding === null ? usage.loops?.global : usage.loops?.bindings[binding];
    const token = binding === null ? usage.tokens?.global : usage.tokens?.bindings[binding];
    lines.push(`${binding === null ? '任务总量' : '包 ' + binding}：loop ${loop ?? 0}` + (token
      ? `；token ${token.totalTokens ?? '未知'}（输入 ${token.inputTokens ?? '未知'}，输出 ${token.outputTokens ?? '未知'}；${qualities[token.quality]}；预留 ${token.reservedTokens}；来源 ${token.sources.join('、')}）`
      : '；尚无模型用量'));
  }
  document.querySelector('#task-usage').textContent = lines.join('\n');
}

document.querySelector('#task-cancel').addEventListener('click', async () => {
  const runId = document.querySelector('#task-run-id').value.trim();
  const generation = taskQueryGeneration;
  document.querySelector('#task-cancel').disabled = true;
  document.querySelector('#task-cancel-status').textContent = '正在请求取消…';
  try {
    const response = await window.agentPlatform.cancelRun(runId);
    if (generation !== taskQueryGeneration) return;
    if (!response.ok) {
      taskError.textContent = taskFailure(response.error);
      document.querySelector('#task-cancel-status').textContent = '取消请求未成功';
      document.querySelector('#task-cancel').disabled = false;
      return;
    }
    clearTimeout(taskPollTimer);
    await pollTask(runId, ++taskQueryGeneration);
  } catch {
    if (generation !== taskQueryGeneration) return;
    document.querySelector('#task-cancel-status').textContent = '取消请求失败，可重试或查询状态';
    document.querySelector('#task-cancel').disabled = false;
  }
});

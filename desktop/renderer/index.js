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
    await refreshEnvironments();
    await refreshServices();
    await flowEditor.refresh();
    status.textContent = `后端已就绪：${result.address}`;
    healthButton.disabled = false;
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
const serviceResult = document.querySelector('#service-result');
let services = [];
let backendAddress = '';
async function refreshServices() {
  const result = await window.agentPlatform.listServices();
  if (!result.ok) { serviceResult.textContent = errorText(result.error); return; }
  services = result.data;
  updateTaskServices();
}
function updateTaskServices(selected = taskServiceSelect.value) {
  taskServiceSelect.replaceChildren(new Option('请选择服务', ''));
  for (const item of services) taskServiceSelect.add(new Option(`${item.name} · ${item.current.version}`, item.serviceId));
  taskServiceSelect.value = selected;
  showTaskService();
}
document.querySelector('#task-service-refresh').addEventListener('click', async () => {
  const result = await window.agentPlatform.listServices();
  if (!result.ok) { taskError.textContent = taskFailure(result.error); return; }
  services = result.data;
  updateTaskServices();
  taskError.textContent = '';
});
const taskStatus = document.querySelector('#task-status');
const taskError = document.querySelector('#task-error');
let taskPollTimer;
let taskQueryGeneration = 0;
function taskFailure(error) {
  return `${error.code} · ${error.stage}：${errorText(error)}`;
}
function showTaskService() {
  const selected = services.find(s=>s.serviceId===taskServiceSelect.value);
  document.querySelector('#task-current').textContent = selected
    ? `稳定入口 ${selected.serviceId} · 当前实例 ${selected.activeInstanceId} · 版本 ${selected.current.version}` : '请选择已保存服务';
}
taskServiceSelect.addEventListener('change',showTaskService);
document.querySelector('#task-example').addEventListener('click', async () => {
  const id=taskServiceSelect.value;
  if (!id) { taskError.textContent = '请先选择已保存的服务'; return; }
  const response = await window.agentPlatform.serviceSchema(id);
  if(taskServiceSelect.value!==id)return;
  if (!response.ok) { taskError.textContent = taskFailure(response.error); return; }
  const index=services.findIndex(s=>s.serviceId===id);services[index]=response.data.service;showTaskService();
  if(!response.data.examples.length){taskError.textContent='服务没有可用输入样例，请按输入契约填写';return;}
  document.querySelector('#task-input').value = JSON.stringify(response.data.examples[0].input, null, 2);
  taskError.textContent = '已填入服务校验过的输入样例，可编辑后提交。';
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
    if (step.executionPath?.length) item.textContent += ' · 路径 ' + step.executionPath.join(' / ');
    if (Object.keys(step.usage).length) item.textContent += ` · 用量 ${JSON.stringify(step.usage)}`;
    if (step.output !== null) { const output=document.createElement('pre');output.textContent=JSON.stringify(step.output,null,2);item.append(output); }
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

function showUsage(usage) {
  const qualities = {exact: '供应商报告', unsupported: '未知'};
  const lines = [];
  const bindings = new Set([...Object.keys(usage.loops?.bindings || {}), ...Object.keys(usage.tokens?.bindings || {})]);
  for (const binding of [null, ...bindings]) {
    const loop = binding === null ? usage.loops?.global : usage.loops?.bindings[binding];
    const token = binding === null ? usage.tokens?.global : usage.tokens?.bindings[binding];
    lines.push(`${binding === null ? '任务总量' : '包 ' + binding}：loop ${loop ?? 0}` + (token
      ? `；token ${token.totalTokens ?? '未知'}（输入 ${token.inputTokens ?? '未知'}，输出 ${token.outputTokens ?? '未知'}；${qualities[token.quality]}；来源 ${token.sources.join('、')}）`
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

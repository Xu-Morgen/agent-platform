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
    await refreshPlatform();
    await refreshRunHistory();
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
  environmentResult.textContent = occupied.length ? `环境被任务占用：${occupied.join('、')}` : value ? `已加载「${value.name}」 · ${value.connections.length} 个连接 · 修订 ${value.revision}` : '';
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
    environmentResult.textContent = `环境已保存 · ${result.data.name} · ${result.data.connections.length} 个连接`;
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
let watchedRunId = '', lastRunStatus = '', taskSubmitting = false;
const runStatusNames = {queued:'排队中',running:'运行中',completed:'已完成',failed:'失败',cancelled:'已取消'};
function taskElement(tag, text, className) {
  const item=document.createElement(tag);item.textContent=text ?? '';if(className)item.className=className;return item;
}
function setTaskStatus(text, status='idle') { taskStatus.textContent=text;taskStatus.dataset.status=status; }
function taskInputNotice(text, error=false) {
  const notice=document.querySelector('#task-input-notice');notice.textContent=text;notice.dataset.error=String(error);
}
function taskResultPlaceholder(title, description) {
  const empty=document.querySelector('#task-result-empty');empty.hidden=false;
  empty.replaceChildren(taskElement('span','↳'),taskElement('strong',title),taskElement('p',description));
  const result=document.querySelector('#task-result');result.hidden=true;result.textContent='';
}
function focusTaskInspection() {
  const panel=document.querySelector('#task-inspection');panel.scrollIntoView({behavior:'smooth',block:'start'});panel.focus({preventScroll:true});
}
function highlightHistoryTask() {
  for(const button of document.querySelectorAll('.run-history-card'))button.setAttribute('aria-pressed',String(button.dataset.runId===watchedRunId));
}
function taskFailure(error) {
  return `${error.code} · ${error.stage}：${errorText(error)}`;
}
let taskSchemaGeneration = 0;
async function showTaskService() {
  const generation = ++taskSchemaGeneration;
  const selected = services.find(s=>s.serviceId===taskServiceSelect.value);
  document.querySelector('#task-current').textContent = selected
    ? `当前版本 ${selected.current.version} · ${selected.name} · 提交后固定使用该版本执行` : '请选择已保存的服务，或前往服务配置创建一个服务。';
  document.querySelector('#task-submit').disabled=!selected || taskSubmitting;
  document.querySelector('#task-example').disabled=!selected;
  taskInputNotice('');
  window.taskFiles.setSchema({});
  if (selected) {
    document.querySelector('#task-submit').disabled = true;
    const response = await window.agentPlatform.serviceSchema(selected.serviceId);
    if (generation !== taskSchemaGeneration) return;
    if (!response.ok) { taskInputNotice(taskFailure(response.error),true);return; }
    window.taskFiles.setSchema(response.data.input);
    document.querySelector('#task-submit').disabled = taskSubmitting || window.taskFiles.pending;
  }
}
window.addEventListener('task-files-change', () => { document.querySelector('#task-submit').disabled = !taskServiceSelect.value || taskSubmitting || window.taskFiles.pending; });
window.addEventListener('task-files-error', event => taskInputNotice(event.detail, true));
window.addEventListener('task-files-notice', event => taskInputNotice(event.detail));
taskServiceSelect.addEventListener('change',showTaskService);
document.querySelector('#task-example').addEventListener('click', async () => {
  const id=taskServiceSelect.value;
  if (!id) { taskInputNotice('请先选择已保存的服务',true); return; }
  const response = await window.agentPlatform.serviceSchema(id);
  if(taskServiceSelect.value!==id)return;
  if (!response.ok) { taskInputNotice(taskFailure(response.error),true); return; }
  const index=services.findIndex(s=>s.serviceId===id);services[index]=response.data.service;showTaskService();
  if(!response.data.examples.length){taskInputNotice('服务没有可用输入样例，请按输入契约填写。',true);return;}
  document.querySelector('#task-input').value = JSON.stringify(response.data.examples[0].input, null, 2);
  document.querySelector('#task-input').setCustomValidity('');
  taskInputNotice('已填入输入样例，可编辑后提交。');
});
document.querySelector('#task-input').addEventListener('input',()=>{
  document.querySelector('#task-input').setCustomValidity('');taskInputNotice('');
});
document.querySelector('#task-format').onclick=()=>{
  const input=document.querySelector('#task-input');
  try { input.value=JSON.stringify(JSON.parse(input.value),null,2);input.setCustomValidity('');taskInputNotice('JSON 格式已整理。'); }
  catch { input.setCustomValidity('请输入有效的 JSON');taskInputNotice('JSON 格式无效，请检查引号、逗号和括号。',true);input.reportValidity(); }
};
async function pollTask(runId, generation) {
  const response = await window.agentPlatform.getRun(runId);
  if (generation !== taskQueryGeneration) return;
  if (!response.ok) {
    taskError.textContent = taskFailure(response.error);setTaskStatus('查询失败','failed');
    document.querySelector('#task-detail-hint').textContent='未能读取最新任务状态，请重新查询。';
    document.querySelector('#task-cancel').disabled=true;
    taskResultPlaceholder('暂时无法读取任务','请检查任务 ID 或重新查询。');return;
  }
  const run = response.data;
  setTaskStatus(runStatusNames[run.status] || run.status,run.status);
  document.querySelector('#task-detail-hint').textContent=({queued:'任务已提交，等待开始执行。',running:'任务正在执行，状态和步骤将自动更新。',completed:'任务已完成，可查看返回结果和每一步的输出。',failed:'任务执行失败，请查看错误信息与执行步骤。',cancelled:'任务已停止，已执行的步骤保留在下方。'})[run.status];
  const metadata=document.querySelector('#task-metadata');metadata.hidden=false;metadata.replaceChildren();
  for(const [label,value] of [['调用服务',services.find(s=>s.serviceId===run.serviceId)?.name || run.serviceId],['实际版本','v'+run.version],['提交时间',new Date(run.createdAt).toLocaleString('zh-CN',{hour12:false})],['任务 ID',run.runId]])metadata.append(taskElement('dt',label),taskElement('dd',value));
  document.querySelector('#task-request-details').hidden=false;
  document.querySelector('#task-request-input').textContent=JSON.stringify(run.input,null,2);
  taskError.textContent = run.error ? taskFailure(run.error) : '';
  document.querySelector('#task-cancel').disabled = !['queued', 'running'].includes(run.status) || run.cancelRequested;
  document.querySelector('#task-cancel-status').textContent = run.cancelRequested
    ? (run.status === 'failed' ? '取消等待失败，请查看原始错误' : run.status === 'cancelled' ? '已取消'
      : run.cancelPhase === 'waiting_transport' ? '取消已受理，等待当前模型传输结束' : '取消已受理，等待停止执行') : '';
  showUsage(run.usage);
  document.querySelector('#task-loop-count').textContent=run.usage.loops?.global ?? 0;
  const token=run.usage.tokens?.global;
  document.querySelector('#task-token-count').textContent=token ? token.totalTokens ?? '未知' : '—';
  document.querySelector('#task-step-count').textContent=run.steps.filter(step=>step.status==='completed').length;
  const steps = document.querySelector('#task-steps');
  const opened=new Set(Array.from(steps.querySelectorAll('details[open]')).map(detail=>detail.dataset.stepKey));
  steps.replaceChildren();
  if(!run.steps.length)steps.append(taskElement('li','还没有执行步骤记录。','field-hint'));
  run.steps.forEach((step,index)=>{
    const item=taskElement('li','','step-record');item.dataset.status=step.status;item.append(taskElement('span','','step-dot'));
    const heading=taskElement('div','','step-heading');const badge=taskElement('span',runStatusNames[step.status] || step.status,'run-status');badge.dataset.status=step.status;
    heading.append(taskElement('strong',step.stepId==='nodes.output'?'服务返回':step.stepId.replace(/^nodes\./,'')),badge);item.append(heading);
    const kindNames={node:'节点',block:'通用块',package:'业务包',model:'模型调用',step:'执行步骤'};
    const caption=`${kindNames[step.kind] || step.kind} · 尝试 ${step.attempt}${step.packageBindingId ? ' · 包 '+step.packageBindingId : ''}${step.executionPath?.length ? ' · '+step.executionPath.join(' / ') : ''}`;
    item.append(taskElement('p',caption,'step-caption'));
    if(step.error)item.append(taskElement('p',taskFailure(step.error),'task-error'));
    if(step.progress && Object.keys(step.progress).length)item.append(taskElement('p',
      (step.progress.message || step.progress.phase || '') + (step.progress.current != null ? ` · ${step.progress.current}${step.progress.total != null ? ' / '+step.progress.total : ''}` : ''),'step-caption'));
    if(step.output!==null || Object.keys(step.usage).length){
      const detail=document.createElement('details');detail.dataset.stepKey=JSON.stringify([index,step.stepId,step.attempt,step.executionPath]);detail.open=opened.has(detail.dataset.stepKey);
      detail.append(taskElement('summary','查看步骤输出与用量'));
      if(step.output!==null)detail.append(taskElement('pre',JSON.stringify(step.output,null,2)));
      if(Object.keys(step.usage).length)detail.append(taskElement('pre','用量：'+JSON.stringify(step.usage,null,2)));
      item.append(detail);
    }
    steps.append(item);
  });
  if(['completed','failed','cancelled'].includes(run.status) && lastRunStatus!==run.status)refreshRunHistory();
  lastRunStatus=run.status;
  if (run.status === 'completed') {
    const result = await window.agentPlatform.getRunResult(runId);
    if (generation !== taskQueryGeneration) return;
    if (result.ok) {
      const output=document.querySelector('#task-result');output.textContent=JSON.stringify(result.data.result,null,2);output.hidden=false;document.querySelector('#task-result-empty').hidden=true;
    } else { taskError.textContent=taskFailure(result.error);taskResultPlaceholder('结果读取失败','任务已完成，请重新打开任务获取结果。'); }
  } else {
    taskResultPlaceholder(run.status==='failed'?'本次任务未产生最终结果':run.status==='cancelled'?'任务已取消':'等待任务完成',run.status==='failed'?'查看错误信息后，可修改输入并重新提交。':run.status==='cancelled'?'可以查看已记录的执行步骤。':'执行成功后，返回的数据会自动显示在这里。');
    if (run.status === 'queued' || run.status === 'running')taskPollTimer = setTimeout(() => pollTask(runId, generation), 500);
  }
}
function watchTask(runId) {
  clearTimeout(taskPollTimer);
  const generation = ++taskQueryGeneration;
  watchedRunId=runId;lastRunStatus='';highlightHistoryTask();
  document.querySelector('#task-run-id').value = runId;
  taskResultPlaceholder('正在读取任务','稍候将显示运行状态和结果。');
  document.querySelector('#task-steps').replaceChildren(taskElement('li','正在读取执行步骤…','field-hint'));
  document.querySelector('#task-metadata').hidden=true;
  document.querySelector('#task-request-details').hidden=true;
  document.querySelector('#task-request-details').open=false;
  document.querySelector('#task-request-input').textContent='';
  document.querySelector('#task-detail-hint').textContent='正在查询任务记录…';
  for(const id of ['task-loop-count','task-token-count','task-step-count'])document.getElementById(id).textContent='—';
  taskError.textContent = '';
  document.querySelector('#task-usage').textContent = '正在读取用量…';
  document.querySelector('#task-cancel').disabled = true;
  document.querySelector('#task-cancel-status').textContent = '';
  setTaskStatus('查询中…');
  return pollTask(runId, generation);
}
document.querySelector('#task-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.querySelector('#task-submit');
  taskSubmitting=true;button.disabled=true;
  try {
    const selected = services.find(value => value.serviceId === taskServiceSelect.value);
    if (!selected) { taskInputNotice('请先选择已保存的服务',true); return; }
    const input = window.taskFiles.input(JSON.parse(document.querySelector('#task-input').value));
    const response = await window.agentPlatform.submitRun({ serviceId: selected.serviceId, expectedInstanceId: selected.activeInstanceId, input });
    if (!response.ok) { taskInputNotice(taskFailure(response.error),true); return; }
    taskInputNotice('任务已提交，可在任务详情中查看运行状态。');focusTaskInspection();
    await watchTask(response.data.runId);
    await refreshRunHistory();
  } catch (error) {
    taskInputNotice(error instanceof SyntaxError ? 'JSON 格式无效，请检查引号、逗号和括号。' : error.message || '任务请求失败，请稍后重试。',true);
  } finally { taskSubmitting=false;button.disabled=!taskServiceSelect.value; }
});
document.querySelector('#task-query-form').addEventListener('submit', event => {
  event.preventDefault();
  focusTaskInspection();watchTask(document.querySelector('#task-run-id').value.trim());
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
  const runId = watchedRunId;
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


async function refreshPlatform() {
  const response = await window.agentPlatform.platformInfo();
  const note = document.querySelector('.session-note');
  note.textContent = !response.ok ? '无法读取存储状态：' + errorText(response.error)
    : response.data.persistent
      ? `本地 PostgreSQL：配置、源码、草稿、版本与任务跨重启保留。数据目录：${response.data.dataDirectory || '未提供'}。中断任务不会自动重跑。`
      : '开发用内存模式：退出后数据清空。桌面正常启动应使用本地 PostgreSQL。';
}
let historyOffset = 0;
let historyGeneration = 0;
async function refreshRunHistory() {
  const generation = ++historyGeneration;
  const query = {limit: 20, offset: historyOffset};
  if (taskServiceSelect.value) query.serviceId = taskServiceSelect.value;
  const filter = document.querySelector('#run-history-status').value;
  if (filter) query.status = filter;
  const response = await window.agentPlatform.listRuns(query);
  if (generation !== historyGeneration) return;
  const message = document.querySelector('#run-history-result');
  if (!response.ok) { message.textContent = errorText(response.error); return; }
  const list = document.querySelector('#run-history');
  list.replaceChildren();
  if(!response.data.length)list.append(taskElement('li','没有匹配的任务。提交一次任务后，可在这里重新打开。','field-hint'));
  for (const run of response.data) {
    const item = document.createElement('li');
    const button=taskElement('button','','run-history-card');button.type='button';button.dataset.runId=run.runId;
    button.setAttribute('aria-pressed',String(run.runId===watchedRunId));
    const top=taskElement('span');const badge=taskElement('span',runStatusNames[run.status] || run.status,'run-status');badge.dataset.status=run.status;
    top.append(taskElement('strong',services.find(service=>service.serviceId===run.serviceId)?.name || '服务任务'),badge);
    const info=taskElement('span');const date=taskElement('time',new Date(run.createdAt).toLocaleString('zh-CN',{hour12:false}));date.dateTime=run.createdAt;
    info.append(date,taskElement('small','v'+run.version));button.append(top,info,taskElement('code',run.runId));
    button.onclick=()=>{focusTaskInspection();watchTask(run.runId);};
    item.append(button);list.append(item);
  }
  message.textContent = response.data.length ? `第 ${Math.floor(historyOffset / 20) + 1} 页` : '没有匹配的任务';
  document.querySelector('#run-history-prev').disabled = historyOffset === 0;
  document.querySelector('#run-history-next').disabled = response.data.length < 20;
}
function resetRunHistory() { historyOffset = 0; refreshRunHistory(); }
document.querySelector('#run-history-refresh').onclick = resetRunHistory;
document.querySelector('#run-history-status').onchange = resetRunHistory;
taskServiceSelect.addEventListener('change', resetRunHistory);
document.querySelector('#run-history-prev').onclick = () => { historyOffset = Math.max(0, historyOffset - 20); refreshRunHistory(); };
document.querySelector('#run-history-next').onclick = () => { historyOffset += 20; refreshRunHistory(); };

document.querySelector('#task-steps').append(taskElement('li','选择任务后显示执行记录。','field-hint'));
showTaskService();

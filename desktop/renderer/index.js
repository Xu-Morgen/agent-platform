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
  document.querySelector('#environment-connections').value = JSON.stringify(value?.connections || [
    { connectionId: 'model', kind: 'model', baseUrl: 'http://localhost:9000', model: 'synthetic', timeoutSeconds: 60 },
  ], null, 2);
  document.querySelector('#environment-credential').value = '';
  environmentResult.textContent = value ? `环境 ${value.environmentId} · revision ${value.revision}；凭据 ********（仅显示引用）` : '';
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
    const connections = JSON.parse(document.querySelector('#environment-connections').value);
    const credential = document.querySelector('#environment-credential').value;
    if (credential) {
      const connection = connections.find(item => item.connectionId === document.querySelector('#credential-connection').value);
      if (!connection) throw new Error('凭据对应的连接标识不存在');
      delete connection.credentialRef;
      connection.credential = credential;
    }
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
const definitionSelect = document.querySelector('#definition-select');
const serviceResult = document.querySelector('#service-result');
const definitionEditor = document.querySelector('#service-definition');
const definitions = new Map();
let services = [];
let backendAddress = '';
function showDefinition(value) {
  definitionEditor.value = JSON.stringify(value.definition, null, 2);
  document.querySelector('#service-schemas').textContent = JSON.stringify(value.schemas, null, 2);
  document.querySelector('#budget-defaults').textContent = `全局预算默认值（各包绑定上限之和，可在 budget 修改）：${JSON.stringify(value.budgetDefaults || value.definition.budget)}`;
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
    ? `稳定入口：${backendAddress}/api/v1/services/${selected.serviceId} · 当前版本 ${selected.current.version} · ${selected.activeInstanceId}` : '保存后生成稳定服务标识';
  if (!selected) return;
  const result = await window.agentPlatform.serviceSchema(selected.serviceId);
  if (!result.ok) { serviceResult.textContent = errorText(result.error); return; }
  const value = result.data;
  rememberDefinition({ loadId: value.definitionLoadId, definition: value.definition,
    schemas: { input: value.input, output: value.output, ...definitions.get(value.definitionLoadId)?.schemas },
    budgetDefaults: value.definition.budget });
}
async function refreshServices(selected = serviceSelect.value) {
  const result = await window.agentPlatform.listServices();
  if (!result.ok) { serviceResult.textContent = errorText(result.error); return; }
  services = result.data;
  serviceSelect.replaceChildren(new Option('新建服务', ''));
  for (const item of services) serviceSelect.add(new Option(item.name, item.serviceId));
  serviceSelect.value = selected;
  await editService();
}
serviceSelect.addEventListener('change', editService);
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

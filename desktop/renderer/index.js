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
    status.textContent = `后端已就绪：${result.address}`;
    healthButton.disabled = false;
    await refreshEnvironments();
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

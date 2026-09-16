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
  } catch {
    status.textContent = '桌面请求桥不可用';
  }
}
healthButton.addEventListener('click', refreshHealth);
refreshHealth();

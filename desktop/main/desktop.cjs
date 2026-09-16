const { createWindow } = require('./window.cjs');

async function openDesktop(backend) {
  const window = await createWindow();
  const setStatus = (message) => window.webContents.executeJavaScript(`document.querySelector('#status').textContent = ${JSON.stringify(message)}`);
  await setStatus('后端启动中…');
  try {
    const ready = await backend.start();
    if (!window.isDestroyed()) await setStatus(`后端已就绪：${ready.address}`);
  } catch (error) {
    if (!window.isDestroyed()) await setStatus(`启动失败：${error.message}`);
  }
  return window;
}
module.exports = { openDesktop };

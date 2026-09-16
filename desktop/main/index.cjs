const { app } = require('electron');
const { openDesktop } = require('./desktop.cjs');
const { Backend } = require('./backend.cjs');

const backend = new Backend();
let exiting = false;
app.on('before-quit', (event) => {
  if (exiting) return;
  event.preventDefault();
  backend.stop().finally(() => { exiting = true; app.quit(); });
});
app.on('window-all-closed', () => app.quit());
app.whenReady().then(() => openDesktop(backend)).catch((error) => {
  console.error('桌面启动失败:', error.message);
  backend.stop().finally(() => app.exit(1));
});

module.exports = { backend };

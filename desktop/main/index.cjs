const { app } = require('electron');
const { openDesktop } = require('./desktop.cjs');
const { Backend } = require('./backend.cjs');

const backend = new Backend();
app.on('window-all-closed', () => app.quit());
app.whenReady().then(() => openDesktop(backend)).catch((error) => {
  console.error('桌面启动失败:', error.message);
  app.exit(1);
});

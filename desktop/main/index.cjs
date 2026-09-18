const { app, BrowserWindow } = require('electron');
const path = require('node:path');
const { openDesktop } = require('./desktop.cjs');
const { Backend } = require('./backend.cjs');

app.setName('Agent Platform');
const backend = new Backend();
let exiting = false;
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const window = BrowserWindow.getAllWindows()[0];
    if (window) { if (window.isMinimized()) window.restore(); window.focus(); }
  });
  app.on('before-quit', (event) => {
    if (exiting) return;
    event.preventDefault();
    backend.stop().finally(() => { exiting = true; app.quit(); });
  });
  app.on('window-all-closed', () => app.quit());
  app.whenReady().then(() => {
    backend.dataDirectory = path.join(app.getPath('userData'), 'storage');
    return openDesktop(backend);
  }).catch((error) => {
    console.error('桌面启动失败:', error.message);
    backend.stop().finally(() => app.exit(1));
  });
}

module.exports = { backend };

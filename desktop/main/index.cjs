const { app } = require('electron');
const { createWindow } = require('./window.cjs');

app.on('window-all-closed', () => app.quit());
app.whenReady().then(createWindow).catch((error) => {
  console.error('桌面启动失败:', error.message);
  app.exit(1);
});

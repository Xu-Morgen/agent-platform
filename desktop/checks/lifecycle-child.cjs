// 加载真实桌面主入口；只负责触发验收所需的关闭动作。
const { app, BrowserWindow } = require('electron');
const { backend } = require('../main/index.cjs');
app.whenReady().then(async () => {
  const ready = await backend.start();
  console.log('LIFECYCLE ' + JSON.stringify(ready));
  if (!process.argv.includes('--parent-kill')) {
    for (const window of BrowserWindow.getAllWindows()) window.close();
  }
}).catch((error) => { console.error(error); app.exit(1); });

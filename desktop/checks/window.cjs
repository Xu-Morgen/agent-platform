const { app } = require('electron');
const assert = require('node:assert/strict');
const { createWindow } = require('../main/window.cjs');
const watchdog = setTimeout(() => app.exit(1), 15000);
app.on('window-all-closed', () => app.quit());
app.whenReady().then(async () => {
  const window = await createWindow();
  assert.equal(await window.webContents.executeJavaScript('document.querySelector("h1").textContent'), 'Agent Platform');
  assert.equal(await window.webContents.executeJavaScript('typeof require'), 'undefined');
  console.log('T02 PASS: real HTML window loaded, Node unavailable; closing window');
  clearTimeout(watchdog);
  window.close();
}).catch((error) => { console.error(error); app.exit(1); });

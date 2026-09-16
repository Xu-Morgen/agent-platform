const { BrowserWindow } = require('electron');
const path = require('node:path');

async function createWindow() {
  const window = new BrowserWindow({
    width: 960, height: 680, title: 'Agent Platform',
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },
  });
  await window.loadFile(path.join(__dirname, '../renderer/index.html'));
  return window;
}
module.exports = { createWindow };

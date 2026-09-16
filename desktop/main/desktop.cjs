const { createWindow } = require('./window.cjs');
const { registerHealthBridge } = require('./ipc.cjs');

async function openDesktop(backend) {
  registerHealthBridge(backend);
  return createWindow();
}
module.exports = { openDesktop };

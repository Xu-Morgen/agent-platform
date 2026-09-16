const { createWindow } = require('./window.cjs');
const { registerHealthBridge, registerConfigurationBridge } = require('./ipc.cjs');

async function openDesktop(backend) {
  registerHealthBridge(backend);
  registerConfigurationBridge(backend);
  return createWindow();
}
module.exports = { openDesktop };

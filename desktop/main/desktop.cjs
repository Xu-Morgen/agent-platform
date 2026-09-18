const { createWindow } = require('./window.cjs');
const { registerHealthBridge, registerConfigurationBridge, registerResourcePathBridge } = require('./ipc.cjs');

async function openDesktop(backend) {
  registerHealthBridge(backend);
  registerConfigurationBridge(backend);
  registerResourcePathBridge();
  return createWindow();
}
module.exports = { openDesktop };

const { ipcMain } = require('electron');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { validate } = require('./validate.cjs');
const healthSchema = require('../contracts/health.schema.json');
const errorSchema = require('../contracts/error.schema.json');
const pageURL = pathToFileURL(path.join(__dirname, '../renderer/index.html')).href;

function failure(code, message) {
  return { ok: false, error: { code, stage: 'desktop.health', message, runId: null, fieldPath: null, details: {} } };
}

function registerHealthBridge(backend) {
  ipcMain.removeHandler('platform:health');
  ipcMain.handle('platform:health', async (event) => {
    if (event.senderFrame?.url !== pageURL || event.senderFrame !== event.sender.mainFrame) {
      return failure('CONTRACT_VALIDATION_ERROR', '请求来源无效');
    }
    try {
      await backend.start();
    } catch (error) {
      return failure('STARTUP_ERROR', error.message);
    }
    if (!backend.address) return failure('BACKEND_UNAVAILABLE', '后端连接已关闭');
    try {
      const response = await fetch(`${backend.address}/api/v1/health`, { signal: AbortSignal.timeout(3000) });
      const data = await response.json();
      if (!response.ok) {
        return validate(errorSchema, data) ? { ok: false, error: data } : failure('OUTPUT_VALIDATION_ERROR', '后端错误响应不符合契约');
      }
      if (!validate(healthSchema, data)) return failure('OUTPUT_VALIDATION_ERROR', '健康响应不符合契约');
      return { ok: true, data, address: backend.address };
    } catch {
      return failure('BACKEND_UNAVAILABLE', '无法读取后端健康状态');
    }
  });
}
module.exports = { registerHealthBridge };

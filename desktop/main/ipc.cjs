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

// 路由由主进程固定，页面不能指定任意 URL 或 HTTP 方法。
const operations = {
  submitRun: (body) => ['POST', '/runs', body],
  getRun: (id) => ['GET', `/runs/${encodeURIComponent(id)}`],
  getRunResult: (id) => ['GET', `/runs/${encodeURIComponent(id)}/result`],
  serviceHistory: (id) => ['GET', `/services/${encodeURIComponent(id)}/versions`],
  activateService: (id, instanceId) => ['POST', `/services/${encodeURIComponent(id)}/activate`, { instanceId }],
  loadDefinition: (body) => ['POST', '/registry/load', body],
  listServices: () => ['GET', '/services'],
  createService: (body) => ['POST', '/services', body],
  saveServiceVersion: (id, body) => ['POST', `/services/${encodeURIComponent(id)}/versions`, body],
  serviceSchema: (id) => ['GET', `/services/${encodeURIComponent(id)}/schema`],
  listEnvironments: () => ['GET', '/environments'],
  createEnvironment: (body) => ['POST', '/environments', body],
  updateEnvironment: (id, body) => ['PUT', `/environments/${encodeURIComponent(id)}`, body],
};
function registerConfigurationBridge(backend) {
  for (const [name, route] of Object.entries(operations)) {
    ipcMain.removeHandler(`platform:${name}`);
    ipcMain.handle(`platform:${name}`, async (event, ...args) => {
      if (event.senderFrame?.url !== pageURL || event.senderFrame !== event.sender.mainFrame) {
        return failure('CONTRACT_VALIDATION_ERROR', '请求来源无效');
      }
      if (!backend.address) return failure('BACKEND_UNAVAILABLE', '后端尚未就绪');
      try {
        const [method, routePath, body] = route(...args);
        const response = await fetch(`${backend.address}/api/v1${routePath}`, {
          method, headers: { 'Content-Type': 'application/json' },
          body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(10000),
        });
        const data = await response.json();
        if (!response.ok) return validate(errorSchema, data) ? { ok: false, error: data } : failure('OUTPUT_VALIDATION_ERROR', '错误响应不符合契约');
        return { ok: true, data };
      } catch {
        return failure('BACKEND_UNAVAILABLE', '配置请求失败，请检查后端连接');
      }
    });
  }
}
module.exports.registerConfigurationBridge = registerConfigurationBridge;

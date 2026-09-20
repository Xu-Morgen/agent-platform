const { ipcMain, BrowserWindow, dialog } = require('electron');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { validate } = require('./validate.cjs');
const healthSchema = require('../contracts/health.schema.json');
const errorSchema = require('../contracts/error.schema.json');
const pageURL = pathToFileURL(path.join(__dirname, '../renderer/index.html')).href;

function failure(code, message, stage = 'desktop.health') {
  return { ok: false, error: { code, stage, message, runId: null, fieldPath: null, details: {} } };
}

function registerResourcePathBridge() {
  ipcMain.removeHandler('platform:selectResourcePath');
  ipcMain.handle('platform:selectResourcePath', async (event, kind) => {
    const fail = (message) => failure('CONTRACT_VALIDATION_ERROR', message, 'desktop.resourcePath');
    if (event.senderFrame?.url.split('#')[0] !== pageURL || event.senderFrame !== event.sender.mainFrame) {
      return fail('请求来源无效');
    }
    if (!['package', 'block', 'contract'].includes(kind)) return fail('请选择业务包、通用块或契约');
    const owner = BrowserWindow.fromWebContents(event.sender);
    if (!owner || owner.isDestroyed()) return fail('当前窗口不可用');
    const isPackage = kind === 'package';
    try {
      const result = await dialog.showOpenDialog(owner, {
        title: isPackage ? '选择业务包目录' : kind === 'block' ? '选择通用块文件' : '选择契约文件',
        buttonLabel: '选择路径',
        properties: [isPackage ? 'openDirectory' : 'openFile'],
        ...(isPackage ? {} : { filters: [{ name: 'Python 文件', extensions: ['py'] }] }),
      });
      return { ok: true, data: { path: result.canceled ? null : result.filePaths[0] || null } };
    } catch {
      return failure('RESOURCE_PATH_ERROR', '无法打开路径选择窗口，请重试或手动填写路径', 'desktop.resourcePath');
    }
  });
}

function registerHealthBridge(backend) {
  ipcMain.removeHandler('platform:health');
  ipcMain.handle('platform:health', async (event) => {
    if (event.senderFrame?.url.split('#')[0] !== pageURL || event.senderFrame !== event.sender.mainFrame) {
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
module.exports = { registerHealthBridge, registerResourcePathBridge };

// 路由由主进程固定，页面不能指定任意 URL 或 HTTP 方法。
const operations = {
  prepareResource: (body) => ['POST', '/preparations', body],
  preparationStatus: (id) => ['GET', `/preparations/${encodeURIComponent(id)}`],
  cancelPreparation: (id) => ['POST', `/preparations/${encodeURIComponent(id)}/cancel`],
  removeTaskFile: (id) => ['DELETE', `/files/${encodeURIComponent(id)}`],
  platformInfo: () => ['GET', '/platform'],
  listRuns: (query = {}) => ['GET', `/runs?${new URLSearchParams(query)}`],
  createDraft: (body) => ['POST', '/drafts', body],
  listDrafts: () => ['GET', '/drafts'],
  getDraft: (id) => ['GET', `/drafts/${encodeURIComponent(id)}`],
  updateDraft: (id, body) => ['PUT', `/drafts/${encodeURIComponent(id)}`, body],
  validateDraft: (id) => ['POST', `/drafts/${encodeURIComponent(id)}/validate`],
  validateFlow: (body) => ['POST', '/flows/validate', body],
  validateFlowNode: (body) => ['POST', '/flows/validate-node', body],
  validateFlowPorts: (body) => ['POST', '/flows/validate-ports', body],
  loadResource: (body) => ['POST', '/catalog/load', body],
  listResources: () => ['GET', '/catalog'],
  getResource: (id) => ['GET', `/catalog/${encodeURIComponent(id)}`],
  connectionModels: (body) => ['POST', '/connection-tools/models', body],
  testConnection: (body) => ['POST', '/connection-tools/test', body],
  cancelRun: (id) => ['POST', `/runs/${encodeURIComponent(id)}/cancel`],
  submitRun: (body) => ['POST', '/runs', body],
  getRun: (id) => ['GET', `/runs/${encodeURIComponent(id)}`],
  getRunResult: (id) => ['GET', `/runs/${encodeURIComponent(id)}/result`],
  getServiceVersion: (id, instanceId) => ['GET', `/services/${encodeURIComponent(id)}/versions/${encodeURIComponent(instanceId)}`],
  copyServiceVersion: (id, instanceId) => ['POST', `/services/${encodeURIComponent(id)}/versions/${encodeURIComponent(instanceId)}/draft`],
  serviceHistory: (id) => ['GET', `/services/${encodeURIComponent(id)}/versions`],
  activateService: (id, instanceId) => ['POST', `/services/${encodeURIComponent(id)}/activate`, { instanceId }],
  listServices: () => ['GET', '/services'],
  createService: (body) => ['POST', '/services', body],
  saveServiceVersion: (id, body) => ['POST', `/services/${encodeURIComponent(id)}/versions`, body],
  serviceSchema: (id) => ['GET', `/services/${encodeURIComponent(id)}/schema`],
  listEnvironments: () => ['GET', '/environments'],
  createEnvironment: (body) => ['POST', '/environments', body],
  updateEnvironment: (id, body) => ['PUT', `/environments/${encodeURIComponent(id)}`, body],
};
function registerConfigurationBridge(backend) {
  ipcMain.removeHandler('platform:uploadTaskFile');
  ipcMain.handle('platform:uploadTaskFile', async (event, filename) => {
    if (event.senderFrame?.url.split('#')[0] !== pageURL || event.senderFrame !== event.sender.mainFrame) {
      return failure('CONTRACT_VALIDATION_ERROR', '请求来源无效', 'desktop.files');
    }
    const owner = BrowserWindow.fromWebContents(event.sender);
    if (!owner || owner.isDestroyed() || !backend.address) return failure('BACKEND_UNAVAILABLE', '窗口或后端不可用', 'desktop.files');
    let stream;
    try {
      if (typeof filename !== 'string' || !path.isAbsolute(filename)) {
        return failure('FILE_SAVE_FAILED', '请选择本地文件', 'desktop.files');
      }
      stream = require('node:fs').createReadStream(filename);
      const response = await fetch(`${backend.address}/api/v1/files?name=${encodeURIComponent(path.basename(filename))}`, {
        method: 'POST', headers: { 'Content-Type': 'application/octet-stream' },
        body: stream, duplex: 'half', signal: AbortSignal.timeout(120000),
      });
      const data = await response.json();
      return response.ok ? { ok: true, data } : validate(errorSchema, data) ? { ok: false, error: data }
        : failure('FILE_SAVE_FAILED', '文件保存响应无效', 'desktop.files');
    } catch (error) {
      return failure('FILE_SAVE_FAILED', ['EACCES', 'ENOENT'].includes(error.code || error.cause?.code) ? '所选文件不可访问' : '文件保存失败，请重试', 'desktop.files');
    } finally { stream?.destroy(); }
  });
  for (const [name, route] of Object.entries(operations)) {
    ipcMain.removeHandler(`platform:${name}`);
    ipcMain.handle(`platform:${name}`, async (event, ...args) => {
      if (event.senderFrame?.url.split('#')[0] !== pageURL || event.senderFrame !== event.sender.mainFrame) {
        return failure('CONTRACT_VALIDATION_ERROR', '请求来源无效');
      }
      if (!backend.address) return failure('BACKEND_UNAVAILABLE', '后端尚未就绪');
      try {
        const [method, routePath, body] = route(...args);
        // 诊断使用连接自己的超时；普通配置操作保持原有 10 秒限制。
        const diagnostic = name === 'connectionModels' || name === 'testConnection';
        const seconds = body?.connection?.timeoutSeconds ?? 60;
        const timeout = diagnostic && Number.isFinite(seconds) && seconds > 0
          ? Math.min(Math.ceil(seconds * 1000) + 5000, 2147483647) : 10000;
        const response = await fetch(`${backend.address}/api/v1${routePath}`, {
          method, headers: { 'Content-Type': 'application/json' },
          body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(timeout),
        });
        const data = response.status === 204 ? null : await response.json();
        if (!response.ok) return validate(errorSchema, data) ? { ok: false, error: data } : failure('OUTPUT_VALIDATION_ERROR', '错误响应不符合契约');
        return { ok: true, data };
      } catch {
        return failure('BACKEND_UNAVAILABLE', '配置请求失败，请检查后端连接');
      }
    });
  }
}
module.exports.registerConfigurationBridge = registerConfigurationBridge;

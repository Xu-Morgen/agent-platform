const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('agentPlatform', Object.freeze({
  submitRun: (body) => ipcRenderer.invoke('platform:submitRun', body),
  getRun: (id) => ipcRenderer.invoke('platform:getRun', id),
  getRunResult: (id) => ipcRenderer.invoke('platform:getRunResult', id),
  listEnvironments: () => ipcRenderer.invoke('platform:listEnvironments'),
  createEnvironment: (body) => ipcRenderer.invoke('platform:createEnvironment', body),
  updateEnvironment: (id, body) => ipcRenderer.invoke('platform:updateEnvironment', id, body),
  loadDefinition: (body) => ipcRenderer.invoke('platform:loadDefinition', body),
  listServices: () => ipcRenderer.invoke('platform:listServices'),
  createService: (body) => ipcRenderer.invoke('platform:createService', body),
  saveServiceVersion: (id, body) => ipcRenderer.invoke('platform:saveServiceVersion', id, body),
  serviceSchema: (id) => ipcRenderer.invoke('platform:serviceSchema', id),
  serviceHistory: (id) => ipcRenderer.invoke('platform:serviceHistory', id),
  activateService: (id, instanceId) => ipcRenderer.invoke('platform:activateService', id, instanceId),
  health: () => ipcRenderer.invoke('platform:health'),
}));

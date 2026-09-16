const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('agentPlatform', Object.freeze({
  listEnvironments: () => ipcRenderer.invoke('platform:listEnvironments'),
  createEnvironment: (body) => ipcRenderer.invoke('platform:createEnvironment', body),
  updateEnvironment: (id, body) => ipcRenderer.invoke('platform:updateEnvironment', id, body),
  health: () => ipcRenderer.invoke('platform:health'),
}));

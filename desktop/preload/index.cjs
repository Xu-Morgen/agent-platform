const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('agentPlatform', Object.freeze({
  health: () => ipcRenderer.invoke('platform:health'),
}));

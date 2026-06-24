const { contextBridge, ipcRenderer, webUtils } = require('electron')

contextBridge.exposeInMainWorld('seraphielDesktop', {
  getConnection: profile => ipcRenderer.invoke('seraphiel:connection', profile),
  revalidateConnection: () => ipcRenderer.invoke('seraphiel:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('seraphiel:backend:touch', profile),
  getGatewayWsUrl: profile => ipcRenderer.invoke('seraphiel:gateway:ws-url', profile),
  openSessionWindow: sessionId => ipcRenderer.invoke('seraphiel:window:openSession', sessionId),
  getBootProgress: () => ipcRenderer.invoke('seraphiel:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('seraphiel:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('seraphiel:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('seraphiel:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('seraphiel:connection-config:test', payload),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('seraphiel:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('seraphiel:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('seraphiel:connection-config:oauth-logout', remoteUrl),
  profile: {
    get: () => ipcRenderer.invoke('seraphiel:profile:get'),
    set: name => ipcRenderer.invoke('seraphiel:profile:set', name)
  },
  api: request => ipcRenderer.invoke('seraphiel:api', request),
  notify: payload => ipcRenderer.invoke('seraphiel:notify', payload),
  requestMicrophoneAccess: () => ipcRenderer.invoke('seraphiel:requestMicrophoneAccess'),
  readFileDataUrl: filePath => ipcRenderer.invoke('seraphiel:readFileDataUrl', filePath),
  readFileText: filePath => ipcRenderer.invoke('seraphiel:readFileText', filePath),
  selectPaths: options => ipcRenderer.invoke('seraphiel:selectPaths', options),
  writeClipboard: text => ipcRenderer.invoke('seraphiel:writeClipboard', text),
  saveImageFromUrl: url => ipcRenderer.invoke('seraphiel:saveImageFromUrl', url),
  saveImageBuffer: (data, ext) => ipcRenderer.invoke('seraphiel:saveImageBuffer', { data, ext }),
  saveClipboardImage: () => ipcRenderer.invoke('seraphiel:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('seraphiel:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('seraphiel:watchPreviewFile', url),
  stopPreviewFileWatch: id => ipcRenderer.invoke('seraphiel:stopPreviewFileWatch', id),
  setTitleBarTheme: payload => ipcRenderer.send('seraphiel:titlebar-theme', payload),
  setPreviewShortcutActive: active => ipcRenderer.send('seraphiel:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('seraphiel:openExternal', url),
  fetchLinkTitle: url => ipcRenderer.invoke('seraphiel:fetchLinkTitle', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('seraphiel:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('seraphiel:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('seraphiel:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('seraphiel:setting:defaultProjectDir:pick')
  },
  revealLogs: () => ipcRenderer.invoke('seraphiel:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('seraphiel:logs:recent'),
  readDir: dirPath => ipcRenderer.invoke('seraphiel:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('seraphiel:fs:gitRoot', startPath),
  terminal: {
    dispose: id => ipcRenderer.invoke('seraphiel:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('seraphiel:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('seraphiel:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('seraphiel:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `seraphiel:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)
      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `seraphiel:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)
      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('seraphiel:close-preview-requested', listener)
    return () => ipcRenderer.removeListener('seraphiel:close-preview-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('seraphiel:open-updates', listener)
    return () => ipcRenderer.removeListener('seraphiel:open-updates', listener)
  },
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('seraphiel:window-state-changed', listener)
    return () => ipcRenderer.removeListener('seraphiel:window-state-changed', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('seraphiel:preview-file-changed', listener)
    return () => ipcRenderer.removeListener('seraphiel:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('seraphiel:backend-exit', listener)
    return () => ipcRenderer.removeListener('seraphiel:backend-exit', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('seraphiel:power-resume', listener)
    return () => ipcRenderer.removeListener('seraphiel:power-resume', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('seraphiel:boot-progress', listener)
    return () => ipcRenderer.removeListener('seraphiel:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.cjs (apps/desktop/electron/bootstrap-runner.cjs).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('seraphiel:bootstrap:get'),
  resetBootstrap: () => ipcRenderer.invoke('seraphiel:bootstrap:reset'),
  repairBootstrap: () => ipcRenderer.invoke('seraphiel:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('seraphiel:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('seraphiel:bootstrap:event', listener)
    return () => ipcRenderer.removeListener('seraphiel:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('seraphiel:version'),
  uninstall: {
    summary: () => ipcRenderer.invoke('seraphiel:uninstall:summary'),
    run: mode => ipcRenderer.invoke('seraphiel:uninstall:run', { mode })
  },
  updates: {
    check: () => ipcRenderer.invoke('seraphiel:updates:check'),
    apply: opts => ipcRenderer.invoke('seraphiel:updates:apply', opts),
    getBranch: () => ipcRenderer.invoke('seraphiel:updates:branch:get'),
    setBranch: name => ipcRenderer.invoke('seraphiel:updates:branch:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('seraphiel:updates:progress', listener)
      return () => ipcRenderer.removeListener('seraphiel:updates:progress', listener)
    }
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('seraphiel:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('seraphiel:vscode-theme:search', query)
  }
})

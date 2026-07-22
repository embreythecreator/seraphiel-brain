import { contextBridge, ipcRenderer, webUtils } from 'electron'

contextBridge.exposeInMainWorld('seraphielDesktop', {
  getConnection: profile => ipcRenderer.invoke('seraphiel:connection', profile),
  revalidateConnection: () => ipcRenderer.invoke('seraphiel:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('seraphiel:backend:touch', profile),
  getGatewayWsUrl: profile => ipcRenderer.invoke('seraphiel:gateway:ws-url', profile),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('seraphiel:window:openSession', sessionId, opts),
  openNewSessionWindow: () => ipcRenderer.invoke('seraphiel:window:openNewSession'),
  petOverlay: {
    // Main renderer → main process: window lifecycle + drag. `request` is
    // `{ bounds, screen }`; resolves with the screen bounds it actually used.
    open: request => ipcRenderer.invoke('seraphiel:pet-overlay:open', request),
    close: () => ipcRenderer.invoke('seraphiel:pet-overlay:close'),
    setBounds: bounds => ipcRenderer.send('seraphiel:pet-overlay:set-bounds', bounds),
    setIgnoreMouse: ignore => ipcRenderer.send('seraphiel:pet-overlay:ignore-mouse', ignore),
    // Flip the overlay focusable (and focus it) while the composer needs keys.
    setFocusable: focusable => ipcRenderer.send('seraphiel:pet-overlay:set-focusable', focusable),
    // Main renderer → overlay (forwarded by main): push the latest pet state.
    pushState: payload => ipcRenderer.send('seraphiel:pet-overlay:state', payload),
    // Overlay → main renderer (forwarded by main): pop back in / composer submit.
    control: payload => ipcRenderer.send('seraphiel:pet-overlay:control', payload),
    // Overlay subscribes to state pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('seraphiel:pet-overlay:state', listener)

      return () => ipcRenderer.removeListener('seraphiel:pet-overlay:state', listener)
    },
    // Main renderer subscribes to overlay control messages.
    onControl: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('seraphiel:pet-overlay:control', listener)

      return () => ipcRenderer.removeListener('seraphiel:pet-overlay:control', listener)
    }
  },
  getBootProgress: () => ipcRenderer.invoke('seraphiel:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('seraphiel:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('seraphiel:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('seraphiel:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('seraphiel:connection-config:test', payload),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('seraphiel:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('seraphiel:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('seraphiel:connection-config:oauth-logout', remoteUrl),
  // Seraphiel Cloud: one portal login powers discovery + silent per-agent sign-in
  // (cloud-auto-discovery Phase 3).
  cloud: {
    status: () => ipcRenderer.invoke('seraphiel:cloud:status'),
    login: () => ipcRenderer.invoke('seraphiel:cloud:login'),
    logout: () => ipcRenderer.invoke('seraphiel:cloud:logout'),
    discover: org => ipcRenderer.invoke('seraphiel:cloud:discover', org),
    agentSignIn: dashboardUrl => ipcRenderer.invoke('seraphiel:cloud:agent-sign-in', dashboardUrl)
  },
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
  setNativeTheme: mode => ipcRenderer.send('seraphiel:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('seraphiel:translucency', payload),
  setPreviewShortcutActive: active => ipcRenderer.send('seraphiel:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('seraphiel:openExternal', url),
  openPreviewInBrowser: url => ipcRenderer.invoke('seraphiel:openPreviewInBrowser', url),
  fetchLinkTitle: url => ipcRenderer.invoke('seraphiel:fetchLinkTitle', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('seraphiel:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('seraphiel:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('seraphiel:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('seraphiel:setting:defaultProjectDir:pick')
  },
  zoom: {
    // Current zoom of this window, as { level, percent }.
    get: () => ipcRenderer.invoke('seraphiel:zoom:get'),
    setPercent: percent => ipcRenderer.send('seraphiel:zoom:set-percent', percent),
    // Fires on every zoom change, including the Ctrl/Cmd +/-/0 shortcuts,
    // so the settings UI can stay in sync with the keyboard.
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('seraphiel:zoom:changed', listener)

      return () => ipcRenderer.removeListener('seraphiel:zoom:changed', listener)
    }
  },
  revealLogs: () => ipcRenderer.invoke('seraphiel:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('seraphiel:logs:recent'),
  readDir: dirPath => ipcRenderer.invoke('seraphiel:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('seraphiel:fs:gitRoot', startPath),
  revealPath: targetPath => ipcRenderer.invoke('seraphiel:fs:reveal', targetPath),
  openDir: dirPath => ipcRenderer.invoke('seraphiel:fs:openDir', dirPath),
  renamePath: (targetPath, newName) => ipcRenderer.invoke('seraphiel:fs:rename', targetPath, newName),
  writeTextFile: (filePath, content) => ipcRenderer.invoke('seraphiel:fs:writeText', filePath, content),
  trashPath: targetPath => ipcRenderer.invoke('seraphiel:fs:trash', targetPath),
  git: {
    worktreeList: repoPath => ipcRenderer.invoke('seraphiel:git:worktreeList', repoPath),
    worktreeAdd: (repoPath, options) => ipcRenderer.invoke('seraphiel:git:worktreeAdd', repoPath, options),
    worktreeRemove: (repoPath, worktreePath, options) =>
      ipcRenderer.invoke('seraphiel:git:worktreeRemove', repoPath, worktreePath, options),
    branchSwitch: (repoPath, branch) => ipcRenderer.invoke('seraphiel:git:branchSwitch', repoPath, branch),
    branchList: repoPath => ipcRenderer.invoke('seraphiel:git:branchList', repoPath),
    baseBranchList: repoPath => ipcRenderer.invoke('seraphiel:git:baseBranchList', repoPath),
    repoStatus: repoPath => ipcRenderer.invoke('seraphiel:git:repoStatus', repoPath),
    fileDiff: (repoPath, filePath) => ipcRenderer.invoke('seraphiel:git:fileDiff', repoPath, filePath),
    scanRepos: (roots, options) => ipcRenderer.invoke('seraphiel:git:scanRepos', roots, options),
    review: {
      list: (repoPath, scope, baseRef) => ipcRenderer.invoke('seraphiel:git:review:list', repoPath, scope, baseRef),
      diff: (repoPath, filePath, scope, baseRef, staged) =>
        ipcRenderer.invoke('seraphiel:git:review:diff', repoPath, filePath, scope, baseRef, staged),
      stage: (repoPath, filePath) => ipcRenderer.invoke('seraphiel:git:review:stage', repoPath, filePath),
      unstage: (repoPath, filePath) => ipcRenderer.invoke('seraphiel:git:review:unstage', repoPath, filePath),
      revert: (repoPath, filePath) => ipcRenderer.invoke('seraphiel:git:review:revert', repoPath, filePath),
      revParse: (repoPath, ref) => ipcRenderer.invoke('seraphiel:git:review:revParse', repoPath, ref),
      commit: (repoPath, message, push) => ipcRenderer.invoke('seraphiel:git:review:commit', repoPath, message, push),
      commitContext: repoPath => ipcRenderer.invoke('seraphiel:git:review:commitContext', repoPath),
      push: repoPath => ipcRenderer.invoke('seraphiel:git:review:push', repoPath),
      shipInfo: repoPath => ipcRenderer.invoke('seraphiel:git:review:shipInfo', repoPath),
      createPr: repoPath => ipcRenderer.invoke('seraphiel:git:review:createPr', repoPath)
    }
  },
  terminal: {
    cwd: id => ipcRenderer.invoke('seraphiel:terminal:cwd', id),
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
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('seraphiel:deep-link', listener)

    return () => ipcRenderer.removeListener('seraphiel:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('seraphiel:deep-link-ready'),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('seraphiel:window-state-changed', listener)

    return () => ipcRenderer.removeListener('seraphiel:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('seraphiel:focus-session', listener)

    return () => ipcRenderer.removeListener('seraphiel:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('seraphiel:notification-action', listener)

    return () => ipcRenderer.removeListener('seraphiel:notification-action', listener)
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
  // Soft gateway-mode apply finished tearing down the primary backend. Renderer
  // should wipe session lists + re-dial without a window reload.
  onConnectionApplied: callback => {
    const listener = () => callback()
    ipcRenderer.on('seraphiel:connection:applied', listener)

    return () => ipcRenderer.removeListener('seraphiel:connection:applied', listener)
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
  // runner in main.ts (apps/desktop/electron/bootstrap-runner.ts).
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
  getRemoteDisplayReason: () => ipcRenderer.invoke('seraphiel:get-remote-display-reason'),
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

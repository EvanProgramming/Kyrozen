/**
 * Auto-update logic for the Kyrozen desktop client.
 *
 * electron-updater works out of the box on Windows and on signed macOS apps.
 * Because the project does not currently have an Apple Developer certificate,
 * macOS updates are handled by notifying the user and opening the download page
 * instead of performing a silent update.
 */

import { dialog, shell } from 'electron';
import { autoUpdater, UpdateInfo } from 'electron-updater';

let updateCheckTimer: NodeJS.Timeout | null = null;
let mainWindowReference: Electron.BrowserWindow | null = null;

const UPDATE_INTERVAL_MS = 60 * 60 * 1000; // 1 hour

function sendUpdateStatus(status: string, message: string, payload?: Record<string, unknown>) {
  mainWindowReference?.webContents.send('kyrozen:update-status', {
    status,
    message,
    ...payload,
  });
}

export function initAutoUpdater(mainWindow: Electron.BrowserWindow): void {
  mainWindowReference = mainWindow;

  // In development we do not want the updater to run (there is no packaged app).
  if (process.env.NODE_ENV === 'development') {
    return;
  }

  // macOS requires code signing for silent auto-updates. Without a valid Apple
  // Developer certificate we only notify the user and let them download the
  // update manually. Windows and Linux use the normal silent update flow.
  const isMacOS = process.platform === 'darwin';
  const canAutoUpdate = !isMacOS;

  autoUpdater.autoDownload = canAutoUpdate;
  autoUpdater.autoInstallOnAppQuit = canAutoUpdate;

  autoUpdater.on('checking-for-update', () => {
    sendUpdateStatus('checking', '正在检查更新...');
  });

  autoUpdater.on('update-available', (info: UpdateInfo) => {
    sendUpdateStatus('available', `发现新版本 ${info.version}`, { version: info.version });
    if (!canAutoUpdate) {
      dialog
        .showMessageBox(mainWindow, {
          type: 'info',
          buttons: ['下载更新', '稍后'],
          defaultId: 0,
          cancelId: 1,
          title: 'Kyrozen 更新',
          message: `新版本 ${info.version} 已发布`,
          detail: '当前 macOS 客户端未签名，无法自动更新。点击下载后请手动替换应用。',
        })
        .then((result) => {
          if (result.response === 0) {
            const url = info.releaseName || `https://github.com/kyrozen/kyrozen/releases/tag/v${info.version}`;
            shell.openExternal(url);
          }
        })
        .catch(() => {
          // ignore
        });
    }
  });

  autoUpdater.on('update-not-available', (info: UpdateInfo) => {
    sendUpdateStatus('not-available', `当前已是最新版本 (${info.version})`, { version: info.version });
  });

  autoUpdater.on('download-progress', (progress) => {
    sendUpdateStatus('downloading', `正在下载更新 ${Math.round(progress.percent)}%`, {
      percent: progress.percent,
      transferred: progress.transferred,
      total: progress.total,
    });
  });

  autoUpdater.on('update-downloaded', (info: UpdateInfo) => {
    sendUpdateStatus('downloaded', `更新 ${info.version} 已下载，将在退出时安装`, { version: info.version });
    dialog
      .showMessageBox(mainWindow, {
        type: 'info',
        buttons: ['立即重启', '稍后'],
        defaultId: 0,
        cancelId: 1,
        title: 'Kyrozen 更新',
        message: `新版本 ${info.version} 已下载`,
        detail: '立即重启以应用更新，或稍后手动重启。',
      })
      .then((result) => {
        if (result.response === 0) {
          autoUpdater.quitAndInstall();
        }
      })
      .catch(() => {
        // ignore
      });
  });

  autoUpdater.on('error', (err) => {
    sendUpdateStatus('error', `检查更新失败: ${err.message}`, { message: err.message });
  });

  // Check once at startup and then periodically.
  void checkForUpdates();
  updateCheckTimer = setInterval(() => {
    void checkForUpdates();
  }, UPDATE_INTERVAL_MS);
}

export async function checkForUpdates(): Promise<void> {
  if (process.env.NODE_ENV === 'development') {
    return;
  }
  try {
    await autoUpdater.checkForUpdatesAndNotify();
  } catch {
    // Failures are surfaced via the 'error' event above.
  }
}

export function stopUpdateChecks(): void {
  if (updateCheckTimer) {
    clearInterval(updateCheckTimer);
    updateCheckTimer = null;
  }
}

/**
 * Configure the updater feed URL at runtime.
 * Useful when the update server is different from the default electron-builder
 * feed (e.g. a self-hosted update endpoint).
 */
export function setUpdateFeedURL(feedUrl: string): void {
  autoUpdater.setFeedURL(feedUrl);
}

/**
 * Return the canonical update metadata filename for the current platform.
 */
export function getUpdateMetaFilename(): string {
  const platform = process.platform;
  const arch = process.arch;
  if (platform === 'win32') return 'latest.yml';
  if (platform === 'darwin') return `latest-mac.yml`;
  return `latest-linux-${arch}.yml`;
}

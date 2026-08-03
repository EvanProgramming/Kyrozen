/**
 * Auto-update logic for the Kyrozen desktop client.
 *
 * electron-updater works out of the box on Windows and on signed macOS apps.
 * Because the project does not currently have an Apple Developer certificate,
 * macOS updates are handled by notifying the user and opening the download page
 * instead of performing a silent update.
 */

import { app, dialog, shell } from 'electron';
import { autoUpdater, UpdateDownloadedEvent, UpdateInfo } from 'electron-updater';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { spawnSync } from 'child_process';
import { UPDATE_PUBLIC_KEY } from './updatePublicKey';

let updateCheckTimer: NodeJS.Timeout | null = null;
let mainWindowReference: Electron.BrowserWindow | null = null;
let updateApiBaseUrl: string | null = null;

const UPDATE_INTERVAL_MS = 60 * 60 * 1000; // 1 hour

function hasTrustedMacSignature(): boolean {
  if (process.platform !== 'darwin' || !app.isPackaged) return false;
  const result = spawnSync('/usr/bin/codesign', ['-dv', '--verbose=4', app.getPath('exe')], { encoding: 'utf-8' });
  const output = `${result.stdout || ''}\n${result.stderr || ''}`;
  const team = output.match(/TeamIdentifier=([^\s]+)/)?.[1];
  return result.status === 0 && !!team && team !== 'not';
}

function sendUpdateStatus(status: string, message: string, payload?: Record<string, unknown>) {
  mainWindowReference?.webContents.send('kyrozen:update-status', {
    status,
    message,
    ...payload,
  });
}

function sha512File(filePath: string): string {
  const hash = crypto.createHash('sha512');
  hash.update(fs.readFileSync(filePath));
  return hash.digest('base64');
}

async function fetchSignature(version: string, filename: string): Promise<{ sha512: string; signature: string } | null> {
  if (!updateApiBaseUrl) return null;
  const url = new URL('/api/desktop/updates/signatures', updateApiBaseUrl);
  url.searchParams.set('version', version);
  url.searchParams.set('filename', filename);
  try {
    const response = await fetch(url.toString());
    if (!response.ok) return null;
    const data = (await response.json()) as { sha512?: string; signature?: string };
    if (!data.sha512 || !data.signature) return null;
    return { sha512: data.sha512, signature: data.signature };
  } catch {
    return null;
  }
}

function verifySignature(fileHash: string, signatureBase64: string): boolean {
  try {
    const verifier = crypto.createVerify('RSA-SHA512');
    verifier.update(fileHash);
    verifier.end();
    return verifier.verify(UPDATE_PUBLIC_KEY, signatureBase64, 'base64');
  } catch {
    return false;
  }
}

async function verifyDownloadedUpdate(event: UpdateDownloadedEvent): Promise<boolean> {
  if (!updateApiBaseUrl) {
    // Without an API base URL we cannot verify the signature; allow the update
    // but log a warning. This keeps standalone/offline builds functional.
    sendUpdateStatus('warning', '未配置更新签名服务器，跳过签名验证');
    return true;
  }

  const filename = path.basename(event.downloadedFile);
  sendUpdateStatus('verifying', `正在验证 ${filename} 的签名...`, { version: event.version });

  const fileHash = sha512File(event.downloadedFile);
  const signatureInfo = await fetchSignature(event.version, filename);

  if (!signatureInfo) {
    sendUpdateStatus('error', '无法获取更新包签名信息，安装已中止', { version: event.version });
    return false;
  }

  if (fileHash !== signatureInfo.sha512) {
    sendUpdateStatus('error', '更新包哈希校验失败，安装已中止', { version: event.version });
    return false;
  }

  if (!verifySignature(fileHash, signatureInfo.signature)) {
    sendUpdateStatus('error', '更新包签名验证失败，安装已中止', { version: event.version });
    return false;
  }

  sendUpdateStatus('verified', '更新包签名验证通过', { version: event.version });
  return true;
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
  const canAutoUpdate = !isMacOS || hasTrustedMacSignature();

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
            const url = `https://github.com/EvanProgramming/Kyrozen/releases/tag/v${info.version}`;
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

  autoUpdater.on('update-downloaded', async (event: UpdateDownloadedEvent) => {
    const verified = await verifyDownloadedUpdate(event);
    if (!verified) {
      // Prevent silent installation on quit if verification failed.
      autoUpdater.autoInstallOnAppQuit = false;
      try {
        fs.unlinkSync(event.downloadedFile);
      } catch {
        // ignore cleanup errors
      }
      dialog
        .showMessageBox(mainWindow, {
          type: 'warning',
          buttons: ['确定'],
          defaultId: 0,
          title: 'Kyrozen 更新',
          message: `更新 ${event.version} 签名验证失败`,
          detail: '已中止安装，请稍后再试或访问官网手动下载。',
        })
        .catch(() => {
          // ignore
        });
      return;
    }

    sendUpdateStatus('downloaded', `更新 ${event.version} 已下载并验证，将在退出时安装`, { version: event.version });
    dialog
      .showMessageBox(mainWindow, {
        type: 'info',
        buttons: ['立即重启', '稍后'],
        defaultId: 0,
        cancelId: 1,
        title: 'Kyrozen 更新',
        message: `新版本 ${event.version} 已下载`,
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
    // Beta releases are intentionally marked as prerelease. GitHub's
    // /releases/latest endpoint returns 406 when there is no stable release;
    // this is an expected state, not a user-facing error.
    const msg = err.message || '';
    if (/no published versions|no releases|No published|Unable to find latest version|\b406\b|releases\/latest/i.test(msg)) {
      // A prerelease-only repository has no stable feed by design. Keep the
      // startup surface quiet; users can still download a newer beta manually.
      sendUpdateStatus('up-to-date', '');
    } else {
      sendUpdateStatus('error', `检查更新失败: ${msg}`, { message: msg });
    }
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
 * Set the API base URL used to fetch update signatures.
 * This is separate from the updater feed URL so GitHub releases can still be
 * used for downloads while the Kyrozen backend provides signatures.
 */
export function setUpdateApiBaseUrl(baseUrl: string): void {
  updateApiBaseUrl = baseUrl.replace(/\/$/, '');
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

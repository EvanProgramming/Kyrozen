/**
 * Register the Kyrozen native messaging host manifest with supported browsers.
 *
 * Chrome / Edge / Firefox read a JSON manifest from a well-known directory that
 * points to the host executable. This module writes those manifests at runtime
 * so the browser extension can connect to the desktop client without manual
 * installation steps.
 */

import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { app } from 'electron';

const HOST_NAME = 'com.kyrozen.desktop';

function getBrowserNativeMessagingDirs(): string[] {
  const platform = os.platform();
  const home = os.homedir();
  if (platform === 'darwin') {
    return [
      path.join(home, 'Library/Application Support/Google/Chrome/NativeMessagingHosts'),
      path.join(home, 'Library/Application Support/Microsoft Edge/NativeMessagingHosts'),
      path.join(home, 'Library/Application Support/Mozilla/NativeMessagingHosts'),
    ];
  }
  if (platform === 'win32') {
    // On Windows the manifest path is read from the registry. We return the
    // directory where the manifest and host binary should live so callers can
    // also write the registry keys if they have permission.
    const localAppData = process.env.LOCALAPPDATA || path.join(home, 'AppData/Local');
    return [path.join(localAppData, 'Kyrozen/NativeMessagingHost')];
  }
  return [
    path.join(home, '.config/google-chrome/NativeMessagingHosts'),
    path.join(home, '.config/microsoft-edge/NativeMessagingHosts'),
    path.join(home, '.mozilla/native-messaging-hosts'),
  ];
}

function getHostExecutablePath(): string {
  if (app.isPackaged) {
    // electron-builder extraResources places the host at <app>/Contents/Resources/native-messaging-host/
    return path.join(process.resourcesPath, 'native-messaging-host', 'nativeMessagingHost.js');
  }
  // Development: use the vite build output directory relative to the repo.
  return path.resolve(process.cwd(), 'dist-electron/native-messaging-host/nativeMessagingHost.js');
}

interface HostManifest {
  name: string;
  description: string;
  path: string;
  type: 'stdio';
  allowed_origins?: string[];
  allowed_extensions?: string[];
}

function buildChromeManifest(hostPath: string, extensionIds: string[]): HostManifest {
  return {
    name: HOST_NAME,
    description: 'Kyrozen Desktop Native Messaging Host',
    path: hostPath,
    type: 'stdio',
    allowed_origins: extensionIds.map((id) => `chrome-extension://${id}/`),
  };
}

function buildFirefoxManifest(hostPath: string, extensionIds: string[]): HostManifest {
  return {
    name: HOST_NAME,
    description: 'Kyrozen Desktop Native Messaging Host',
    path: hostPath,
    type: 'stdio',
    allowed_extensions: extensionIds,
  };
}

/**
 * Register the native messaging host manifest for all supported browsers.
 *
 * @param extensionIds Chrome extension IDs or Firefox extension IDs allowed to
 *   connect to the host. In production these should match the published extension.
 */
export async function registerNativeMessagingHost(extensionIds: string[]): Promise<void> {
  if (!extensionIds.length) return;
  const hostPath = getHostExecutablePath();
  const chromeManifest = buildChromeManifest(hostPath, extensionIds);
  const firefoxManifest = buildFirefoxManifest(hostPath, extensionIds);

  for (const dir of getBrowserNativeMessagingDirs()) {
    try {
      await fs.mkdir(dir, { recursive: true });
      if (dir.includes('Mozilla') || dir.includes('mozilla')) {
        await fs.writeFile(path.join(dir, `${HOST_NAME}.json`), JSON.stringify(firefoxManifest, null, 2));
      } else {
        await fs.writeFile(path.join(dir, `${HOST_NAME}.json`), JSON.stringify(chromeManifest, null, 2));
      }
    } catch (err) {
      // Registration is best-effort; browsers where the user denied permission
      // will simply fall back to the localhost HTTP bridge.
      console.warn(`Failed to register native messaging host in ${dir}:`, err);
    }
  }
}

#!/usr/bin/env node
/**
 * Post-install hook for the Kyrozen desktop client.
 *
 * macOS Gatekeeper / XProtect frequently quarantines the downloaded Electron
 * binary as "malware". This script removes the quarantine attribute and applies
 * an ad-hoc signature so development builds can run locally.
 */

import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

if (os.platform() !== 'darwin') {
  process.exit(0);
}

const electronApp = path.resolve(
  'node_modules/electron/dist/Electron.app'
);

if (!existsSync(electronApp)) {
  console.log('[postinstall] Electron.app not found, skipping macOS quarantine fix.');
  process.exit(0);
}

try {
  console.log('[postinstall] Removing macOS quarantine attribute from Electron.app...');
  execSync(`xattr -dr com.apple.quarantine "${electronApp}"`, { stdio: 'inherit' });
  console.log('[postinstall] Re-signing Electron.app ad-hoc...');
  execSync(`codesign --force --deep --sign - "${electronApp}"`, { stdio: 'inherit' });
  console.log('[postinstall] Done.');
} catch (err) {
  console.error('[postinstall] Failed to fix Electron.app:', err.message);
  process.exit(0); // Do not fail npm install because of this.
}

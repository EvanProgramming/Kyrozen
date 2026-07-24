/**
 * Hardware toolchain management for the Kyrozen desktop client.
 *
 * The desktop client is responsible for making ``arduino-cli`` and
 * ``platformio`` available to the local Python Agent. This module can either
 * reuse tools already installed on the system or download/install portable
 * versions into the client's userData directory.
 */

import { app } from 'electron';
import fs from 'fs/promises';
import https from 'https';
import path from 'path';
import { spawn } from 'child_process';

const ARDUINO_CLI_VERSION = '1.0.4';

interface ToolInfo {
  command: string;
  path: string | null;
  bundled: boolean;
  version: string | null;
}

const tools: Map<string, ToolInfo> = new Map();
let pythonExePath: string | null = null;

export function setPythonExe(pythonPath: string): void {
  pythonExePath = pythonPath;
}

function getToolchainBaseDir(): string {
  return path.join(app.getPath('userData'), 'hardware-toolchain');
}

function httpsGet(url: string): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    https
      .get(url, (res) => {
        if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          httpsGet(res.headers.location).then(resolve).catch(reject);
          return;
        }
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        const chunks: Buffer[] = [];
        res.on('data', (chunk) => chunks.push(chunk));
        res.on('end', () => resolve(Buffer.concat(chunks)));
        res.on('error', reject);
      })
      .on('error', reject);
  });
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function runCommand(exe: string, args: string[], cwd?: string): Promise<{ stdout: string; stderr: string; code: number | null }> {
  return new Promise((resolve) => {
    const child = spawn(exe, args, { cwd, shell: false });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (data) => {
      stdout += data.toString();
    });
    child.stderr.on('data', (data) => {
      stderr += data.toString();
    });
    child.on('close', (code) => {
      resolve({ stdout, stderr, code });
    });
    child.on('error', (err) => {
      resolve({ stdout, stderr: err.message, code: -1 });
    });
  });
}

async function which(command: string): Promise<string | null> {
  const shell = process.platform === 'win32' ? 'where' : 'which';
  const result = await runCommand(shell, [command]);
  if (result.code === 0) {
    return result.stdout.split('\n')[0].trim();
  }
  return null;
}

function getArduinoReleaseInfo():
  | { url: string; filename: string; extractedName: string }
  | null {
  const platform = process.platform;
  const arch = process.arch;
  const base = `https://github.com/arduino/arduino-cli/releases/download/v${ARDUINO_CLI_VERSION}`;
  if (platform === 'win32') {
    return {
      url: `${base}/arduino-cli_${ARDUINO_CLI_VERSION}_Windows_64bit.zip`,
      filename: 'arduino-cli.zip',
      extractedName: 'arduino-cli.exe',
    };
  }
  if (platform === 'darwin') {
    const macArch = arch === 'arm64' ? 'ARM64' : '64bit';
    return {
      url: `${base}/arduino-cli_${ARDUINO_CLI_VERSION}_macOS_${macArch}.tar.gz`,
      filename: 'arduino-cli.tar.gz',
      extractedName: 'arduino-cli',
    };
  }
  if (platform === 'linux') {
    const linuxArch = arch === 'arm64' ? 'ARM64' : '64bit';
    return {
      url: `${base}/arduino-cli_${ARDUINO_CLI_VERSION}_Linux_${linuxArch}.tar.gz`,
      filename: 'arduino-cli.tar.gz',
      extractedName: 'arduino-cli',
    };
  }
  return null;
}

async function extractArchive(archivePath: string, outDir: string): Promise<void> {
  await fs.mkdir(outDir, { recursive: true });
  if (archivePath.endsWith('.zip')) {
    await runCommand('powershell', ['-Command', `Expand-Archive -Path "${archivePath}" -DestinationPath "${outDir}" -Force`]);
  } else {
    // tar.gz
    await runCommand('tar', ['-xzf', archivePath, '-C', outDir]);
  }
}

/**
 * Ensure arduino-cli is available. Prefer a system install, otherwise download
 * a portable version into the client's userData directory.
 */
export async function ensureArduinoCLI(onProgress?: (message: string) => void): Promise<ToolInfo> {
  const cached = tools.get('arduino-cli');
  if (cached) return cached;

  const systemPath = await which('arduino-cli');
  if (systemPath) {
    const info: ToolInfo = { command: 'arduino-cli', path: systemPath, bundled: false, version: null };
    const versionResult = await runCommand(systemPath, ['version']);
    info.version = versionResult.stdout.split('\n')[0].trim();
    tools.set('arduino-cli', info);
    return info;
  }

  onProgress?.('Arduino CLI not found, downloading bundled version...');
  const release = getArduinoReleaseInfo();
  if (!release) {
    throw new Error(`Unsupported platform ${process.platform} for bundled Arduino CLI`);
  }

  const baseDir = path.join(getToolchainBaseDir(), 'arduino-cli');
  const archivePath = path.join(baseDir, release.filename);
  const exePath = path.join(baseDir, release.extractedName);

  if (await fileExists(exePath)) {
    const info: ToolInfo = { command: 'arduino-cli', path: exePath, bundled: true, version: null };
    const versionResult = await runCommand(exePath, ['version']);
    info.version = versionResult.stdout.split('\n')[0].trim();
    tools.set('arduino-cli', info);
    return info;
  }

  await fs.mkdir(baseDir, { recursive: true });
  onProgress?.(`Downloading Arduino CLI ${ARDUINO_CLI_VERSION}...`);
  const data = await httpsGet(release.url);
  await fs.writeFile(archivePath, data);
  onProgress?.('Extracting Arduino CLI...');
  await extractArchive(archivePath, baseDir);

  if (process.platform !== 'win32') {
    await fs.chmod(exePath, 0o755);
  }

  const info: ToolInfo = { command: 'arduino-cli', path: exePath, bundled: true, version: null };
  const versionResult = await runCommand(exePath, ['version']);
  info.version = versionResult.stdout.split('\n')[0].trim();
  tools.set('arduino-cli', info);
  onProgress?.(`Arduino CLI ready: ${info.version}`);
  return info;
}

/**
 * Ensure PlatformIO Core is available. Prefer a system install, otherwise
 * install it into the bundled Python runtime.
 */
export async function ensurePlatformIO(onProgress?: (message: string) => void): Promise<ToolInfo> {
  const cached = tools.get('pio');
  if (cached) return cached;

  const systemPath = await which('pio');
  if (systemPath) {
    const info: ToolInfo = { command: 'pio', path: systemPath, bundled: false, version: null };
    const versionResult = await runCommand(systemPath, ['--version']);
    info.version = versionResult.stdout.split('\n')[0].trim();
    tools.set('pio', info);
    return info;
  }

  if (!pythonExePath) {
    throw new Error('Bundled Python runtime is required to install PlatformIO');
  }

  onProgress?.('PlatformIO not found, installing into bundled Python...');
  const result = await runCommand(pythonExePath, ['-m', 'pip', 'install', '-q', 'platformio']);
  if (result.code !== 0) {
    throw new Error(`Failed to install PlatformIO: ${result.stderr}`);
  }

  // Find the newly installed pio executable next to the Python binary.
  const pythonDir = path.dirname(pythonExePath);
  const possibleNames = process.platform === 'win32' ? ['pio.exe'] : ['pio'];
  const possibleDirs = process.platform === 'win32' ? ['Scripts'] : ['bin'];
  let pioPath: string | null = null;
  for (const dir of possibleDirs) {
    for (const name of possibleNames) {
      const candidate = path.join(pythonDir, '..', dir, name);
      if (await fileExists(candidate)) {
        pioPath = path.resolve(candidate);
        break;
      }
    }
    if (pioPath) break;
  }

  if (!pioPath) {
    throw new Error('PlatformIO installed but pio executable not found');
  }

  const info: ToolInfo = { command: 'pio', path: pioPath, bundled: true, version: null };
  const versionResult = await runCommand(pioPath, ['--version']);
  info.version = versionResult.stdout.split('\n')[0].trim();
  tools.set('pio', info);
  onProgress?.(`PlatformIO ready: ${info.version}`);
  return info;
}

/**
 * Install common Arduino board packages and PlatformIO platforms that the
 * Agent is likely to need. This reduces first-use latency.
 */
export async function installCommonCores(onProgress?: (message: string) => void): Promise<void> {
  try {
    const arduino = await ensureArduinoCLI(onProgress);
    onProgress?.('Installing common Arduino cores...');
    await runCommand(arduino.path!, ['core', 'install', 'arduino:esp32', 'arduino:avr']);
  } catch (err: any) {
    onProgress?.(`Could not install common Arduino cores: ${err.message || err}`);
  }

  try {
    const pio = await ensurePlatformIO(onProgress);
    onProgress?.('Installing common PlatformIO platforms...');
    await runCommand(pio.path!, ['platform', 'install', 'espressif32', 'atmelavr']);
  } catch (err: any) {
    onProgress?.(`Could not install common PlatformIO platforms: ${err.message || err}`);
  }
}

/**
 * Return the resolved filesystem path for a hardware command, or null if it
 * cannot be made available.
 */
export async function resolveHardwareCommand(command: string): Promise<string | null> {
  if (command === 'arduino-cli') {
    const info = await ensureArduinoCLI();
    return info.path;
  }
  if (command === 'pio') {
    const info = await ensurePlatformIO();
    return info.path;
  }
  return which(command);
}

export function getToolStatus(): Record<string, ToolInfo> {
  return Object.fromEntries(tools.entries());
}

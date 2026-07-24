import { app } from 'electron';
import fs from 'fs/promises';
import path from 'path';
import { spawn } from 'child_process';
import { createWriteStream } from 'fs';
import https from 'https';

const PYTHON_VERSION = '3.12.4';
const RELEASE_TAG = '20240713';

interface RuntimeInfo {
  pythonExe: string;
  version: string;
  ready: boolean;
}

function getReleaseUrl(): { url: string; filename: string } | null {
  const platform = process.platform;
  const arch = process.arch;

  const builds: Record<string, Record<string, string>> = {
    darwin: {
      arm64: `cpython-${PYTHON_VERSION}+${RELEASE_TAG}-aarch64-apple-darwin-install_only.tar.gz`,
      x64: `cpython-${PYTHON_VERSION}+${RELEASE_TAG}-x86_64-apple-darwin-install_only.tar.gz`,
    },
    win32: {
      x64: `cpython-${PYTHON_VERSION}+${RELEASE_TAG}-x86_64-pc-windows-msvc-install_only.tar.gz`,
    },
    linux: {
      x64: `cpython-${PYTHON_VERSION}+${RELEASE_TAG}-x86_64-unknown-linux-gnu-install_only.tar.gz`,
    },
  };

  const filename = builds[platform]?.[arch];
  if (!filename) return null;

  return {
    url: `https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE_TAG}/${filename}`,
    filename,
  };
}

function getRuntimeBaseDir(): string {
  return path.join(app.getPath('userData'), 'python-runtime');
}

function getMarkerPath(): string {
  return path.join(getRuntimeBaseDir(), 'runtime.json');
}

async function getPythonExecutable(extractDir: string): Promise<string | null> {
  const candidates: string[] = [];
  if (process.platform === 'win32') {
    candidates.push(path.join(extractDir, 'python', 'python.exe'));
    candidates.push(path.join(extractDir, 'python', 'install', 'python.exe'));
  } else {
    candidates.push(path.join(extractDir, 'python', 'bin', `python${PYTHON_VERSION.split('.').slice(0, 2).join('.')}`));
    candidates.push(path.join(extractDir, 'python', 'bin', 'python3'));
    candidates.push(path.join(extractDir, 'python', 'bin', `python${PYTHON_VERSION}`));
  }
  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      return candidate;
    } catch {
      // continue searching
    }
  }
  return null;
}

async function downloadFile(url: string, dest: string, onProgress?: (percent: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const file = createWriteStream(dest);
    https
      .get(url, { timeout: 120_000 }, (response) => {
        if (response.statusCode && response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
          file.close();
          void downloadFile(response.headers.location, dest, onProgress).then(resolve).catch(reject);
          return;
        }
        if (response.statusCode !== 200) {
          file.close();
          reject(new Error(`Download failed: HTTP ${response.statusCode}`));
          return;
        }

        const total = parseInt(response.headers['content-length'] || '0', 10);
        let downloaded = 0;
        response.on('data', (chunk: Buffer) => {
          downloaded += chunk.length;
          if (total && onProgress) {
            onProgress(Math.round((downloaded / total) * 100));
          }
        });
        response.pipe(file);
        file.on('finish', () => {
          file.close();
          resolve();
        });
      })
      .on('error', (err) => {
        file.close();
        reject(err);
      });
  });
}

async function extractTarball(tarPath: string, extractDir: string): Promise<void> {
  await fs.mkdir(extractDir, { recursive: true });
  return new Promise((resolve, reject) => {
    const child = spawn('tar', ['-xzf', tarPath, '-C', extractDir], { stdio: 'ignore' });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`tar exited with code ${code}`));
    });
  });
}

async function runCommand(
  exe: string,
  args: string[],
  options?: { cwd?: string; env?: NodeJS.ProcessEnv },
): Promise<{ code: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    let stdout = '';
    let stderr = '';
    const child = spawn(exe, args, {
      ...options,
      env: { ...process.env, ...options?.env },
    });
    child.stdout?.on('data', (d) => {
      stdout += d.toString();
    });
    child.stderr?.on('data', (d) => {
      stderr += d.toString();
    });
    child.on('close', (code) => resolve({ code, stdout, stderr }));
  });
}

async function installDependencies(pythonExe: string, repoRoot: string): Promise<void> {
  const requirementsPath = path.join(repoRoot, 'requirements.txt');
  try {
    await fs.access(requirementsPath);
  } catch {
    return;
  }

  const pipInstall = await runCommand(pythonExe, ['-m', 'pip', 'install', '--upgrade', 'pip']);
  if (pipInstall.code !== 0) {
    throw new Error(`Failed to upgrade pip: ${pipInstall.stderr}`);
  }

  const deps = await runCommand(pythonExe, ['-m', 'pip', 'install', '-r', requirementsPath]);
  if (deps.code !== 0) {
    throw new Error(`Failed to install dependencies: ${deps.stderr}`);
  }
}

async function verifyPython(pythonExe: string): Promise<string> {
  const result = await runCommand(pythonExe, ['--version']);
  if (result.code !== 0 || !result.stdout.includes('Python')) {
    throw new Error(`Python verification failed: ${result.stderr || result.stdout}`);
  }
  return result.stdout.trim() || result.stderr.trim();
}

/**
 * Ensure a local portable Python runtime is available.
 *
 * On first launch this downloads a python-build-standalone distribution,
 * extracts it, installs requirements.txt, and verifies it works. Subsequent
 * launches reuse the cached runtime.
 *
 * Returns the path to the python executable, or null if a portable runtime
 * cannot be provisioned (callers should fall back to the system python3).
 */
export async function ensurePythonRuntime(
  repoRoot: string,
  onProgress?: (message: string) => void,
): Promise<string | null> {
  const release = getReleaseUrl();
  if (!release) {
    onProgress?.('Unsupported platform/architecture for bundled Python');
    return null;
  }

  const baseDir = getRuntimeBaseDir();
  const extractDir = path.join(baseDir, 'extracted');
  const markerPath = getMarkerPath();

  // Reuse cached runtime if marker exists.
  try {
    const markerRaw = await fs.readFile(markerPath, 'utf-8');
    const marker: RuntimeInfo = JSON.parse(markerRaw);
    if (marker.ready && marker.pythonExe) {
      await fs.access(marker.pythonExe);
      return marker.pythonExe;
    }
  } catch {
    // ignore missing or invalid marker
  }

  onProgress?.(`Downloading Python ${PYTHON_VERSION}...`);
  await fs.mkdir(baseDir, { recursive: true });
  const tarPath = path.join(baseDir, release.filename);

  try {
    await fs.access(tarPath);
  } catch {
    await downloadFile(release.url, tarPath, (percent) => {
      onProgress?.(`Downloading Python ${PYTHON_VERSION}... ${percent}%`);
    });
  }

  // Basic integrity check: file must be non-empty and look like a tarball.
  const stats = await fs.stat(tarPath);
  if (stats.size < 1_000_000) {
    throw new Error('Downloaded Python archive is unexpectedly small');
  }

  onProgress?.('Extracting Python runtime...');
  await extractTarball(tarPath, extractDir);

  const pythonExe = await getPythonExecutable(extractDir);
  if (!pythonExe) {
    throw new Error('Could not locate Python executable after extraction');
  }

  onProgress?.('Verifying Python runtime...');
  const version = await verifyPython(pythonExe);

  onProgress?.('Installing Python dependencies...');
  await installDependencies(pythonExe, repoRoot);

  const info: RuntimeInfo = {
    pythonExe,
    version,
    ready: true,
  };
  await fs.writeFile(markerPath, JSON.stringify(info, null, 2));
  onProgress?.(`Python runtime ready: ${version}`);
  return pythonExe;
}

/**
 * Return the cached portable Python executable if available, otherwise null.
 */
export async function getCachedPythonRuntime(): Promise<string | null> {
  try {
    const markerPath = getMarkerPath();
    const markerRaw = await fs.readFile(markerPath, 'utf-8');
    const marker: RuntimeInfo = JSON.parse(markerRaw);
    if (marker.ready && marker.pythonExe) {
      await fs.access(marker.pythonExe);
      return marker.pythonExe;
    }
  } catch {
    // ignore
  }
  return null;
}

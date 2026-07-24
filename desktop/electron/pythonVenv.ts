import fs from 'fs/promises';
import path from 'path';
import { spawn } from 'child_process';

interface VenvInfo {
  pythonPath: string;
  createdAt: string;
  pythonVersion: string;
}

export function getProjectVenvRoot(projectRoot: string): string {
  return path.join(projectRoot, '.kyrozen', 'venv');
}

export function getVenvPython(projectRoot: string): string {
  const venvRoot = getProjectVenvRoot(projectRoot);
  if (process.platform === 'win32') {
    return path.join(venvRoot, 'Scripts', 'python.exe');
  }
  return path.join(venvRoot, 'bin', 'python');
}

function getMarkerPath(projectRoot: string): string {
  return path.join(getProjectVenvRoot(projectRoot), 'kyrozen-venv.json');
}

async function venvExists(projectRoot: string): Promise<boolean> {
  try {
    const marker = await fs.readFile(getMarkerPath(projectRoot), 'utf-8');
    const info: VenvInfo = JSON.parse(marker);
    await fs.access(info.pythonPath);
    return true;
  } catch {
    return false;
  }
}

function runCommand(
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

async function getPythonVersion(pythonExe: string): Promise<string> {
  const result = await runCommand(pythonExe, ['--version']);
  if (result.code !== 0) {
    throw new Error(`Failed to get Python version: ${result.stderr || result.stdout}`);
  }
  return (result.stdout.trim() || result.stderr.trim()).replace(/^Python\s+/, '');
}

/**
 * Ensure a project-level virtual environment exists at <projectRoot>/.kyrozen/venv.
 *
 * Uses the provided base Python interpreter to create the venv. On subsequent
 * calls the existing venv is reused.
 */
export async function ensureProjectVenv(
  projectRoot: string,
  basePython: string,
  onProgress?: (message: string) => void,
): Promise<{ pythonPath: string; created: boolean; error?: string }> {
  const venvRoot = getProjectVenvRoot(projectRoot);
  const pythonPath = getVenvPython(projectRoot);

  if (await venvExists(projectRoot)) {
    return { pythonPath, created: false };
  }

  onProgress?.('Creating project virtual environment...');
  await fs.mkdir(venvRoot, { recursive: true });
  const create = await runCommand(basePython, ['-m', 'venv', venvRoot]);
  if (create.code !== 0) {
    return { pythonPath, created: false, error: `venv creation failed: ${create.stderr}` };
  }

  onProgress?.('Upgrading venv pip...');
  const pipUpgrade = await runCommand(pythonPath, ['-m', 'pip', 'install', '--upgrade', 'pip']);
  if (pipUpgrade.code !== 0) {
    return { pythonPath, created: false, error: `pip upgrade failed: ${pipUpgrade.stderr}` };
  }

  const info: VenvInfo = {
    pythonPath,
    createdAt: new Date().toISOString(),
    pythonVersion: await getPythonVersion(pythonPath),
  };
  await fs.writeFile(getMarkerPath(projectRoot), JSON.stringify(info, null, 2));

  onProgress?.(`Project venv ready: ${info.pythonVersion}`);
  return { pythonPath, created: true };
}

/**
 * Install dependencies into the project venv.
 *
 * If no packages are provided and a requirements.txt exists in the project
 * root, it is installed automatically.
 */
export async function installProjectDependencies(
  projectRoot: string,
  packages?: string[],
  onProgress?: (message: string) => void,
): Promise<{ success: boolean; installed: string[]; error?: string }> {
  const pythonPath = getVenvPython(projectRoot);
  try {
    await fs.access(pythonPath);
  } catch {
    return { success: false, installed: [], error: 'Project venv not found' };
  }

  const targets: string[] = [];
  if (packages && packages.length > 0) {
    targets.push(...packages);
  } else {
    const requirementsPath = path.join(projectRoot, 'requirements.txt');
    try {
      await fs.access(requirementsPath);
      targets.push('-r', requirementsPath);
    } catch {
      return { success: true, installed: [] };
    }
  }

  onProgress?.(`Installing dependencies: ${targets.join(' ')}`);
  const result = await runCommand(pythonPath, ['-m', 'pip', 'install', ...targets]);
  if (result.code !== 0) {
    return { success: false, installed: targets, error: result.stderr || result.stdout };
  }
  return { success: true, installed: targets };
}

/**
 * Return the project venv interpreter path if it exists.
 */
export async function getProjectVenv(projectRoot: string): Promise<{ ready: boolean; pythonPath: string | null }> {
  const pythonPath = getVenvPython(projectRoot);
  if (await venvExists(projectRoot)) {
    return { ready: true, pythonPath };
  }
  return { ready: false, pythonPath: null };
}

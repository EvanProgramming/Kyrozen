/**
 * Project-level Git helpers used by the desktop client.
 *
 * All operations target the workspace root of the current project. Credentials
 * are not persisted locally; the GitHub access token is fetched from the
 * backend on demand.
 */

import * as fs from 'fs/promises';
import * as path from 'path';
import simpleGit, { SimpleGit } from 'simple-git';

interface GitConfig {
  autoCommit: boolean;
  remoteUrl?: string;
}

const AUTO_COMMIT_FILE = '.kyrozen';
const CONFIG_NAME = 'git-config.json';

function getConfigPath(workspaceRoot: string): string {
  return path.join(workspaceRoot, AUTO_COMMIT_FILE, CONFIG_NAME);
}

async function loadGitConfig(workspaceRoot: string): Promise<GitConfig> {
  try {
    const raw = await fs.readFile(getConfigPath(workspaceRoot), 'utf-8');
    const parsed = JSON.parse(raw) as Partial<GitConfig>;
    return { autoCommit: false, ...parsed };
  } catch {
    return { autoCommit: false };
  }
}

async function saveGitConfig(workspaceRoot: string, config: GitConfig): Promise<void> {
  await fs.mkdir(path.dirname(getConfigPath(workspaceRoot)), { recursive: true });
  await fs.writeFile(getConfigPath(workspaceRoot), JSON.stringify(config, null, 2));
}

function gitInstance(workspaceRoot: string): SimpleGit {
  return simpleGit(workspaceRoot);
}

async function ensureKyrozenGitignore(workspaceRoot: string): Promise<void> {
  const gitignore = path.join(workspaceRoot, '.gitignore');
  let content = '';
  try { content = await fs.readFile(gitignore, 'utf-8'); } catch { /* create below */ }
  const lines = content.split(/\r?\n/).map((line) => line.trim());
  const additions = ['.kyrozen/', '.env'].filter((entry) => !lines.includes(entry));
  if (additions.length === 0) return;
  const prefix = content && !content.endsWith('\n') ? '\n' : '';
  await fs.writeFile(gitignore, `${content}${prefix}${additions.join('\n')}\n`, 'utf-8');
}

export async function initGitRepo(workspaceRoot: string, remoteUrl?: string): Promise<{ success: boolean; error?: string }> {
  try {
    const git = gitInstance(workspaceRoot);
    const isRepo = await git.checkIsRepo();
    if (!isRepo) {
      await git.init(false, { '--initial-branch': 'main' });
    }
    await ensureKyrozenGitignore(workspaceRoot);
    const name = await git.getConfig('user.name', 'local');
    const email = await git.getConfig('user.email', 'local');
    if (!name.value) await git.addConfig('user.name', 'Kyrozen', false, 'local');
    if (!email.value) await git.addConfig('user.email', 'kyrozen@users.noreply.github.com', false, 'local');
    if (remoteUrl) {
      const remotes = await git.getRemotes(true);
      if (remotes.find((r) => r.name === 'origin')) {
        await git.remote(['set-url', 'origin', remoteUrl]);
      } else {
        await git.addRemote('origin', remoteUrl);
      }
    }
    return { success: true };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
}

export async function getGitStatus(workspaceRoot: string): Promise<{
  success: boolean;
  isRepo: boolean;
  branch?: string;
  ahead?: number;
  behind?: number;
  modified?: string[];
  untracked?: string[];
  error?: string;
}> {
  try {
    const git = gitInstance(workspaceRoot);
    const isRepo = await git.checkIsRepo();
    if (!isRepo) {
      return { success: true, isRepo: false };
    }
    const status = await git.status();
    return {
      success: true,
      isRepo: true,
      branch: status.current || undefined,
      ahead: status.ahead,
      behind: status.behind,
      modified: status.modified,
      untracked: status.not_added,
    };
  } catch (err: any) {
    return { success: false, isRepo: false, error: err.message || String(err) };
  }
}

export async function commitAndPush(
  workspaceRoot: string,
  token: string | null,
  message: string
): Promise<{ success: boolean; error?: string }> {
  try {
    const git = gitInstance(workspaceRoot);
    const isRepo = await git.checkIsRepo();
    if (!isRepo) {
      return { success: false, error: '工作区不是 Git 仓库，请先初始化' };
    }

    const config = await loadGitConfig(workspaceRoot);
    await git.add('-A');
    const status = await git.status();
    if (status.staged.length > 0 || status.modified.length > 0 || status.not_added.length > 0 || status.deleted.length > 0) {
      await git.commit(message);
    }

    const remotes = await git.getRemotes(true);
    const origin = remotes.find((r) => r.name === 'origin');
    if (!origin?.refs.fetch || !token) return { success: true };

    const authorization = Buffer.from(`x-access-token:${token}`).toString('base64');
    await git.raw([
      '-c', `http.extraHeader=Authorization: Basic ${authorization}`,
      'push', '--set-upstream', 'origin', status.current || 'main',
    ]);
    config.remoteUrl = origin.refs.fetch;
    await saveGitConfig(workspaceRoot, config);

    return { success: true };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
}

export async function setAutoCommit(workspaceRoot: string, enabled: boolean): Promise<{ success: boolean; error?: string }> {
  try {
    await ensureKyrozenGitignore(workspaceRoot);
    const config = await loadGitConfig(workspaceRoot);
    config.autoCommit = enabled;
    await saveGitConfig(workspaceRoot, config);
    return { success: true };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
}

export async function getAutoCommit(workspaceRoot: string): Promise<{ enabled: boolean }> {
  const config = await loadGitConfig(workspaceRoot);
  return { enabled: config.autoCommit };
}

/**
 * Called after file changes to optionally auto-commit. Best-effort: failures are
 * swallowed to avoid breaking the agent workflow.
 */
export async function maybeAutoCommit(workspaceRoot: string, token: string | null): Promise<void> {
  if (!token) return;
  const { enabled } = await getAutoCommit(workspaceRoot);
  if (!enabled) return;
  const now = new Date().toISOString();
  const result = await commitAndPush(workspaceRoot, token, `Kyrozen auto-commit at ${now}`);
  if (!result.success) {
    console.warn(`Auto-commit failed for ${workspaceRoot}: ${result.error}`);
  }
}

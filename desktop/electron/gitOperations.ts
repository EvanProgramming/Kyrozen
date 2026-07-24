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

function injectTokenIntoRemoteUrl(remoteUrl: string, token: string): string {
  // Convert https://github.com/user/repo.git -> https://TOKEN@github.com/user/repo.git
  const url = new URL(remoteUrl);
  url.username = token;
  url.password = '';
  return url.toString();
}

export async function initGitRepo(workspaceRoot: string, remoteUrl?: string): Promise<{ success: boolean; error?: string }> {
  try {
    const git = gitInstance(workspaceRoot);
    const isRepo = await git.checkIsRepo();
    if (!isRepo) {
      await git.init();
    }
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
  token: string,
  message: string
): Promise<{ success: boolean; error?: string }> {
  try {
    const git = gitInstance(workspaceRoot);
    const isRepo = await git.checkIsRepo();
    if (!isRepo) {
      return { success: false, error: '工作区不是 Git 仓库，请先初始化' };
    }

    const remotes = await git.getRemotes(true);
    const origin = remotes.find((r) => r.name === 'origin');
    if (!origin?.refs.fetch) {
      return { success: false, error: '未配置 origin 远程仓库' };
    }

    const config = await loadGitConfig(workspaceRoot);

    // Rewrite remote URL with token so push can authenticate.
    const authenticatedUrl = injectTokenIntoRemoteUrl(origin.refs.fetch, token);
    await git.remote(['set-url', 'origin', authenticatedUrl]);

    await git.add('.');
    const status = await git.status();
    if (status.staged.length === 0 && status.modified.length === 0 && status.not_added.length === 0) {
      // Nothing to commit; reset remote URL and return.
      await git.remote(['set-url', 'origin', origin.refs.fetch]);
      return { success: true };
    }

    await git.commit(message);
    await git.push('origin', status.current || 'main');

    // Restore remote URL without token to avoid leaking credentials in .git/config.
    await git.remote(['set-url', 'origin', origin.refs.fetch]);

    config.remoteUrl = origin.refs.fetch;
    await saveGitConfig(workspaceRoot, config);

    return { success: true };
  } catch (err: any) {
    return { success: false, error: err.message || String(err) };
  }
}

export async function setAutoCommit(workspaceRoot: string, enabled: boolean): Promise<{ success: boolean; error?: string }> {
  try {
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

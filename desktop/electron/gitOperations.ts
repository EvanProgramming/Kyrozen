/**
 * Project-level Git helpers used by the desktop client (3.5).
 *
 * All operations target the workspace root of the current project. Credentials
 * are not persisted locally: the GitHub access token is supplied as a one-shot
 * `http.extraHeader` on the push command line and never written to `.git/config`,
 * the remote URL, logs, or project files (3.5 requirement #5).
 *
 * The five push-failure kinds (repo-name-exists is handled at create time) and
 * their recovery actions mirror `kyrozen/core/git_ops.py` so the desktop and the
 * Python agent share identical behaviour.
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

const PUSH_FAILURE_RECOVERY: Record<string, string> = {
  auth_failed: 'GitHub 令牌无效或权限不足。请在「设置 → GitHub」中重新连接账号后重试。',
  network_failed: '无法连接 GitHub。请检查网络连接后重试。',
  non_fast_forward: '远程分支包含本地没有的提交。请先拉取（fetch + rebase）后再推送，或确认要强制覆盖。',
  remote_exists: "远程 'origin' 已存在。请先移除旧远程或直接使用现有远程。",
  unknown: '推送失败。请查看详细错误并稍后重试。',
};

const CREATE_REPO_FAILURE_RECOVERY: Record<string, string> = {
  name_exists: '该名称的仓库已存在。请换一个仓库名，或删除已有仓库后重试。',
  auth_failed: 'GitHub 令牌无效或权限不足。请重新连接账号后重试。',
  network_failed: '无法连接 GitHub。请检查网络连接后重试。',
  unknown: '创建仓库失败。请查看详细错误并稍后重试。',
};

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
  const additions = ['.kyrozen/', '.env', '__pycache__/', 'node_modules/', 'dist/', 'dist-electron/'].filter(
    (entry) => !lines.includes(entry),
  );
  if (additions.length === 0) return;
  const prefix = content && !content.endsWith('\n') ? '\n' : '';
  await fs.writeFile(gitignore, `${content}${prefix}${additions.join('\n')}\n`, 'utf-8');
}

export interface GitStatus {
  success: boolean;
  isRepo: boolean;
  branch?: string;
  ahead?: number;
  behind?: number;
  modified?: string[];
  untracked?: string[];
  staged?: string[];
  recentCommits?: GitCommit[];
  remoteUrl?: string | null;
  error?: string;
}

export interface GitCommit {
  hash: string;
  message: string;
  date: string;
  author: string;
  files?: string[];
}

export interface PushResult {
  success: boolean;
  committed?: boolean;
  failureKind?: string;
  reason?: string;
  recovery?: string;
  error?: string;
}

export interface CreateRepoResult {
  success: boolean;
  url?: string;
  cloneUrl?: string;
  failureKind?: string;
  reason?: string;
  recovery?: string;
  error?: string;
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

    // P0-13/P0-R7 修复：首个提交不能只包含 .gitignore。
    // 当 workspace 已有真实项目文件且尚无提交时，创建首个提交；
    // 若只有 .gitignore，先写入一份 README.md 作为真实交付物，再提交，
    // 避免出现“首提交只有 .gitignore、没有真实项目内容”的误导状态。
    const hasCommits = await git.revparse(['--verify', 'HEAD']).then(() => true).catch(() => false);
    if (!hasCommits) {
      await git.add('-A');
      const status = await git.status();
      const realFiles = [...(status.staged || []), ...(status.files || [])]
        .filter((f) => f !== '.gitignore' && f !== '.kyrozen_gitignore');
      if (realFiles.length > 0) {
        await git.commit('chore: initial Kyrozen project commit');
      } else {
        const readmePath = path.join(workspaceRoot, 'README.md');
        const fs = await import('fs/promises');
        const exists = await fs.stat(readmePath).then(() => true).catch(() => false);
        if (!exists) {
          await fs.writeFile(
            readmePath,
            '# Kyrozen 项目\n\n本仓库由 Kyrozen 初始化。问题定义、调研、PRD 与生成的软件将逐步提交到此处。\n',
            'utf-8',
          );
        }
        await git.add('-A');
        await git.commit('chore: initialize Kyrozen project');
      }
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

export async function getGitStatus(workspaceRoot: string): Promise<GitStatus> {
  try {
    const git = gitInstance(workspaceRoot);
    const isRepo = await git.checkIsRepo();
    if (!isRepo) {
      return { success: true, isRepo: false };
    }
    const status = await git.status();
    const remotes = await git.getRemotes(true);
    const origin = remotes.find((r) => r.name === 'origin');
    const commits = await getGitCommits(workspaceRoot);
    return {
      success: true,
      isRepo: true,
      branch: status.current || undefined,
      ahead: status.ahead,
      behind: status.behind,
      modified: status.modified,
      untracked: status.not_added,
      staged: status.staged,
      recentCommits: commits.commits,
      remoteUrl: origin?.refs.fetch || null,
    };
  } catch (err: any) {
    return { success: false, isRepo: false, error: err.message || String(err) };
  }
}

export async function getGitCommits(workspaceRoot: string): Promise<{ success: boolean; commits: GitCommit[]; remoteUrl: string | null }> {
  try {
    const git = gitInstance(workspaceRoot);
    const isRepo = await git.checkIsRepo();
    if (!isRepo) return { success: true, commits: [], remoteUrl: null };
    const log = await git.log({ maxCount: 5 });
    const remotes = await git.getRemotes(true);
    const origin = remotes.find((r) => r.name === 'origin');
    const commits: GitCommit[] = log.all.map((c) => ({
      hash: c.hash,
      message: c.message,
      date: c.date,
      author: c.author_name,
    }));
    // Attach the file list for the latest commit only (cheap, powers the
    // auto-commit file banner in the UI, 3.5 #7).
    if (commits.length > 0) {
      try {
        const out = await git.raw(['diff', '--name-only', `${commits[0].hash}~1`, commits[0].hash]);
        commits[0].files = out.split('\n').map((s) => s.trim()).filter(Boolean);
      } catch {
        commits[0].files = [];
      }
    }
    return { success: true, commits, remoteUrl: origin?.refs.fetch || null };
  } catch {
    return { success: true, commits: [], remoteUrl: null };
  }
}

export async function commitAndPush(
  workspaceRoot: string,
  token: string | null,
  message: string,
): Promise<PushResult> {
  try {
    const git = gitInstance(workspaceRoot);
    const isRepo = await git.checkIsRepo();
    if (!isRepo) {
      return { success: false, error: '工作区不是 Git 仓库，请先初始化' };
    }

    const config = await loadGitConfig(workspaceRoot);
    await git.add('-A');
    const status = await git.status();
    let committed = false;
    if (status.staged.length > 0 || status.modified.length > 0 || status.not_added.length > 0 || status.deleted.length > 0) {
      await git.commit(message);
      committed = true;
    }

    const remotes = await git.getRemotes(true);
    const origin = remotes.find((r) => r.name === 'origin');
    if (!origin?.refs.fetch || !token) {
      // Local commit only (no remote or not connected).
      return { success: true, committed };
    }

    // Token travels only as a one-shot header; never persisted to .git/config.
    const authorization = Buffer.from(`x-access-token:${token}`).toString('base64');
    try {
      await git.raw([
        '-c', `http.extraHeader=Authorization: Basic ${authorization}`,
        'push', '--set-upstream', 'origin', status.current || 'main',
      ]);
    } catch (pushErr: any) {
      const classified = classifyPushError(pushErr.message || String(pushErr));
      return { success: false, committed, ...classified };
    }

    config.remoteUrl = origin.refs.fetch;
    await saveGitConfig(workspaceRoot, config);
    return { success: true, committed };
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
    console.warn(`Auto-commit failed for ${workspaceRoot}: ${result.error || result.reason}`);
  }
}

// --- failure classification (shared with kyrozen/core/git_ops.py) ----------

export function classifyPushError(stderr: string): { kind: string; reason: string; recovery: string } {
  const text = (stderr || '').toLowerCase();
  if (text.includes('already exists') && text.includes('origin')) {
    return { kind: 'remote_exists', reason: "远程 'origin' 已存在。", recovery: PUSH_FAILURE_RECOVERY.remote_exists };
  }
  if (text.includes('could not resolve host') || text.includes('failed to connect') || text.includes('connection refused') ||
      text.includes('network is unreachable') || text.includes('operation timed out') || text.includes('timeout') ||
      text.includes('fatal: unable to access') || text.includes('temporary failure in name resolution')) {
    return { kind: 'network_failed', reason: '推送失败：无法连接 GitHub 服务器。', recovery: PUSH_FAILURE_RECOVERY.network_failed };
  }
  if (text.includes('authentication failed') || text.includes('could not read username') ||
      text.includes('repository not found') || text.includes('invalid username or password') ||
      text.includes('bad credentials') || text.includes('permission denied') || text.includes('403') || text.includes('401')) {
    return { kind: 'auth_failed', reason: '推送被拒绝：GitHub 令牌无效或权限不足。', recovery: PUSH_FAILURE_RECOVERY.auth_failed };
  }
  if (text.includes('non-fast-forward') || text.includes('fetch first') ||
      text.includes('updates were rejected because the tip') || text.includes('rejected')) {
    return { kind: 'non_fast_forward', reason: '推送被拒绝：远程分支包含本地没有的提交（non-fast-forward）。', recovery: PUSH_FAILURE_RECOVERY.non_fast_forward };
  }
  return { kind: 'unknown', reason: '推送失败。', recovery: PUSH_FAILURE_RECOVERY.unknown };
}

export function classifyCreateRepoError(status: number, body: any): { kind: string; reason: string; recovery: string } {
  const message = typeof body === 'object' && body ? String(body.message || (body.errors as any) || '') : '';
  if (status === 422 || message.toLowerCase().includes('name already exists')) {
    return { kind: 'name_exists', reason: '仓库名已存在（GitHub: name already exists）。', recovery: CREATE_REPO_FAILURE_RECOVERY.name_exists };
  }
  if (status === 401 || status === 403) {
    return { kind: 'auth_failed', reason: '创建仓库被拒绝：令牌无效或权限不足。', recovery: CREATE_REPO_FAILURE_RECOVERY.auth_failed };
  }
  if (status === 0) {
    return { kind: 'network_failed', reason: '创建仓库失败：无法连接 GitHub。', recovery: CREATE_REPO_FAILURE_RECOVERY.network_failed };
  }
  return { kind: 'unknown', reason: `创建仓库失败（HTTP ${status}）。`, recovery: CREATE_REPO_FAILURE_RECOVERY.unknown };
}

/**
 * Scan the workspace (excluding `.git`) for occurrences of `token`. A correct
 * implementation always returns `[]` — the token must never be written to
 * `.git/config`, the remote URL, logs, or project files (3.5 #5, acceptance:
 * secret scan zero hits).
 */
export async function scanSecrets(workspaceRoot: string, token: string): Promise<string[]> {
  if (!token) return [];
  const hits: string[] = [];
  const gitConfig = path.join(workspaceRoot, '.git', 'config');
  try {
    const cfg = await fs.readFile(gitConfig, 'utf-8');
    if (cfg.includes(token)) hits.push(path.relative(workspaceRoot, gitConfig));
  } catch { /* no git config */ }
  async function walk(dir: string): Promise<void> {
    let entries: { name: string; isDirectory(): boolean; isFile(): boolean }[];
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.name === '.git') continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        await walk(full);
      } else {
        try {
          const content = await fs.readFile(full, 'utf-8');
          if (content.includes(token)) hits.push(path.relative(workspaceRoot, full));
        } catch { /* binary / unreadable */ }
      }
    }
  }
  await walk(workspaceRoot);
  return hits;
}

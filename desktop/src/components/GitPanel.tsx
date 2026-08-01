import { useEffect, useRef, useState } from 'react';

interface GitHubStatus {
  connected: boolean;
  scope?: string;
  login?: string;
  avatarUrl?: string;
  expired?: boolean;
}

interface GitCommit {
  hash: string;
  message: string;
  date: string;
  author: string;
  files?: string[];
}

interface GitStatus {
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

interface PushFailure {
  failureKind?: string;
  reason?: string;
  recovery?: string;
  error?: string;
}

export function GitPanel({ projectId }: { projectId: string | null }) {
  const kyzen = window.kyrozen!;
  const [gh, setGh] = useState<GitHubStatus | null>(null);
  const [status, setStatus] = useState<GitStatus | null>(null);
  const [repositoryName, setRepositoryName] = useState('');
  const [repositoryPrivate, setRepositoryPrivate] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [commitMessage, setCommitMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [failure, setFailure] = useState<PushFailure | null>(null);
  const [autoBanner, setAutoBanner] = useState<string[] | null>(null);
  const lastHashRef = useRef<string | null>(null);

  const loadStatus = async () => {
    const github = await kyzen.getGitHubStatus();
    setGh(github);
    const git = await kyzen.getGitStatus(projectId ?? undefined);
    setStatus(git);
    if (git.recentCommits && git.recentCommits.length > 0) {
      lastHashRef.current = git.recentCommits[0].hash;
    }
  };

  useEffect(() => {
    if (!projectId) { setStatus(null); return; }
    void loadStatus();
    const refreshTimer = window.setInterval(() => { void loadStatus(); }, 4000);
    return () => { window.clearInterval(refreshTimer); };
  }, [kyzen, projectId]);

  const initRepo = async () => {
    setLoading(true); setError(null); setFailure(null);
    const result = await kyzen.initGitRepo();
    if (!result.success) setError(result.error || '初始化失败');
    else setSuccess('Git 仓库已初始化（主分支 main，已包含首个提交与 .gitignore）');
    setLoading(false);
    await loadStatus();
  };

  const createRepository = async () => {
    if (!repositoryName.trim() || !gh?.login) return;
    setLoading(true); setError(null); setFailure(null); setConfirmOpen(false);
    const result = await kyzen.createGitHubRepo(gh.login, repositoryName.trim(), '', repositoryPrivate);
    if (result.success) {
      setSuccess('GitHub 仓库已创建，首次提交已推送并连接到当前项目');
      setRepositoryName('');
    } else {
      // 3.5 #6: surface the classified reason + recovery (e.g. name_exists).
      setFailure({ failureKind: result.failureKind, reason: result.reason || result.error, recovery: result.recovery });
    }
    setLoading(false);
    await loadStatus();
  };

  const commit = async () => {
    if (!commitMessage.trim()) { setError('请输入提交信息'); return; }
    setLoading(true); setError(null); setFailure(null);
    const before = status ? [...(status.modified || []), ...(status.untracked || []), ...(status.staged || [])] : [];
    const result = await kyzen.commitAndPush(commitMessage);
    if (!result.success) {
      setFailure({ failureKind: result.failureKind, reason: result.reason || result.error, recovery: result.recovery });
      setError(null);
    } else {
      setSuccess(gh?.connected ? '提交完成并推送至 GitHub' : '本地提交成功');
      setCommitMessage('');
      if (before.length > 0) setAutoBanner(before);
    }
    setLoading(false);
    await loadStatus();
  };

  const generateCommitMessage = () => {
    const files = [
      ...(status?.staged || []),
      ...(status?.modified || []),
      ...(status?.untracked || []),
    ];
    const uniqueFiles = [...new Set(files)];
    if (uniqueFiles.length === 0) {
      setCommitMessage('chore: update project');
      return;
    }
    const firstName = uniqueFiles[0].split('/').pop() || uniqueFiles[0];
    const subject = uniqueFiles.length === 1
      ? `update ${firstName}`
      : `update ${uniqueFiles.length} files`;
    setCommitMessage(`chore: ${subject}`);
  };

  const changedCount = (status?.modified?.length || 0) + (status?.untracked?.length || 0) + (status?.staged?.length || 0);
  const statusBadge = (s: GitStatus | null) => {
    if (!s?.isRepo) return <span className="text-xs px-2 py-0.5 rounded-sm bg-paper-edge text-ink-faint">未初始化</span>;
    return <span className="text-xs px-2 py-0.5 rounded-sm bg-success-soft text-success">已初始化</span>;
  };

  return (
    <div className="flex flex-col overflow-y-auto border-t border-line p-4" data-testid="git-panel">
      <h3 className="font-display text-lg text-ink mb-3">GitHub / Git</h3>
      {!projectId && <div className="text-xs text-ink-faint">选择项目后管理仓库</div>}

      {/* P0-12 修复：创建 GitHub 仓库的条件是"无远程 origin"，不是"非仓库"。
+           本地初始化后仍应能创建远程并推送。 */}
      {gh?.connected && !gh.expired && !status?.remoteUrl && (
        <div className="mb-4 p-3 panel space-y-2">
          <div className="text-sm font-medium">创建 GitHub 仓库</div>
          <div className="text-xs text-ink-faint">所有者：<span className="text-ink-soft">{gh.login}</span></div>
          <input className="input" value={repositoryName} onChange={(e) => setRepositoryName(e.target.value)} placeholder="仓库名称" />
          <label className="flex items-center gap-2 text-xs text-ink-soft">
            <input type="checkbox" checked={repositoryPrivate} onChange={(e) => setRepositoryPrivate(e.target.checked)} />
            私有仓库
          </label>
          <button type="button" onClick={() => setConfirmOpen(true)} disabled={loading || !repositoryName.trim()} className="btn-primary w-full text-sm">下一步</button>

          {confirmOpen && (
            <div className="border-l-2 border-l-accent bg-accent-soft p-2 space-y-1">
              <div className="text-xs font-medium text-ink">确认创建仓库</div>
              <div className="text-xs text-ink-soft">{gh.login}/{repositoryName.trim()}</div>
              <div className="text-xs text-ink-soft">{repositoryPrivate ? '私有仓库' : '公开仓库'}</div>
              <div className="flex gap-2 pt-1">
                <button type="button" onClick={createRepository} disabled={loading} className="btn-primary text-xs flex-1">确认创建</button>
                <button type="button" onClick={() => setConfirmOpen(false)} className="btn-ghost text-xs flex-1">返回</button>
              </div>
            </div>
          )}
          {failure && (
            <div className="border-l-2 border-l-danger bg-danger-soft p-2 space-y-1">
              <div className="text-xs font-medium text-danger">{failure.reason}</div>
              {failure.recovery && <div className="text-xs text-ink-soft">{failure.recovery}</div>}
              <button type="button" onClick={() => setFailure(null)} className="btn-ghost text-xs">关闭</button>
            </div>
          )}
        </div>
      )}

      {/* 3.5 #3: init local repo (and first commit handled by backend) */}
      {!status?.isRepo && (
        <div className="mb-4 p-3 panel space-y-2">
          <div className="text-sm font-medium">本地仓库</div>
          <button type="button" onClick={initRepo} disabled={loading} className="btn-secondary w-full text-sm py-1.5">初始化 Git 仓库（main 分支 + .gitignore + 首个提交）</button>
        </div>
      )}

      {/* 3.5 #7: repo view — branch / status / commits / remote */}
      {status?.isRepo && (
        <div className="mb-4 p-3 panel space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">仓库</span>
            {statusBadge(status)}
          </div>
          <div className="text-sm text-ink-soft">
            分支: {status.branch || 'unknown'}
            {typeof status.ahead === 'number' && status.ahead > 0 && <span className="ml-2 text-success">↑{status.ahead}</span>}
            {typeof status.behind === 'number' && status.behind > 0 && <span className="ml-2 text-danger">↓{status.behind}</span>}
          </div>
          {status.remoteUrl && (
            <div className="text-xs text-ink-faint break-all">
              远程: <a href={status.remoteUrl} target="_blank" rel="noreferrer" className="text-accent underline">{status.remoteUrl}</a>
            </div>
          )}

          <div className="text-xs font-medium text-ink-soft">最近提交</div>
          <div className="max-h-32 overflow-y-auto space-y-1">
            {(status.recentCommits && status.recentCommits.length > 0)
              ? status.recentCommits.map((c) => (
                <div key={c.hash} className="text-xs text-ink-soft">
                  <span className="font-mono text-ink-faint">{c.hash.slice(0, 7)}</span> {c.message}
                  <span className="text-ink-faint"> · {c.date}</span>
                </div>
              ))
              : <div className="text-xs text-ink-ghost">暂无提交</div>}
          </div>

          <div className="text-xs font-medium text-ink-soft">变更文件 ({changedCount})</div>
          <div className="max-h-28 overflow-y-auto space-y-1">
            {status.staged?.map((f) => <div key={`s-${f}`} className="text-xs text-accent font-mono truncate">A {f}</div>)}
            {status.modified?.map((f) => <div key={`m-${f}`} className="text-xs text-warning font-mono truncate">M {f}</div>)}
            {status.untracked?.map((f) => <div key={`u-${f}`} className="text-xs text-success font-mono truncate">? {f}</div>)}
            {changedCount === 0 && <div className="text-xs text-ink-ghost">暂无变更</div>}
          </div>

          <div className="flex items-center gap-1.5">
            <input type="text" value={commitMessage} onChange={(e) => setCommitMessage(e.target.value)} placeholder="提交信息" className="input min-w-0 flex-1" />
            <button
              type="button"
              onClick={generateCommitMessage}
              disabled={loading || changedCount === 0}
              className="btn-secondary shrink-0 px-2 py-1.5 text-sm"
              title="自动生成提交信息"
              aria-label="自动生成提交信息"
            >
              ✨
            </button>
          </div>
          <button type="button" onClick={commit} disabled={loading || changedCount === 0} className="btn-primary w-full text-sm py-1.5">
            {gh?.connected ? '提交并推送' : '本地提交'}
          </button>
          {failure && (
            <div className="border-l-2 border-l-danger bg-danger-soft p-2 space-y-1">
              <div className="text-xs font-medium text-danger">{failure.reason || failure.error}</div>
              {failure.recovery && <div className="text-xs text-ink-soft">{failure.recovery}</div>}
              <button type="button" onClick={() => setFailure(null)} className="btn-ghost text-xs">关闭</button>
            </div>
          )}

        </div>
      )}

      {/* 3.5 #7: dismissible auto-commit file banner */}
      {autoBanner && (
        <div className="mb-4 p-3 panel border-l-2 border-l-accent space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-ink">已提交文件</span>
            <button type="button" onClick={() => setAutoBanner(null)} className="text-xs text-ink-faint hover:text-ink">关闭 ✕</button>
          </div>
          <div className="max-h-28 overflow-y-auto space-y-0.5">
            {autoBanner.map((f) => <div key={f} className="text-xs font-mono text-ink-soft truncate">{f}</div>)}
          </div>
        </div>
      )}

      {error && <div className="mb-2 text-sm text-danger">{error}</div>}
      {success && <div className="mb-2 text-sm text-success">{success}</div>}
    </div>
  );
}

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
  upstream?: string | null;
  error?: string;
}

interface PushFailure {
  operation: 'create' | 'push';
  failureKind?: string;
  reason?: string;
  recovery?: string;
  error?: string;
  repositoryUrl?: string;
  cloneUrl?: string;
}

export function GitPanel({ projectId }: { projectId: string | null }) {
  const kyzen = window.kyrozen!;
  const [gh, setGh] = useState<GitHubStatus | null>(null);
  const [status, setStatus] = useState<GitStatus | null>(null);
  const [repositoryName, setRepositoryName] = useState('');
  const [repositoryPrivate, setRepositoryPrivate] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [commitMessage, setCommitMessage] = useState('');
  const [autoCommit, setAutoCommit] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [failure, setFailure] = useState<PushFailure | null>(null);
  const [autoBanner, setAutoBanner] = useState<string[] | null>(null);
  const lastHashRef = useRef<string | null>(null);
  const repositoryNameRef = useRef<HTMLInputElement | null>(null);

  const loadStatus = async () => {
    const github = await kyzen.getGitHubStatus();
    setGh(github);
    const git = await kyzen.getGitStatus(projectId ?? undefined);
    setStatus(git);
    const auto = await kyzen.getAutoCommit();
    setAutoCommit(auto.enabled);
    if (git.recentCommits && git.recentCommits.length > 0) {
      lastHashRef.current = git.recentCommits[0].hash;
    }
    return { github, git };
  };

  useEffect(() => {
    if (!projectId) { setStatus(null); return; }
    void loadStatus();
    const unsubscribe = kyzen.onGitHubStatus((st) => { setGh(st); void loadStatus(); });
    return () => { unsubscribe?.(); };
  }, [kyzen, projectId]);

  // 3.5 #7: while auto-commit is on, surface the committed file list when a new
  // commit appears (dismissible banner).
  useEffect(() => {
    if (!projectId || !autoCommit) return;
    const timer = setInterval(async () => {
      try {
        const result = await kyzen.getGitCommits(projectId ?? undefined);
        const latest = result.commits?.[0];
        if (latest && lastHashRef.current && latest.hash !== lastHashRef.current) {
          lastHashRef.current = latest.hash;
          setAutoBanner(latest.files && latest.files.length > 0 ? latest.files : ['(无文件变更)']);
        } else if (latest) {
          lastHashRef.current = latest.hash;
        }
      } catch { /* ignore */ }
    }, 4000);
    return () => clearInterval(timer);
  }, [kyzen, projectId, autoCommit]);

  const connect = async () => {
    setLoading(true); setError(null); setSuccess(null);
    const result = await kyzen.connectGitHub();
    if (!result.success) setError(result.error || '连接失败');
    setLoading(false);
  };

  const relogin = async () => {
    setLoading(true); setError(null); setSuccess(null);
    const result = await kyzen.startGithubLogin();
    if (!result.success) setError(result.error || '重新连接失败');
    setLoading(false);
  };

  const disconnect = async () => {
    setLoading(true); setError(null); setSuccess(null); setFailure(null);
    await kyzen.disconnectGitHub();
    setSuccess('已断开 GitHub 连接');
    await loadStatus();
    setLoading(false);
  };

  const initRepo = async () => {
    if (!projectId) { setError('请先选择项目'); return; }
    setLoading(true); setError(null); setSuccess(null); setFailure(null);
    const result = await kyzen.initGitRepo();
    if (!result.success) setError(result.error || '初始化失败');
    else setSuccess('Git 仓库已初始化（主分支 main，已包含首个提交与 .gitignore）');
    setLoading(false);
    await loadStatus();
  };

  const createRepository = async () => {
    if (!projectId) { setError('请先选择项目'); return; }
    if (!status?.isRepo) { setError('请先初始化当前项目的 Git 仓库'); return; }
    if (status.remoteUrl) { setError('当前项目已经配置 origin，不能重复创建远程仓库'); return; }
    if (!repositoryName.trim()) { setError('请输入仓库名称'); return; }
    if (!gh?.login || !gh.connected || gh.expired) { setError('请先重新连接 GitHub'); return; }
    setLoading(true); setError(null); setSuccess(null); setFailure(null); setConfirmOpen(false);
    const result = await kyzen.createGitHubRepo(gh.login, repositoryName.trim(), '', repositoryPrivate);
    if (result.success) {
      // Do not trust a generic IPC success as proof of publication.  A real
      // first push establishes both origin and an upstream tracking branch.
      const refreshed = await loadStatus();
      if (refreshed.git.isRepo && refreshed.git.remoteUrl && refreshed.git.upstream) {
        setSuccess('GitHub 仓库已创建，首次提交已推送并连接到当前项目');
        setRepositoryName('');
      } else {
        setFailure({
          operation: 'push',
          failureKind: 'publish_unverified',
          reason: 'GitHub 仓库可能已创建，但未确认首次推送成功。',
          recovery: '保留当前本地提交，检查远程配置后重试推送。',
          repositoryUrl: result.url,
          cloneUrl: result.cloneUrl,
        });
      }
    } else {
      setFailure({
        operation: result.url || result.cloneUrl ? 'push' : 'create',
        failureKind: result.failureKind,
        reason: result.reason || result.error,
        recovery: result.recovery,
        repositoryUrl: result.url,
        cloneUrl: result.cloneUrl,
      });
    }
    setLoading(false);
    await loadStatus();
  };

  const commit = async () => {
    const hasChanges = changedCount > 0;
    if (hasChanges && !commitMessage.trim()) { setError('请输入提交信息'); return; }
    if (!hasChanges && !canPush) { setError('当前没有需要提交的变更'); return; }
    setLoading(true); setError(null); setSuccess(null); setFailure(null);
    const before = status ? [...(status.modified || []), ...(status.untracked || []), ...(status.staged || [])] : [];
    const result = await kyzen.commitAndPush(commitMessage.trim() || 'chore: sync current branch');
    if (!result.success) {
      setFailure({ operation: 'push', failureKind: result.failureKind, reason: result.reason || result.error, recovery: result.recovery });
      setError(null);
    } else if (result.pushed) {
      setSuccess(result.committed ? '提交完成并已推送至 GitHub' : '当前分支已成功推送至 GitHub');
      setCommitMessage('');
      if (result.committed && before.length > 0) setAutoBanner(before);
    } else {
      const reason = result.pushSkippedReason === 'no_remote'
        ? '尚未配置 origin'
        : result.pushSkippedReason === 'not_authenticated'
          ? 'GitHub 尚未连接'
          : '未执行远程推送';
      setSuccess(result.committed ? `本地提交成功，尚未推送（${reason}）` : `没有新变更，尚未推送（${reason}）`);
      setCommitMessage('');
      if (result.committed && before.length > 0) setAutoBanner(before);
    }
    setLoading(false);
    await loadStatus();
  };

  const retryPush = async () => {
    if (!projectId) { setError('请先选择项目'); return; }
    setLoading(true); setError(null); setSuccess(null);
    const latest = await kyzen.getGitStatus(projectId);
    const pendingChanges = (latest.modified?.length || 0) + (latest.untracked?.length || 0) + (latest.staged?.length || 0);
    if (pendingChanges > 0) {
      setStatus(latest);
      setFailure(null);
      setError('检测到新的未提交变更。请填写提交信息，再使用“提交并推送”。');
      setLoading(false);
      return;
    }
    const result = await kyzen.commitAndPush('chore: retry GitHub push');
    if (result.success && result.pushed) {
      setFailure(null);
      setSuccess('当前分支已成功推送至 GitHub');
    } else if (result.success) {
      setFailure({
        operation: 'push',
        failureKind: result.pushSkippedReason || 'push_skipped',
        reason: '没有执行远程推送。',
        recovery: result.pushSkippedReason === 'no_remote' ? '请先创建或配置 GitHub 远程仓库。' : '请重新连接 GitHub 后重试。',
      });
    } else {
      setFailure({ operation: 'push', failureKind: result.failureKind, reason: result.reason || result.error, recovery: result.recovery });
    }
    await loadStatus();
    setLoading(false);
  };

  const retryCreate = () => {
    setFailure(null);
    setConfirmOpen(true);
  };

  const reconnectCreatedRepository = async () => {
    if (!failure?.cloneUrl) return;
    setLoading(true); setError(null); setSuccess(null);
    const initialized = await kyzen.initGitRepo(failure.cloneUrl);
    if (!initialized.success) {
      setError(initialized.error || '连接已创建仓库失败');
      setLoading(false);
      return;
    }
    setLoading(false);
    await retryPush();
  };

  const copyRebaseCommand = async () => {
    const branch = status?.branch || 'main';
    try {
      await navigator.clipboard.writeText(`git pull --rebase origin ${branch}`);
      setSuccess('已复制安全的 rebase 命令；请在当前项目终端运行后点击“重试推送”。');
    } catch {
      setError(`无法访问剪贴板。请在当前项目终端运行：git pull --rebase origin ${branch}`);
    }
  };

  const editRepositoryName = () => {
    setFailure(null);
    setConfirmOpen(false);
    repositoryNameRef.current?.focus();
    repositoryNameRef.current?.select();
  };

  const toggleAutoCommit = async () => {
    const next = !autoCommit;
    setLoading(true);
    const result = await kyzen.setAutoCommit(next);
    if (!result.success) setError(result.error || '设置失败');
    else setAutoCommit(next);
    setLoading(false);
  };

  const changedCount = (status?.modified?.length || 0) + (status?.untracked?.length || 0) + (status?.staged?.length || 0);
  const canPush = Boolean(status?.isRepo && status.remoteUrl && gh?.connected && !gh.expired);
  const statusBadge = (s: GitStatus | null) => {
    if (!s?.isRepo) return <span className="text-xs px-2 py-0.5 rounded-sm bg-paper-edge text-ink-faint">未初始化</span>;
    return <span className="text-xs px-2 py-0.5 rounded-sm bg-success-soft text-success">已初始化</span>;
  };

  return (
    <div className="flex flex-col overflow-y-auto border-t border-line p-4" data-testid="git-panel">
      <h3 className="font-display text-lg text-ink mb-3">GitHub / Git</h3>
      {!projectId && <div className="text-xs text-ink-faint">选择项目后管理仓库</div>}

      {/* 3.5 #2: account card with avatar / login / scope / status */}
      <div className="mb-4 p-3 panel space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">GitHub 账号</span>
          {gh?.connected
            ? <span className={`text-xs px-2 py-0.5 rounded-sm ${gh.expired ? 'bg-warning-soft text-warning' : 'bg-success-soft text-success'}`}>{gh.expired ? '已过期' : '已连接'}</span>
            : <span className="text-xs px-2 py-0.5 rounded-sm bg-paper-edge text-ink-faint">未连接</span>}
        </div>
        {gh?.connected && (
          <div className="flex items-center gap-2">
            {gh.avatarUrl && <img src={gh.avatarUrl} alt={gh.login || ''} className="w-8 h-8 rounded-full bg-paper-sink" />}
            <div className="text-sm">
              <div className="text-ink">{gh.login || '未知用户'}</div>
              {gh.scope && <div className="text-xs text-ink-faint">scope: {gh.scope}</div>}
            </div>
          </div>
        )}
        {!gh?.connected && (
          <button type="button" onClick={connect} disabled={loading} className="btn-primary w-full text-sm py-1.5">
            {loading ? '处理中…' : '授权 GitHub'}
          </button>
        )}
        {gh?.connected && (
          <button type="button" onClick={disconnect} disabled={loading} className="btn-ghost w-full text-sm py-1.5">
            断开连接
          </button>
        )}
        {/* 3.5 #1: expiry -> re-login guidance */}
        {gh?.connected && gh.expired && (
          <div className="border-l-2 border-l-warning bg-warning-soft p-2 text-xs text-ink-soft">
            GitHub 授权已过期或已撤销。请重新连接以继续推送。
            <button type="button" onClick={relogin} disabled={loading} className="btn-primary w-full text-sm py-1 mt-2">重新连接 GitHub</button>
          </div>
        )}
      </div>

      {/* A remote can only be created for a selected, initialized project. */}
      {projectId && gh?.connected && !gh.expired && status?.isRepo && !status.remoteUrl && (
        <div className="mb-4 p-3 panel space-y-2">
          <div className="text-sm font-medium">创建 GitHub 仓库</div>
          <div className="text-xs text-ink-faint">所有者：<span className="text-ink-soft">{gh.login}</span></div>
          <input ref={repositoryNameRef} className="input" value={repositoryName} onChange={(e) => setRepositoryName(e.target.value)} placeholder="仓库名称" />
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
          {failure?.operation === 'create' && (
            <div className="border-l-2 border-l-danger bg-danger-soft p-2 space-y-1">
              <div className="text-xs font-medium text-danger">{failure.reason || failure.error || '创建仓库失败'}</div>
              {failure.recovery && <div className="text-xs text-ink-soft">{failure.recovery}</div>}
              <div className="flex gap-2 pt-1">
                {failure.failureKind === 'name_exists'
                  ? <button type="button" onClick={editRepositoryName} disabled={loading} className="btn-secondary text-xs flex-1">更换仓库名</button>
                  : <button type="button" onClick={retryCreate} disabled={loading} className="btn-secondary text-xs flex-1">重新检查并重试</button>}
                {failure.failureKind === 'auth_failed' && (
                  <button type="button" onClick={relogin} disabled={loading} className="btn-primary text-xs flex-1">重新连接 GitHub</button>
                )}
                <button type="button" onClick={() => setFailure(null)} className="btn-ghost text-xs">关闭</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 3.5 #3: init local repo (and first commit handled by backend) */}
      {projectId && !status?.isRepo && (
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
          {status.remoteUrl && (
            <div className="text-xs text-ink-faint">
              推送跟踪: {status.upstream
                ? <span className="text-success">{status.upstream}</span>
                : <span className="text-warning">尚未建立；首次推送未完成</span>}
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

          <input type="text" value={commitMessage} onChange={(e) => setCommitMessage(e.target.value)} placeholder="提交信息" className="input" />
          <button
            type="button"
            onClick={commit}
            disabled={loading || (changedCount === 0 && !canPush)}
            className="btn-primary w-full text-sm py-1.5"
          >
            {canPush ? (changedCount > 0 ? '提交并推送' : '推送当前分支') : '本地提交'}
          </button>
          {failure?.operation === 'push' && (
            <div className="border-l-2 border-l-danger bg-danger-soft p-2 space-y-1">
              <div className="text-xs font-medium text-danger">{failure.reason || failure.error}</div>
              {failure.recovery && <div className="text-xs text-ink-soft">{failure.recovery}</div>}
              {failure.repositoryUrl && (
                <a href={failure.repositoryUrl} target="_blank" rel="noreferrer" className="block text-xs text-accent underline">打开已创建的 GitHub 仓库</a>
              )}
              <div className="flex gap-2 pt-1">
                {failure.cloneUrl
                  ? <button type="button" onClick={reconnectCreatedRepository} disabled={loading} className="btn-primary text-xs flex-1">连接仓库并重试推送</button>
                  : failure.failureKind === 'auth_failed' || failure.failureKind === 'not_authenticated'
                  ? <button type="button" onClick={relogin} disabled={loading} className="btn-primary text-xs flex-1">重新连接 GitHub</button>
                  : <button type="button" onClick={retryPush} disabled={loading} className="btn-primary text-xs flex-1">重新检查并重试推送</button>}
                {failure.failureKind === 'non_fast_forward' && (
                  <button type="button" onClick={copyRebaseCommand} disabled={loading} className="btn-secondary text-xs flex-1">复制 rebase 修复命令</button>
                )}
                <button type="button" onClick={() => { setFailure(null); void loadStatus(); }} className="btn-ghost text-xs">刷新状态</button>
                <button type="button" onClick={() => setFailure(null)} className="btn-ghost text-xs">关闭</button>
              </div>
            </div>
          )}

          <label className="flex items-center gap-2 text-sm text-ink-soft cursor-pointer">
            <input type="checkbox" checked={autoCommit} onChange={toggleAutoCommit} disabled={loading} className="rounded-sm border-line-strong bg-surface accent-accent focus:ring-0" />
            自动提交变更
          </label>
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

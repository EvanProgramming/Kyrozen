import { useEffect, useState } from 'react';

interface GitStatus {
  success: boolean;
  isRepo: boolean;
  branch?: string;
  ahead?: number;
  behind?: number;
  modified?: string[];
  untracked?: string[];
  error?: string;
}

export function GitPanel() {
  const kyrozen = window.kyrozen!;
  const [connected, setConnected] = useState(false);
  const [scope, setScope] = useState<string | undefined>();
  const [status, setStatus] = useState<GitStatus | null>(null);
  const [remoteUrl, setRemoteUrl] = useState('');
  const [commitMessage, setCommitMessage] = useState('');
  const [autoCommit, setAutoCommit] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadStatus = async () => {
    const github = await kyrozen.getGitHubStatus();
    setConnected(github.connected);
    setScope(github.scope);
    const git = await kyrozen.getGitStatus();
    setStatus(git);
    const auto = await kyrozen.getAutoCommit();
    setAutoCommit(auto.enabled);
  };

  useEffect(() => {
    loadStatus();
    const unsubscribe = kyrozen.onGitHubStatus((st) => {
      setConnected(st.connected);
      setScope(st.scope);
      void loadStatus();
    });
    return () => {
      unsubscribe?.();
    };
  }, [kyrozen]);

  const connect = async () => {
    setLoading(true);
    setError(null);
    const result = await kyrozen.connectGitHub();
    if (!result.success) {
      setError(result.error || '连接失败');
    }
    setLoading(false);
  };

  const initRepo = async () => {
    setLoading(true);
    setError(null);
    const result = await kyrozen.initGitRepo(remoteUrl || undefined);
    if (!result.success) {
      setError(result.error || '初始化失败');
    } else {
      setSuccess('Git 仓库已初始化');
    }
    setLoading(false);
    await loadStatus();
  };

  const commit = async () => {
    if (!commitMessage.trim()) {
      setError('请输入提交信息');
      return;
    }
    setLoading(true);
    setError(null);
    const result = await kyrozen.commitAndPush(commitMessage);
    if (!result.success) {
      setError(result.error || '提交失败');
    } else {
      setSuccess('提交并推送成功');
      setCommitMessage('');
    }
    setLoading(false);
    await loadStatus();
  };

  const toggleAutoCommit = async () => {
    const next = !autoCommit;
    setLoading(true);
    const result = await kyrozen.setAutoCommit(next);
    if (!result.success) {
      setError(result.error || '设置失败');
    } else {
      setAutoCommit(next);
    }
    setLoading(false);
  };

  const changedCount = (status?.modified?.length || 0) + (status?.untracked?.length || 0);

  return (
    <div className="flex flex-col overflow-y-auto border-t border-slate-700 p-4">
      <h3 className="text-sm font-semibold text-slate-200 mb-3">GitHub / Git</h3>

      <div className="mb-4 p-3 panel">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium">GitHub 账号</span>
          <span className={`text-xs px-2 py-0.5 rounded-sm ${connected ? 'bg-success-soft text-success' : 'bg-paper-edge text-ink-faint'}`}>
            {connected ? '已连接' : '未连接'}
          </span>
        </div>
        {connected && scope && <div className="text-xs text-ink-faint mb-2">scope: {scope}</div>}
        <button
          type="button"
          onClick={connect}
          disabled={loading || connected}
          className="btn-primary w-full text-sm py-1.5"
        >
          {connected ? '已授权' : '授权 GitHub'}
        </button>
      </div>

      <div className="mb-4 p-3 panel">
        <div className="text-sm font-medium mb-2">仓库</div>
        {status?.isRepo ? (
          <div className="text-sm text-ink-soft mb-2">
            分支: {status.branch || 'unknown'}
            {typeof status.ahead === 'number' && status.ahead > 0 && (
              <span className="ml-2 text-success">↑{status.ahead}</span>
            )}
            {typeof status.behind === 'number' && status.behind > 0 && (
              <span className="ml-2 text-danger">↓{status.behind}</span>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            <input
              type="text"
              value={remoteUrl}
              onChange={(e) => setRemoteUrl(e.target.value)}
              placeholder="https://github.com/user/repo.git（可选）"
              className="input"
            />
            <button
              type="button"
              onClick={initRepo}
              disabled={loading}
              className="btn-secondary w-full text-sm py-1.5"
            >
              初始化 Git 仓库
            </button>
          </div>
        )}
      </div>

      {status?.isRepo && (
        <div className="mb-4 p-3 panel space-y-3">
          <div className="text-sm font-medium">变更文件 ({changedCount})</div>
          <div className="max-h-32 overflow-y-auto space-y-1">
            {status.modified?.map((f) => (
              <div key={f} className="text-xs text-warning font-mono truncate">M {f}</div>
            ))}
            {status.untracked?.map((f) => (
              <div key={f} className="text-xs text-success font-mono truncate">? {f}</div>
            ))}
            {changedCount === 0 && <div className="text-xs text-ink-ghost">暂无变更</div>}
          </div>

          <input
            type="text"
            value={commitMessage}
            onChange={(e) => setCommitMessage(e.target.value)}
            placeholder="提交信息"
            className="input"
          />
          <button
            type="button"
            onClick={commit}
            disabled={loading || changedCount === 0}
            className="btn-primary w-full text-sm py-1.5"
          >
            提交并推送
          </button>

          <label className="flex items-center gap-2 text-sm text-ink-soft cursor-pointer">
            <input
              type="checkbox"
              checked={autoCommit}
              onChange={toggleAutoCommit}
              disabled={loading}
              className="rounded-sm border-line-strong bg-surface accent-accent focus:ring-0"
            />
            自动提交变更
          </label>
        </div>
      )}

      {error && <div className="mb-2 text-sm text-danger">{error}</div>}
      {success && <div className="mb-2 text-sm text-success">{success}</div>}
    </div>
  );
}

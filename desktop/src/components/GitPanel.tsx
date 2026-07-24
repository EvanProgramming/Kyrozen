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
    <div className="h-full flex flex-col bg-slate-900 text-slate-200 p-4 border-l border-slate-700 overflow-y-auto">
      <h2 className="text-lg font-semibold mb-4">GitHub / Git</h2>

      <div className="mb-4 p-3 bg-slate-800 rounded-lg">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium">GitHub 账号</span>
          <span className={`text-xs px-2 py-0.5 rounded ${connected ? 'bg-green-900 text-green-300' : 'bg-slate-600 text-slate-300'}`}>
            {connected ? '已连接' : '未连接'}
          </span>
        </div>
        {connected && scope && <div className="text-xs text-slate-400 mb-2">scope: {scope}</div>}
        <button
          type="button"
          onClick={connect}
          disabled={loading || connected}
          className="w-full py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 text-white rounded text-sm font-medium transition-colors"
        >
          {connected ? '已授权' : '授权 GitHub'}
        </button>
      </div>

      <div className="mb-4 p-3 bg-slate-800 rounded-lg">
        <div className="text-sm font-medium mb-2">仓库</div>
        {status?.isRepo ? (
          <div className="text-sm text-slate-300 mb-2">
            分支: {status.branch || 'unknown'}
            {typeof status.ahead === 'number' && status.ahead > 0 && (
              <span className="ml-2 text-green-400">↑{status.ahead}</span>
            )}
            {typeof status.behind === 'number' && status.behind > 0 && (
              <span className="ml-2 text-red-400">↓{status.behind}</span>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            <input
              type="text"
              value={remoteUrl}
              onChange={(e) => setRemoteUrl(e.target.value)}
              placeholder="https://github.com/user/repo.git（可选）"
              className="w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm focus:outline-none focus:border-blue-500"
            />
            <button
              type="button"
              onClick={initRepo}
              disabled={loading}
              className="w-full py-1.5 bg-slate-700 hover:bg-slate-600 text-white rounded text-sm font-medium transition-colors"
            >
              初始化 Git 仓库
            </button>
          </div>
        )}
      </div>

      {status?.isRepo && (
        <div className="mb-4 p-3 bg-slate-800 rounded-lg space-y-3">
          <div className="text-sm font-medium">变更文件 ({changedCount})</div>
          <div className="max-h-32 overflow-y-auto space-y-1">
            {status.modified?.map((f) => (
              <div key={f} className="text-xs text-yellow-400 font-mono truncate">M {f}</div>
            ))}
            {status.untracked?.map((f) => (
              <div key={f} className="text-xs text-green-400 font-mono truncate">? {f}</div>
            ))}
            {changedCount === 0 && <div className="text-xs text-slate-500">暂无变更</div>}
          </div>

          <input
            type="text"
            value={commitMessage}
            onChange={(e) => setCommitMessage(e.target.value)}
            placeholder="提交信息"
            className="w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm focus:outline-none focus:border-blue-500"
          />
          <button
            type="button"
            onClick={commit}
            disabled={loading || changedCount === 0}
            className="w-full py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 text-white rounded text-sm font-medium transition-colors"
          >
            提交并推送
          </button>

          <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={autoCommit}
              onChange={toggleAutoCommit}
              disabled={loading}
              className="rounded border-slate-600 bg-slate-900 text-blue-600 focus:ring-0"
            />
            自动提交变更
          </label>
        </div>
      )}

      {error && <div className="mb-2 text-sm text-red-400">{error}</div>}
      {success && <div className="mb-2 text-sm text-green-400">{success}</div>}
    </div>
  );
}

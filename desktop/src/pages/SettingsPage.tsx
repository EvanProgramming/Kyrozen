import { useState } from 'react';

export interface Props {
  onClose: () => void;
  fullTrust: boolean;
  onToggleFullTrust: () => void;
  githubStatus: { connected: boolean; scope: string };
  onConnectGitHub: () => void;
  language: 'zh' | 'en';
  onChangeLanguage: (lang: 'zh' | 'en') => void;
  onLogout: () => void;
  serverUrl: string;
  onChangeServerUrl: (url: string) => Promise<void>;
}

export function SettingsPage({
  onClose,
  fullTrust,
  onToggleFullTrust,
  githubStatus,
  onConnectGitHub,
  language,
  onChangeLanguage,
  onLogout,
  serverUrl,
  onChangeServerUrl,
}: Props) {
  const [autoCheckUpdates, setAutoCheckUpdates] = useState(true);
  const [serverUrlInput, setServerUrlInput] = useState(serverUrl);
  const [serverUrlSaving, setServerUrlSaving] = useState(false);
  const [serverUrlError, setServerUrlError] = useState<string | null>(null);

  const isValidServerUrl = (url: string): boolean => {
    try {
      const u = new URL(url);
      return u.protocol === 'https:' || u.protocol === 'http:';
    } catch {
      return false;
    }
  };

  const handleSaveServerUrl = async () => {
    setServerUrlSaving(true);
    setServerUrlError(null);
    const trimmed = serverUrlInput.trim();
    if (!isValidServerUrl(trimmed)) {
      setServerUrlError('请输入有效的 http:// 或 https:// 服务器地址');
      setServerUrlSaving(false);
      return;
    }
    try {
      await onChangeServerUrl(trimmed);
    } catch (err: any) {
      setServerUrlError(err.message || '保存失败');
    } finally {
      setServerUrlSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md bg-slate-800 rounded-lg shadow-xl border border-slate-700 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-700 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-100">设置</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white"
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        <div className="p-5 space-y-6">
          <section>
            <h3 className="text-sm font-medium text-slate-300 mb-3">账号</h3>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-400">已登录</span>
              <button
                type="button"
                onClick={onLogout}
                className="text-red-400 hover:text-red-300"
              >
                退出登录
              </button>
            </div>
          </section>

          <section>
            <h3 className="text-sm font-medium text-slate-300 mb-3">服务器地址</h3>
            <div className="space-y-2">
              <input
                type="text"
                value={serverUrlInput}
                onChange={(e) => setServerUrlInput(e.target.value)}
                placeholder="https://your-server.com"
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-sm text-slate-200 focus:outline-none focus:border-blue-500"
              />
              {serverUrlError && <div className="text-xs text-red-400">{serverUrlError}</div>}
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">修改后需重新登录</span>
                <button
                  type="button"
                  onClick={handleSaveServerUrl}
                  disabled={serverUrlSaving || !serverUrlInput.trim()}
                  className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-600 text-white rounded text-sm transition-colors"
                >
                  {serverUrlSaving ? '保存中...' : '保存'}
                </button>
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-sm font-medium text-slate-300 mb-3">语言</h3>
            <div className="flex gap-2">
              {(['zh', 'en'] as const).map((lang) => (
                <button
                  key={lang}
                  type="button"
                  onClick={() => onChangeLanguage(lang)}
                  className={`px-3 py-1.5 rounded text-sm transition-colors ${
                    language === lang
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {lang === 'zh' ? '中文' : 'English'}
                </button>
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-sm font-medium text-slate-300 mb-3">安全</h3>
            <label className="flex items-center justify-between cursor-pointer group">
              <div>
                <div className={`text-sm ${fullTrust ? 'text-orange-400' : 'text-slate-300'}`}>
                  完全信任模式
                </div>
                <div className="text-xs text-slate-500 mt-0.5">
                  开启后高危操作将自动执行，不再弹窗确认
                </div>
              </div>
              <input
                type="checkbox"
                checked={fullTrust}
                onChange={onToggleFullTrust}
                className="sr-only peer"
              />
              <span
                className={`w-8 h-4 rounded-full relative transition-colors ${
                  fullTrust ? 'bg-orange-500' : 'bg-slate-600'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform ${
                    fullTrust ? 'translate-x-4' : ''
                  }`}
                />
              </span>
            </label>
          </section>

          <section>
            <h3 className="text-sm font-medium text-slate-300 mb-3">GitHub</h3>
            <div className="flex items-center justify-between">
              <div className="text-sm">
                {githubStatus.connected ? (
                  <span className="text-green-400">已连接{githubStatus.scope ? `（${githubStatus.scope}）` : ''}</span>
                ) : (
                  <span className="text-slate-400">未连接</span>
                )}
              </div>
              <button
                type="button"
                onClick={onConnectGitHub}
                className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-sm transition-colors"
              >
                {githubStatus.connected ? '重新授权' : '连接 GitHub'}
              </button>
            </div>
          </section>

          <section>
            <h3 className="text-sm font-medium text-slate-300 mb-3">更新</h3>
            <label className="flex items-center justify-between cursor-pointer group">
              <span className="text-sm text-slate-300">启动时自动检查更新</span>
              <input
                type="checkbox"
                checked={autoCheckUpdates}
                onChange={(e) => setAutoCheckUpdates(e.target.checked)}
                className="sr-only peer"
              />
              <span
                className={`w-8 h-4 rounded-full relative transition-colors ${
                  autoCheckUpdates ? 'bg-blue-500' : 'bg-slate-600'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform ${
                    autoCheckUpdates ? 'translate-x-4' : ''
                  }`}
                />
              </span>
            </label>
          </section>
        </div>

        <div className="px-5 py-4 border-t border-slate-700 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded text-sm transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}

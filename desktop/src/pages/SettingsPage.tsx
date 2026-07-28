import { useState } from 'react';

export interface Props {
  onClose: () => void;
  fullTrust: boolean;
  onToggleFullTrust: () => void;
  githubStatus: { connected: boolean; scope: string; login?: string; avatarUrl?: string; expired?: boolean };
  onConnectGitHub: () => void;
  onDisconnectGitHub: () => void;
  language: 'zh' | 'en';
  onChangeLanguage: (lang: 'zh' | 'en') => void;
  onLogout: () => void;
}

export function SettingsPage({
  onClose,
  fullTrust,
  onToggleFullTrust,
  githubStatus,
  onConnectGitHub,
  onDisconnectGitHub,
  language,
  onChangeLanguage,
  onLogout,
}: Props) {
  const [autoCheckUpdates, setAutoCheckUpdates] = useState(true);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40">
      <div className="w-full max-w-md panel overflow-hidden">
        <div className="px-5 py-4 border-b border-line flex items-center justify-between">
          <h2 className="font-hand text-2xl leading-none text-ink">设置</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-ink-faint hover:text-ink"
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        <div className="p-5 space-y-6">
          <section>
            <h3 className="text-sm font-medium text-ink-soft mb-3">账号</h3>
            <div className="flex items-center justify-between text-sm">
              <span className="text-ink-faint">已登录</span>
              <button
                type="button"
                onClick={onLogout}
                className="text-danger hover:underline"
              >
                退出登录
              </button>
            </div>
          </section>

          <section>
            <h3 className="text-sm font-medium text-ink-soft mb-3">语言</h3>
            <div className="flex gap-2">
              {(['zh', 'en'] as const).map((lang) => (
                <button
                  key={lang}
                  type="button"
                  onClick={() => onChangeLanguage(lang)}
                  className={`px-3 py-1.5 rounded text-sm transition-colors ${
                    language === lang
                      ? 'bg-accent text-white'
                      : 'bg-surface border border-line-strong text-ink-soft hover:bg-paper-sink'
                  }`}
                >
                  {lang === 'zh' ? '中文' : 'English'}
                </button>
              ))}
            </div>
          </section>

          <section>
            <h3 className="text-sm font-medium text-ink-soft mb-3">安全</h3>
            <label className="flex items-center justify-between cursor-pointer group">
              <div>
                <div className={`text-sm ${fullTrust ? 'text-warning font-medium' : 'text-ink-soft'}`}>
                  完全信任模式
                </div>
                <div className="text-xs text-ink-ghost mt-0.5">
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
                  fullTrust ? 'bg-warning' : 'bg-paper-edge'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-3 h-3 bg-surface border border-line-strong rounded-full transition-transform ${
                    fullTrust ? 'translate-x-4' : ''
                  }`}
                />
              </span>
            </label>
          </section>

          <section>
            <h3 className="text-sm font-medium text-ink-soft mb-3">GitHub</h3>
            {githubStatus.connected ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  {githubStatus.avatarUrl ? (
                    <img
                      src={githubStatus.avatarUrl}
                      alt={githubStatus.login || 'GitHub avatar'}
                      className="w-10 h-10 rounded-full border border-line"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-paper-sink border border-line" />
                  )}
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-ink truncate">
                      {githubStatus.login || 'GitHub 用户'}
                    </div>
                    <div className="text-xs text-ink-ghost mt-0.5">
                      已连接{githubStatus.scope ? ` · ${githubStatus.scope}` : ''}
                    </div>
                  </div>
                  <span className="ml-auto inline-flex items-center gap-1 text-xs text-success">
                    <span className="w-2 h-2 rounded-full bg-success inline-block" /> 已授权
                  </span>
                </div>

                {githubStatus.expired && (
                  <div className="flex items-start gap-2 rounded-md bg-danger-soft border border-l-2 border-l-danger px-3 py-2">
                    <span className="text-danger text-sm leading-snug">
                      授权已过期或已被撤销，推送将被拒绝。请重新连接 GitHub 账号后重试。
                    </span>
                    <button
                      type="button"
                      onClick={onConnectGitHub}
                      className="btn-primary text-xs px-2 py-1 shrink-0"
                    >
                      重新连接
                    </button>
                  </div>
                )}

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={onConnectGitHub}
                    className="btn-secondary text-sm px-3 py-1.5"
                  >
                    重新授权
                  </button>
                  <button
                    type="button"
                    onClick={onDisconnectGitHub}
                    className="btn-ghost text-sm px-3 py-1.5 text-danger hover:bg-danger-soft"
                  >
                    断开连接
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between">
                <span className="text-sm text-ink-faint">未连接</span>
                <button
                  type="button"
                  onClick={onConnectGitHub}
                  className="btn-secondary text-sm px-3 py-1.5"
                >
                  连接 GitHub
                </button>
              </div>
            )}
          </section>

          <section>
            <h3 className="text-sm font-medium text-ink-soft mb-3">更新</h3>
            <label className="flex items-center justify-between cursor-pointer group">
              <span className="text-sm text-ink-soft">启动时自动检查更新</span>
              <input
                type="checkbox"
                checked={autoCheckUpdates}
                onChange={(e) => setAutoCheckUpdates(e.target.checked)}
                className="sr-only peer"
              />
              <span
                className={`w-8 h-4 rounded-full relative transition-colors ${
                  autoCheckUpdates ? 'bg-accent' : 'bg-paper-edge'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-3 h-3 bg-surface border border-line-strong rounded-full transition-transform ${
                    autoCheckUpdates ? 'translate-x-4' : ''
                  }`}
                />
              </span>
            </label>
          </section>
        </div>

        <div className="px-5 py-4 border-t border-line flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="btn-secondary text-sm px-4 py-2"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}

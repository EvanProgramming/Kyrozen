import { useCallback, useEffect, useState } from 'react';
import { ChatPage } from './pages/ChatPage';
import { LoginPage } from './pages/LoginPage';
import { OnboardingPage } from './pages/OnboardingPage';
import { SettingsPage } from './pages/SettingsPage';
import { EditorPanel } from './components/EditorPanel';
import { GitPanel } from './components/GitPanel';
import { ProgressPanel } from './components/ProgressPanel';
import { PreviewPanel } from './components/PreviewPanel';
import { SearchPanel } from './components/SearchPanel';
import { ProjectWorkspacePanel } from './components/ProjectWorkspacePanel';

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

interface Project {
  id: string;
  name: string;
  current_stage: string;
  description?: string;
  localOnly?: boolean;
}

interface UpdateStatus {
  status: string;
  message: string;
}

interface QuotaInfo {
  allowed: boolean;
  reason: string;
  used: number;
  limit: number;
  remaining: number;
  plan?: 'free' | 'developer';
  project_limit?: number;
}

interface UserProfile {
  name: string;
  email: string;
  githubUsername: string;
  avatarUrl: string;
}

interface GitHubStatus {
  connected: boolean;
  scope: string;
  login?: string;
  avatarUrl?: string;
  expired?: boolean;
}

const SESSION_HINT_KEY = 'kyrozen:has-saved-session';

function formatQuota(quota: QuotaInfo) {
  if (quota.plan === 'developer') return '开发者账户 · 无限制';
  return `免费账户 · 可完整使用 ${quota.project_limit || 1} 个项目`;
}

function App() {
  const [token, setToken] = useState<string | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaInfo | null>(null);
  const [fullTrust, setFullTrust] = useState(false);
  const [editingFile, setEditingFile] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [onboardingStatus, setOnboardingStatus] = useState<'loading' | 'needed' | 'completed'>('loading');
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [language, setLanguage] = useState<'zh' | 'en'>('zh');
  const [githubStatus, setGithubStatus] = useState<GitHubStatus>({ connected: false, scope: '' });
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);
  // Start in a neutral state. The main process restores credentials
  // asynchronously, so rendering LoginPage immediately causes a distracting
  // login-page flash for returning users.
  const [sessionRestoring, setSessionRestoring] = useState(true);
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [connectionMessage, setConnectionMessage] = useState('正在检查连接状态');
  const [showCreateProject, setShowCreateProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');
  const [newProjectGoal, setNewProjectGoal] = useState('');
  const [creatingProject, setCreatingProject] = useState(false);
  const [createProjectError, setCreateProjectError] = useState('');
  const [showProjectWorkspace, setShowProjectWorkspace] = useState(false);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showFullTrustConfirm, setShowFullTrustConfirm] = useState(false);

  const loadProjects = useCallback(async () => {
    if (!window.kyrozen) return;
    const list = await window.kyrozen.getProjects();
    setProjects(Array.isArray(list) ? list : []);
  }, []);

  const handleCreateProject = async () => {
    if (!window.kyrozen || !newProjectName.trim()) return;
    setCreatingProject(true);
    setCreateProjectError('');
    try {
      const result = await window.kyrozen.createProject(newProjectName.trim(), newProjectDesc.trim(), newProjectGoal.trim());
      if (result.success && result.project) {
        setNewProjectName('');
        setNewProjectDesc('');
        setNewProjectGoal('');
        setShowCreateProject(false);
        await loadProjects();
        await handleSelectProject(result.project.id);
      } else {
        setCreateProjectError(result.error || '项目创建失败');
      }
    } catch (err: any) {
      setCreateProjectError(err.message || '项目创建失败');
    }
    finally { setCreatingProject(false); }
  };

  const loadQuota = async () => {
    if (!window.kyrozen) return;
    try {
      const q = await window.kyrozen.getQuota();
      setQuota(q);
    } catch {
      // quota display is non-critical
    }
  };

  const loadFullTrust = async () => {
    if (!window.kyrozen) return;
    try {
      const t = await window.kyrozen.getFullTrust();
      setFullTrust(t.enabled);
    } catch {
      setFullTrust(false);
    }
  };

  const loadLanguage = async () => {
    if (!window.kyrozen) return;
    try {
      const result = await window.kyrozen.getOnboardingLanguage();
      if (result.language === 'zh' || result.language === 'en') {
        setLanguage(result.language);
      }
    } catch {
      setLanguage('zh');
    }
  };

  const loadGitHubStatus = async () => {
    if (!window.kyrozen) return;
    try {
      const status = await window.kyrozen.getGitHubStatus();
      setGithubStatus((previous) => status.connected ? {
        ...previous,
        connected: true,
        scope: status.scope ?? previous.scope,
        login: status.login ?? previous.login,
        avatarUrl: status.avatarUrl ?? previous.avatarUrl,
        expired: status.expired ?? previous.expired,
      } : { connected: false, scope: status.scope || '' });
    } catch {
      setGithubStatus({ connected: false, scope: '' });
    }
  };

  const handleDisconnectGitHub = async () => {
    if (!window.kyrozen) return;
    try {
      await window.kyrozen.disconnectGitHub();
    } catch {
      /* ignore */
    }
    await loadGitHubStatus();
  };

  const loadUserProfile = async () => {
    if (!window.kyrozen) return;
    try { setUserProfile(await window.kyrozen.getUserProfile()); }
    catch { setUserProfile(null); }
  };

  useEffect(() => {
    if (!window.kyrozen) {
      // Vite/browser previews do not have the Electron preload bridge. Do not
      // leave them on the neutral splash forever; fall back to the signed-out
      // surface so the shell remains inspectable.
      setOnboardingStatus('completed');
      setSessionRestoring(false);
      return;
    }

    let mounted = true;
    let sessionHydrationId = 0;

    const hydrateAuthenticatedSession = async (wsToken: string, preferredProjectId?: string | null) => {
      const hydrationId = ++sessionHydrationId;
      setSessionNotice(null);
      setToken(wsToken);
      setSessionRestoring(true);
      localStorage.setItem(SESSION_HINT_KEY, '1');

      const savedProjectId = preferredProjectId || localStorage.getItem('kyrozen:last-project-id');
      if (savedProjectId) {
        setCurrentProjectId(savedProjectId);
        void window.kyrozen?.setCurrentProject(savedProjectId);
      }

      await Promise.allSettled([
        loadProjects(),
        loadQuota(),
        loadFullTrust(),
        loadGitHubStatus(),
        loadUserProfile(),
        loadLanguage(),
      ]);
      if (mounted && hydrationId === sessionHydrationId) {
        setSessionRestoring(false);
      }
    };

    window.kyrozen
      .getOnboardingStatus()
      .then((status) => {
        setOnboardingStatus(status.completed ? 'completed' : 'needed');
      })
      .catch(() => {
        setOnboardingStatus('completed');
      });

    const unsubProtocolUrl = window.kyrozen.onProtocolUrl(async (url: string) => {
      const params = new URL(url).searchParams;
      const openToken = params.get('token');
      const projectId = params.get('project_id');
      if (openToken && window.kyrozen) {
        const verified = await window.kyrozen.verifyOpenToken(openToken);
        if (verified) {
          if (projectId) {
            localStorage.setItem('kyrozen:last-project-id', projectId);
          }
          void hydrateAuthenticatedSession(verified.wsToken, projectId);
        }
      }
    });

    const unsubSessionResumed = window.kyrozen.onSessionResumed((token: string) => {
      void hydrateAuthenticatedSession(token);
    });

    const unsubSessionEnded = window.kyrozen.onSessionEnded(() => {
      setToken(null);
      setProjects([]);
      setCurrentProjectId(null);
      setQuota(null);
      setFullTrust(false);
      setGithubStatus({ connected: false, scope: '' });
      setUserProfile(null);
      setSessionRestoring(false);
      localStorage.removeItem(SESSION_HINT_KEY);
      localStorage.removeItem('kyrozen:last-project-id');
    });

    const unsubSessionExpired = window.kyrozen.onSessionExpired((message: string) => {
      // P0-16: 会话失效时立即回到登录页，不再显示带旧数据的主界面。
      setToken(null);
      setProjects([]);
      setCurrentProjectId(null);
      setQuota(null);
      setFullTrust(false);
      setGithubStatus({ connected: false, scope: '' });
      setUserProfile(null);
      setSessionRestoring(false);
      localStorage.removeItem(SESSION_HINT_KEY);
      localStorage.removeItem('kyrozen:last-project-id');
      setSessionNotice(message || '登录已过期，请重新登录。');
    });

    const unsubOpenSettings = window.kyrozen.onOpenSettings(() => {
      setShowUserMenu(false);
      setShowSettings(true);
    });

    const unsubOpenPreviewUrl = window.kyrozen.onOpenPreviewUrl((url: string) => {
      setPreviewUrl(url);
    });

    const unsubFullTrustChange = window.kyrozen.onFullTrustChange((status) => {
      setFullTrust(status.enabled);
    });

    const unsubGitHubStatus = window.kyrozen.onGitHubStatus((status) => {
      // Some main-process notifications only carry connected/scope. Preserve
      // the last known identity fields, then immediately request the complete,
      // validated status so Settings and the account menu update without a
      // project switch or reload.
      setGithubStatus((previous) => status.connected ? {
        ...previous,
        ...status,
        connected: true,
        scope: status.scope ?? previous.scope,
      } : { connected: false, scope: status.scope || '' });
      void loadGitHubStatus();
    });

    const unsubConnectionChange = window.kyrozen.onConnectionChange((state, message) => {
      setConnectionState(state);
      setConnectionMessage(message || '');
    });

    const unsubUpdateStatus = window.kyrozen.onUpdateStatus((status) => {
      setUpdateStatus(status);
    });

    // Automatically check for updates a few seconds after startup.
    const updateTimer = setTimeout(() => {
      window.kyrozen?.checkForUpdates().catch(() => {
        // update check is non-critical
      });
    }, 5000);

    let initialSessionTimer: number | null = null;
    let initialSessionAttempts = 0;
    const expectsSavedSession = localStorage.getItem(SESSION_HINT_KEY) === '1'
      || Boolean(localStorage.getItem('kyrozen:last-project-id'));
    // A known saved session gets a longer window for credential refresh. A
    // truly signed-out user reaches LoginPage quickly instead of waiting for
    // the full recovery window. Both paths are explicitly bounded.
    const maxInitialSessionAttempts = expectsSavedSession ? 30 : 4;
    const hydrateInitialSession = () => window.kyrozen?.getInitialSession().then((session) => {
      if (!mounted) return;
      if (!session) {
        setSessionRestoring(false);
        return;
      }
      setConnectionState(session.connection);
      setConnectionMessage(session.message || '');
      if (session?.wsToken) {
        void hydrateAuthenticatedSession(session.wsToken, session.currentProjectId);
        window.kyrozen?.requestInitialToken();
      } else if (initialSessionAttempts < maxInitialSessionAttempts) {
        initialSessionAttempts += 1;
        window.kyrozen?.requestInitialToken();
        initialSessionTimer = window.setTimeout(hydrateInitialSession, 1000);
      } else {
        setSessionRestoring(false);
      }
    }).catch(() => {
      if (!mounted) return;
      initialSessionAttempts += 1;
      if (initialSessionAttempts < maxInitialSessionAttempts) {
        window.kyrozen?.requestInitialToken();
        initialSessionTimer = window.setTimeout(hydrateInitialSession, 1000);
      } else {
        setSessionRestoring(false);
      }
    });
    void hydrateInitialSession();

    return () => {
      mounted = false;
      clearTimeout(updateTimer);
      if (initialSessionTimer != null) window.clearTimeout(initialSessionTimer);
      unsubProtocolUrl();
      unsubSessionResumed();
      unsubSessionEnded();
      unsubSessionExpired();
      unsubOpenSettings();
      unsubOpenPreviewUrl();
      unsubFullTrustChange();
      unsubGitHubStatus();
      unsubConnectionChange();
      unsubUpdateStatus();
    };
  }, []);

  const handleOnboardingComplete = async () => {
    setOnboardingStatus('completed');
    await loadProjects();
    await loadQuota();
    await loadFullTrust();
    await loadLanguage();
    await loadGitHubStatus();
    await loadUserProfile();
    setSessionRestoring(false);
  };

  const handleToggleFullTrust = async () => {
    if (!window.kyrozen) return;
    const next = !fullTrust;
    if (next) {
      setShowUserMenu(false);
      setShowFullTrustConfirm(true);
      return;
    }
    const result = await window.kyrozen.setFullTrust(next);
    setFullTrust(result.enabled);
  };

  const enableFullTrust = async () => {
    if (!window.kyrozen) return;
    const result = await window.kyrozen.setFullTrust(true);
    setFullTrust(result.enabled);
    setShowFullTrustConfirm(false);
  };

  const handleSelectProject = async (projectId: string) => {
    if (!window.kyrozen) return;
    await window.kyrozen.setCurrentProject(projectId);
    setCurrentProjectId(projectId);
    localStorage.setItem('kyrozen:last-project-id', projectId);
    setPreviewUrl(null);
    setEditingFile(null);
    setShowProjectWorkspace(false);
  };

  const handleOpenPreview = (url: string) => {
    setPreviewUrl(url);
  };

  const handleOpenFileFromSearch = async (projectId: string, relativePath: string) => {
    if (projectId !== currentProjectId) {
      await handleSelectProject(projectId);
    }
    setEditingFile(relativePath);
  };

  const handleImportLocalProject = async () => {
    if (!window.kyrozen) return;
    try {
      const imported = await window.kyrozen.importLocalProject();
      if (!imported) {
        return;
      }
      const project: Project = {
        id: imported.projectId,
        name: imported.name,
        current_stage: '本地导入',
        localOnly: true,
      };
      setProjects((prev) => [...prev, project]);
      await handleSelectProject(project.id);
    } catch {
      // import failure is non-critical; nothing to display in UI
    }
  };

  const handleChangeLanguage = async (lang: 'zh' | 'en') => {
    if (!window.kyrozen) return;
    await window.kyrozen.saveOnboardingLanguage(lang);
    setLanguage(lang);
  };

  const handleConnectGitHub = async () => {
    if (!window.kyrozen) return;
    const result = await window.kyrozen.connectGitHub();
    if (result?.success) {
      await loadGitHubStatus();
    }
  };

  const handleLogout = async () => {
    if (!window.kyrozen) return;
    await window.kyrozen.logout();
    setShowSettings(false);
  };

  if (onboardingStatus === 'loading') {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-paper text-ink">
        <div className="text-center">
          <div className="font-display text-3xl">Kyrozen</div>
          <div className="text-sm text-ink-faint mt-2">正在初始化...</div>
        </div>
      </div>
    );
  }

  if (onboardingStatus === 'needed') {
    return <OnboardingPage onComplete={handleOnboardingComplete} />;
  }

  if (!token) {
    if (sessionRestoring) {
      return (
        <div className="h-screen w-screen flex items-center justify-center bg-paper text-ink" role="status" aria-live="polite">
          <div className="text-center">
            <div className="font-display text-3xl">Kyrozen</div>
            <div className="text-sm text-ink-faint mt-2">正在检查登录状态...</div>
          </div>
        </div>
      );
    }
    return (
      <div className="h-screen w-screen flex flex-col bg-paper">
        <LoginPage notice={sessionNotice} />
      </div>
    );
  }

  // P0-16: show loading overlay while session state hydrates to prevent the
  // 4-second window of stale free-account / disabled-state UI.
  if (sessionRestoring) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-paper text-ink">
        <div className="text-center">
          <div className="font-display text-3xl">Kyrozen</div>
          <div className="text-sm text-ink-faint mt-2">正在恢复项目数据...</div>
        </div>
      </div>
    );
  }

  const currentProject = projects.find((p) => p.id === currentProjectId);
  const canCreateProject = quota?.plan === 'developer' || projects.length < (quota?.project_limit || 1);
  const connectionPresentation: Record<ConnectionState, { className: string; label: string }> = {
    connected: { className: 'bg-success', label: '云端已连接' },
    connecting: { className: 'bg-warning', label: '正在连接云端' },
    error: { className: 'bg-danger', label: '连接异常' },
    disconnected: { className: 'bg-ink-ghost', label: '云端未连接' },
  };
  const visibleConnection = connectionPresentation[connectionState];

  return (
    <div className="h-screen w-screen flex flex-col bg-paper text-ink">
      <div
        className={`h-7 flex-shrink-0 px-4 flex items-center justify-center text-xs text-white ${visibleConnection.className}`}
        role="status"
        aria-live="polite"
        title={connectionMessage || visibleConnection.label}
        data-testid="connection-status"
      >
        <span className="font-medium">{visibleConnection.label}</span>
        {connectionMessage && connectionMessage !== visibleConnection.label && (
          <span className="ml-1 opacity-90 truncate">· {connectionMessage}</span>
        )}
      </div>
      <header className="app-drag h-12 border-b border-line bg-surface flex items-center justify-between pl-20 pr-4 flex-shrink-0">
        <div className="flex items-center gap-3 app-no-drag">
          <span className="font-display text-2xl leading-none text-ink">Kyrozen</span>
          {currentProject && (
            <select
              value={currentProjectId || ''}
              onChange={(e) => handleSelectProject(e.target.value)}
              className="bg-surface border border-line-strong text-ink-soft text-xs rounded px-2 py-1 focus:outline-none focus:border-accent"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="flex items-center gap-3 app-no-drag">
          {currentProjectId && (
            <button
              type="button"
              onClick={() => { setShowUserMenu(false); setShowProjectWorkspace(true); }}
              className="btn-primary text-xs px-3 py-1.5"
            >
              项目画布
            </button>
          )}
          <button
            type="button"
            onClick={() => { setShowUserMenu(false); setShowSettings(true); }}
            className="btn-secondary text-xs px-3 py-1.5"
          >
            设置
          </button>
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowUserMenu((value) => !value)}
              className="w-7 h-7 rounded-full overflow-hidden bg-accent flex items-center justify-center text-xs font-medium text-white border border-line-strong"
              aria-label={`${userProfile?.name || 'Kyrozen 用户'}的 Kyrozen 账号菜单`}
              aria-expanded={showUserMenu}
            >
              {userProfile?.avatarUrl ? (
                <img src={userProfile.avatarUrl} alt={userProfile.name} className="w-full h-full object-cover" />
              ) : (userProfile?.name || 'K').slice(0, 1).toUpperCase()}
            </button>
            {showUserMenu && (
              <div className="absolute right-0 top-9 z-40 w-56 panel p-2">
                <div className="px-2 py-2 border-b border-line">
                  <div className="text-[11px] text-ink-faint mb-1">Kyrozen 账号</div>
                  <div className="text-sm font-medium truncate">{userProfile?.name || 'Kyrozen 用户'}</div>
                  <div className="text-xs text-ink-faint truncate">{userProfile?.email || '已登录'}</div>
                </div>
                <div className="px-2 py-2 border-b border-line">
                  <div className="text-[11px] text-ink-faint mb-1">GitHub 授权</div>
                  <div className={`text-xs ${githubStatus.connected && !githubStatus.expired ? 'text-success' : githubStatus.expired ? 'text-danger' : 'text-ink-faint'}`}>
                    {githubStatus.expired
                      ? '授权已过期'
                      : githubStatus.connected
                        ? `已授权${githubStatus.login ? ` · @${githubStatus.login}` : ''}`
                        : '未授权（不影响 Kyrozen 登录）'}
                  </div>
                </div>
                <button type="button" onClick={() => { setShowUserMenu(false); void handleLogout(); }} className="btn-ghost w-full text-sm text-danger mt-1 justify-start">
                  退出登录
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <div className="flex-1 flex overflow-hidden">
        <aside data-testid="project-list" className="w-64 flex-shrink-0 border-r border-line bg-paper-sink flex flex-col">
          <div className="p-4 border-b border-line flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <h2 className="font-display text-lg leading-none text-ink" aria-label={`我的项目，共 ${projects.length} 个`}>
                我的项目
              </h2>
              <span className="text-[11px] text-ink-faint" aria-hidden="true">{projects.length}</span>
              {/* UI cleanup: cross-project search condensed into a small icon
                  next to "我的项目"; click to expand the input below. */}
              <button
                type="button"
                onClick={() => setShowSearch((value) => !value)}
                title="跨项目搜索"
                aria-label="跨项目搜索"
                aria-expanded={showSearch}
                className={`p-1 rounded-sm transition-colors ${showSearch ? 'text-accent bg-accent-soft' : 'text-ink-faint hover:text-ink'}`}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" className="w-3.5 h-3.5" aria-hidden>
                  <circle cx="11" cy="11" r="7" />
                  <path d="M20 20l-3.5-3.5" />
                </svg>
              </button>
            </div>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => { setShowUserMenu(false); setShowCreateProject(true); }}
                title={canCreateProject ? '创建新项目' : '免费账户可完整使用一个项目'}
                className="btn-primary text-xs px-2 py-1"
                disabled={!canCreateProject}
              >
                新建
              </button>
              <button
                type="button"
                onClick={handleImportLocalProject}
                title="导入已有本地目录"
                className="btn-ghost text-xs px-2 py-1"
              >
                导入
              </button>
            </div>
          </div>
          {showSearch && (
            <div className="border-b border-line text-xs">
              <SearchPanel onOpenFile={handleOpenFileFromSearch} />
            </div>
          )}
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {projects.length === 0 && (
              <div className="text-xs text-ink-faint p-2">暂无项目</div>
            )}
            {projects.map((project) => (
              <button
                key={project.id}
                onClick={() => handleSelectProject(project.id)}
                className={`w-full text-left px-3 py-2 rounded-sm text-sm transition-colors border-l-2 ${
                  project.id === currentProjectId
                    ? 'bg-accent-soft border-accent text-ink'
                    : 'border-transparent text-ink-soft hover:bg-paper-edge'
                }`}
              >
                <div className="font-medium truncate">{project.name}</div>
                <div className="text-xs text-ink-faint truncate">
                  {project.current_stage}
                </div>
              </button>
            ))}
          </div>

          {/* UI cleanup: 本地文件 / 硬件工具链 moved into 设置; 会员权益 sits at the
              bottom-left corner of the sidebar. */}
          <div className="p-3 border-t border-line space-y-3 text-xs">
            <label className="flex items-center justify-between cursor-pointer group">
              <span className={`${fullTrust ? 'text-warning font-medium' : 'text-ink-soft'}`}>
                完全信任模式
              </span>
              <input
                type="checkbox"
                checked={fullTrust}
                onChange={handleToggleFullTrust}
                className="sr-only peer"
              />
              <span className={`w-8 h-4 rounded-full relative transition-colors ${
                fullTrust ? 'bg-warning' : 'bg-paper-edge'
              }`}>
                <span className={`absolute top-0.5 left-0.5 w-3 h-3 bg-surface border border-line-strong rounded-full transition-transform ${
                  fullTrust ? 'translate-x-4' : ''
                }`} />
              </span>
            </label>
            {fullTrust && (
              <div className="text-warning">
                高危操作将自动执行，不再确认。
              </div>
            )}

            {quota && (
              <div className="text-ink-soft border-t border-line pt-3" title={quota.reason}>
                <div className="font-medium mb-1">会员权益</div>
                <div className="text-ink-faint">{formatQuota(quota)}</div>
              </div>
            )}
          </div>
        </aside>
        <main className="flex-1 flex flex-col overflow-hidden relative">
          {updateStatus && updateStatus.status !== 'up-to-date' && (
            <div className="px-4 py-2 bg-accent-soft border-b border-line text-sm flex items-center justify-between">
              <div className="text-accent text-xs">{updateStatus.message}</div>
              <button
                type="button"
                onClick={() => setUpdateStatus(null)}
                className="text-accent hover:text-accent-deep text-xs"
                aria-label="关闭更新提示"
              >
                ×
              </button>
            </div>
          )}
          {currentProject && (
            <div className="px-4 py-2 bg-surface border-b border-line text-sm text-ink-soft">
              当前项目：<span className="font-medium text-ink">{currentProject.name}</span>
              <span className="ml-2 text-ink-faint text-xs">{currentProject.current_stage}</span>
            </div>
          )}
          <div className="flex-1 flex overflow-hidden">
            <ChatPage projectId={currentProjectId} onOpenPreview={handleOpenPreview} onProjectChanged={loadProjects} />
            {previewUrl && <PreviewPanel url={previewUrl} onClose={() => setPreviewUrl(null)} />}
          </div>
          {currentProjectId && editingFile && (
            <EditorPanel
              projectId={currentProjectId}
              relativePath={editingFile}
              onClose={() => setEditingFile(null)}
            />
          )}
          {currentProjectId && showProjectWorkspace && (
            <ProjectWorkspacePanel
              projectId={currentProjectId}
              onClose={() => setShowProjectWorkspace(false)}
            />
          )}
        </main>
        <div className="w-72 flex-shrink-0 h-full border-l border-line bg-surface overflow-y-auto flex flex-col">
          {currentProjectId && <ProgressPanel projectId={currentProjectId} />}
          <GitPanel projectId={currentProjectId} />
        </div>
      </div>
      {showCreateProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40" role="dialog" aria-modal="true" aria-labelledby="create-project-title">
          <div className="w-full max-w-sm panel p-6">
            <h2 id="create-project-title" className="font-display text-2xl text-ink mb-4">新建项目</h2>
            <div className="space-y-3">
              <div>
                <label className="label">项目名称 *</label>
                <input
                  type="text"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  placeholder="例如：AI 写作助手"
                  className="input"
                  autoFocus
                  onKeyDown={(e) => e.key === 'Enter' && handleCreateProject()}
                />
              </div>
              <div>
                <label className="label">描述（可选）</label>
                <input
                  type="text"
                  value={newProjectDesc}
                  onChange={(e) => setNewProjectDesc(e.target.value)}
                  placeholder="简短描述这个项目"
                  className="input"
                />
              </div>
              <div>
                <label className="label">目标（可选）</label>
                <textarea
                  value={newProjectGoal}
                  onChange={(e) => setNewProjectGoal(e.target.value)}
                  placeholder="你想用这个项目达成什么目标？"
                  rows={2}
                  className="input resize-none"
                />
              </div>
            </div>
            {createProjectError && (
              <div role="alert" className="mt-3 text-sm text-danger">{createProjectError}</div>
            )}
            <div className="flex justify-end gap-2 mt-5">
              <button
                type="button"
                onClick={() => { setShowCreateProject(false); setNewProjectName(''); setNewProjectDesc(''); setNewProjectGoal(''); setCreateProjectError(''); }}
                className="btn-ghost text-sm"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleCreateProject}
                disabled={creatingProject || !newProjectName.trim()}
                className="btn-primary text-sm"
              >
                {creatingProject ? '创建中...' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}
      {showSettings && (
        <SettingsPage
          onClose={() => setShowSettings(false)}
          fullTrust={fullTrust}
          onToggleFullTrust={handleToggleFullTrust}
          githubStatus={githubStatus}
          onConnectGitHub={handleConnectGitHub}
          onDisconnectGitHub={handleDisconnectGitHub}
          language={language}
          onChangeLanguage={handleChangeLanguage}
          onLogout={handleLogout}
          projectId={currentProjectId}
          onOpenLocalFile={(relativePath) => {
            setEditingFile(relativePath);
            setShowSettings(false);
          }}
        />
      )}
      {showFullTrustConfirm && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/40" role="dialog" aria-modal="true" aria-labelledby="full-trust-title">
          <div className="panel w-full max-w-md p-5">
            <h2 id="full-trust-title" className="font-display text-2xl">开启完全信任模式？</h2>
            <p className="text-sm text-ink-soft mt-2">本次会话内，文件写入和命令执行等高风险操作将自动继续，不再逐次询问。</p>
            <div className="flex justify-end gap-2 mt-5">
              <button type="button" onClick={() => setShowFullTrustConfirm(false)} className="btn-ghost text-sm" autoFocus>取消</button>
              <button type="button" onClick={() => void enableFullTrust()} className="btn-primary text-sm">确认开启</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;

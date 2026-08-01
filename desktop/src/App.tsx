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
  local_only?: boolean;
}

interface ProjectContextMenuState {
  project: Project;
  x: number;
  y: number;
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

function formatQuota(quota: QuotaInfo) {
  if (quota.plan === 'developer') return '开发者账户 · 无限制';
  return `免费账户 · 可完整使用 ${quota.project_limit || 1} 个项目`;
}

const PROJECT_STAGE_LABELS: Record<string, string> = {
  problem_discovery: '问题探索',
  market_research: '市场调研',
  product_definition: '产品定义',
  solution_design: '方案设计',
  development: '软件开发',
  hardware_development: '硬件开发',
  testing: '测试验证',
  iteration: '迭代改进',
};

function projectStageLabel(stage: string): string {
  return PROJECT_STAGE_LABELS[stage] || '进行中';
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
  const [githubStatus, setGithubStatus] = useState<{ connected: boolean; scope: string; login?: string; avatarUrl?: string; expired?: boolean }>({ connected: false, scope: '' });
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);
  // P0-16: prevent the 4-second window where the UI shows free-account
  // restrictions before quota / fullTrust / gitHubStatus finish loading.
  const [sessionRestoring, setSessionRestoring] = useState(false);
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
  const [projectContextMenu, setProjectContextMenu] = useState<ProjectContextMenuState | null>(null);
  const [renameTarget, setRenameTarget] = useState<Project | null>(null);
  const [renameName, setRenameName] = useState('');
  const [renameBusy, setRenameBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [projectActionNotice, setProjectActionNotice] = useState<string | null>(null);

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
      setGithubStatus({
        connected: status.connected,
        scope: status.scope || '',
        login: status.login,
        avatarUrl: status.avatarUrl,
        expired: status.expired,
      });
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
    if (!window.kyrozen) return;

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
          setToken(verified.wsToken);
          void loadProjects();
          void loadUserProfile();
          if (projectId) {
            setCurrentProjectId(projectId);
            localStorage.setItem('kyrozen:last-project-id', projectId);
            void window.kyrozen.setCurrentProject(projectId);
          }
        }
      }
    });

    const unsubSessionResumed = window.kyrozen.onSessionResumed((token: string) => {
      setSessionNotice(null);
      setToken(token);
      setSessionRestoring(true);
      const savedProjectId = localStorage.getItem('kyrozen:last-project-id');
      if (savedProjectId) {
        setCurrentProjectId(savedProjectId);
        void window.kyrozen?.setCurrentProject(savedProjectId);
      }
      // Load all panels; hide the loading screen only after everything settles.
      Promise.all([
        loadProjects(),
        loadQuota(),
        loadGitHubStatus(),
        loadUserProfile(),
        loadLanguage(),
      ]).finally(() => setSessionRestoring(false));
      loadFullTrust(); // non-blocking
    });

    const unsubSessionEnded = window.kyrozen.onSessionEnded(() => {
      setToken(null);
      setProjects([]);
      setCurrentProjectId(null);
      setQuota(null);
      setFullTrust(false);
      setGithubStatus({ connected: false, scope: '' });
      setUserProfile(null);
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
      localStorage.removeItem('kyrozen:last-project-id');
      setSessionNotice(message || '登录已过期，请重新登录。');
    });

    const unsubOpenSettings = window.kyrozen.onOpenSettings(() => {
      setShowSettings(true);
    });

    const unsubOpenPreviewUrl = window.kyrozen.onOpenPreviewUrl((url: string) => {
      setPreviewUrl(url);
    });

    const unsubFullTrustChange = window.kyrozen.onFullTrustChange((status) => {
      setFullTrust(status.enabled);
    });

    const unsubGitHubStatus = window.kyrozen.onGitHubStatus((status) => {
      setGithubStatus({ connected: status.connected, scope: status.scope || '' });
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
    const hydrateInitialSession = () => window.kyrozen?.getInitialSession().then((session) => {
      if (session?.wsToken) {
        setToken(session.wsToken);
        const savedProjectId = session.currentProjectId || localStorage.getItem('kyrozen:last-project-id');
        if (savedProjectId) {
          setCurrentProjectId(savedProjectId);
          void window.kyrozen?.setCurrentProject(savedProjectId);
        }
        void loadProjects();
        void loadQuota();
        void loadFullTrust();
        void loadLanguage();
        void loadGitHubStatus();
        void loadUserProfile();
        window.kyrozen?.requestInitialToken();
      } else if (initialSessionAttempts < 30) {
        initialSessionAttempts += 1;
        window.kyrozen?.requestInitialToken();
        initialSessionTimer = window.setTimeout(hydrateInitialSession, 1000);
      }
    }).catch(() => {
      window.kyrozen?.requestInitialToken();
    });
    void hydrateInitialSession();

    return () => {
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
      unsubUpdateStatus();
    };
  }, []);

  useEffect(() => {
    if (!projectContextMenu) return;
    const closeMenu = () => setProjectContextMenu(null);
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeMenu();
    };
    window.addEventListener('click', closeMenu);
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      window.removeEventListener('click', closeMenu);
      window.removeEventListener('keydown', closeOnEscape);
    };
  }, [projectContextMenu]);

  const handleOnboardingComplete = async () => {
    setOnboardingStatus('completed');
    await loadProjects();
    await loadQuota();
    await loadFullTrust();
    await loadLanguage();
    await loadGitHubStatus();
    await loadUserProfile();
  };

  const handleToggleFullTrust = async () => {
    if (!window.kyrozen) return;
    const next = !fullTrust;
    if (next) {
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
    setProjectContextMenu(null);
  };

  const handleResumeLastProject = async () => {
    const lastProjectId = localStorage.getItem('kyrozen:last-project-id');
    if (!lastProjectId) return;
    const lastProject = projects.find((project) => project.id === lastProjectId);
    if (lastProject) {
      await handleSelectProject(lastProject.id);
    }
  };

  const handleRenameProject = async () => {
    if (!window.kyrozen || !renameTarget || !renameName.trim() || renameBusy) return;
    setRenameBusy(true);
    setProjectActionNotice(null);
    try {
      const result = await window.kyrozen.renameProject(renameTarget.id, renameName.trim());
      if (!result.success) {
        setProjectActionNotice(result.error || '重命名失败');
        return;
      }
      await loadProjects();
      setRenameTarget(null);
    } catch (err: any) {
      setProjectActionNotice(err.message || '重命名失败');
    } finally {
      setRenameBusy(false);
    }
  };

  const handleDeleteProject = async () => {
    if (!window.kyrozen || !deleteTarget || deleteBusy) return;
    setDeleteBusy(true);
    setProjectActionNotice(null);
    try {
      const result = await window.kyrozen.deleteProject(deleteTarget.id);
      if (!result.success) {
        setProjectActionNotice(result.error || '删除失败');
        return;
      }
      setProjects((prev) => prev.filter((project) => project.id !== deleteTarget.id));
      if (currentProjectId === deleteTarget.id) {
        setCurrentProjectId(null);
        setPreviewUrl(null);
        setEditingFile(null);
        setShowProjectWorkspace(false);
        localStorage.removeItem('kyrozen:last-project-id');
      }
      setDeleteTarget(null);
    } catch (err: any) {
      setProjectActionNotice(err.message || '删除失败');
    } finally {
      setDeleteBusy(false);
    }
  };

  const handleOpenProjectInFinder = async (project: Project) => {
    if (!window.kyrozen) return;
    setProjectContextMenu(null);
    const result = await window.kyrozen.openProjectInFinder(project.id);
    if (!result.success) setProjectActionNotice(result.error || '无法在 Finder 中打开项目');
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
    return (
      <div className="h-screen w-screen flex flex-col bg-paper">
        {sessionRestoring && (
          <div className="absolute inset-0 z-50 flex items-center justify-center bg-paper">
            <div className="text-center">
              <div className="font-display text-3xl">Kyrozen</div>
              <div className="text-sm text-ink-faint mt-2">正在恢复会话...</div>
            </div>
          </div>
        )}
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
  const lastProjectId = localStorage.getItem('kyrozen:last-project-id');
  const lastProject = projects.find((project) => project.id === lastProjectId);
  const canCreateProject = quota?.plan === 'developer' || projects.length < (quota?.project_limit || 1);

  return (
    <div className="h-screen w-screen flex flex-col bg-paper text-ink">
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
              onClick={() => setShowProjectWorkspace(true)}
              className="btn-primary text-xs px-3 py-1.5"
            >
              项目画布
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowSettings(true)}
            className="btn-secondary text-xs px-3 py-1.5"
          >
            设置
          </button>
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowUserMenu((value) => !value)}
              className="w-7 h-7 rounded-full overflow-hidden bg-accent flex items-center justify-center text-xs font-medium text-white border border-line-strong"
              aria-label="用户菜单"
              aria-expanded={showUserMenu}
            >
              {userProfile?.avatarUrl ? (
                <img src={userProfile.avatarUrl} alt={userProfile.name} className="w-full h-full object-cover" />
              ) : (userProfile?.name || 'K').slice(0, 1).toUpperCase()}
            </button>
            {showUserMenu && (
              <div className="absolute right-0 top-9 z-40 w-56 panel p-2">
                <div className="px-2 py-2 border-b border-line">
                  <div className="text-sm font-medium truncate">{userProfile?.name || 'Kyrozen 用户'}</div>
                  <div className="text-xs text-ink-faint truncate">{userProfile?.githubUsername ? `@${userProfile.githubUsername}` : userProfile?.email}</div>
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
              <h2 className="font-display text-lg leading-none text-ink">我的项目</h2>
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
                onClick={() => setShowCreateProject(true)}
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
          {projectActionNotice && (
            <div role="alert" className="mx-2 mt-2 rounded-sm border border-danger/30 bg-danger-soft px-2 py-1.5 text-xs text-danger">
              {projectActionNotice}
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
                onContextMenu={(event) => {
                  event.preventDefault();
                  setProjectActionNotice(null);
                  setProjectContextMenu({
                    project,
                    x: Math.min(event.clientX, window.innerWidth - 220),
                    y: Math.min(event.clientY, window.innerHeight - 150),
                  });
                }}
                className={`w-full text-left px-3 py-2 rounded-sm text-sm transition-colors border-l-2 ${
                  project.id === currentProjectId
                    ? 'bg-accent-soft border-accent text-ink'
                    : 'border-transparent text-ink-soft hover:bg-paper-edge'
                }`}
              >
                <div className="font-medium truncate">{project.name}</div>
                <div className="text-xs text-ink-faint truncate">
                  {projectStageLabel(project.current_stage)}
                </div>
              </button>
            ))}
          </div>
          {projectContextMenu && (
            <div
              className="fixed z-50 w-52 panel p-1 shadow-lg"
              style={{ left: projectContextMenu.x, top: projectContextMenu.y }}
              onClick={(event) => event.stopPropagation()}
              onContextMenu={(event) => event.preventDefault()}
            >
              <div className="px-3 py-2 border-b border-line text-xs text-ink-faint truncate">
                {projectContextMenu.project.name}
              </div>
              <button
                type="button"
                className="btn-ghost w-full justify-start text-sm"
                onClick={() => {
                  const project = projectContextMenu.project;
                  setProjectContextMenu(null);
                  setRenameTarget(project);
                  setRenameName(project.name);
                }}
              >
                重命名
              </button>
              <button
                type="button"
                className="btn-ghost w-full justify-start text-sm"
                onClick={() => void handleOpenProjectInFinder(projectContextMenu.project)}
              >
                在 Finder 中打开
              </button>
              <button
                type="button"
                className="btn-ghost w-full justify-start text-sm text-danger hover:bg-danger-soft"
                onClick={() => {
                  const project = projectContextMenu.project;
                  setProjectContextMenu(null);
                  setDeleteTarget(project);
                }}
              >
                删除
              </button>
            </div>
          )}

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
          <div className="flex-1 flex overflow-hidden">
            {currentProjectId ? (
              <ChatPage projectId={currentProjectId} onOpenPreview={handleOpenPreview} onProjectChanged={loadProjects} />
            ) : (
              <div className="flex-1 flex items-center justify-center bg-paper p-8" data-testid="welcome-home">
                <div className="w-full max-w-lg text-center">
                  <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent text-white shadow-sm">
                    <span className="font-display text-3xl">K</span>
                  </div>
                  <h1 className="font-display text-4xl leading-tight text-ink">Kyrozen</h1>
                  <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-ink-soft">
                    从一个想法开始，逐步把它变成清晰、可执行、可验证的成果。
                  </p>
                  <div className="mt-7 flex flex-col items-center justify-center gap-3 sm:flex-row">
                    <button
                      type="button"
                      onClick={() => void handleResumeLastProject()}
                      disabled={!lastProject}
                      className="btn-secondary min-w-40 text-sm disabled:cursor-not-allowed disabled:opacity-45"
                      title={lastProject ? `打开 ${lastProject.name}` : '暂无上次打开的项目'}
                    >
                      继续上次项目
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowCreateProject(true)}
                      className="btn-primary min-w-40 text-sm"
                    >
                      创建新项目
                    </button>
                  </div>
                </div>
              </div>
            )}
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40">
          <div className="w-full max-w-sm panel p-6">
            <h2 className="font-display text-2xl text-ink mb-4">新建项目</h2>
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
      {renameTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40" role="dialog" aria-modal="true" aria-labelledby="rename-project-title">
          <div className="w-full max-w-sm panel p-5">
            <h2 id="rename-project-title" className="font-display text-2xl text-ink">重命名项目</h2>
            <p className="text-sm text-ink-soft mt-2">修改左侧项目列表中的显示名称。</p>
            <input
              autoFocus
              value={renameName}
              onChange={(event) => setRenameName(event.target.value)}
              onKeyDown={(event) => { if (event.key === 'Enter') void handleRenameProject(); }}
              className="input mt-4"
              maxLength={80}
              aria-label="项目名称"
            />
            {projectActionNotice && <div role="alert" className="mt-3 text-sm text-danger">{projectActionNotice}</div>}
            <div className="flex justify-end gap-2 mt-5">
              <button type="button" className="btn-ghost text-sm" onClick={() => setRenameTarget(null)} disabled={renameBusy}>取消</button>
              <button type="button" className="btn-primary text-sm" onClick={() => void handleRenameProject()} disabled={renameBusy || !renameName.trim()}>
                {renameBusy ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40" role="dialog" aria-modal="true" aria-labelledby="delete-project-title">
          <div className="w-full max-w-md panel p-5">
            <h2 id="delete-project-title" className="font-display text-2xl text-ink">删除项目？</h2>
            <p className="text-sm text-ink-soft mt-3">
              确定要删除“<span className="font-medium text-ink">{deleteTarget.name}</span>”吗？云端项目、聊天记录和阶段数据将被删除。
            </p>
            <p className="text-xs text-ink-faint mt-2">本地工作区文件会保留，不会被删除。</p>
            {projectActionNotice && <div role="alert" className="mt-3 text-sm text-danger">{projectActionNotice}</div>}
            <div className="flex justify-end gap-2 mt-5">
              <button type="button" className="btn-ghost text-sm" onClick={() => setDeleteTarget(null)} disabled={deleteBusy}>取消</button>
              <button type="button" className="btn-primary text-sm bg-danger hover:bg-danger/90" onClick={() => void handleDeleteProject()} disabled={deleteBusy}>
                {deleteBusy ? '删除中…' : '确认删除'}
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40">
          <div className="panel w-full max-w-md p-5">
            <h2 className="font-display text-2xl">开启完全信任模式？</h2>
            <p className="text-sm text-ink-soft mt-2">本次会话内，文件写入和命令执行等高风险操作将自动继续，不再逐次询问。</p>
            <div className="flex justify-end gap-2 mt-5">
              <button type="button" onClick={() => setShowFullTrustConfirm(false)} className="btn-ghost text-sm">取消</button>
              <button type="button" onClick={() => void enableFullTrust()} className="btn-primary text-sm">确认开启</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;

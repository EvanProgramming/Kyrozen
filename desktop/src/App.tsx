import { useEffect, useState } from 'react';
import { ChatPage } from './pages/ChatPage';
import { LoginPage } from './pages/LoginPage';
import { OnboardingPage } from './pages/OnboardingPage';
import { SettingsPage } from './pages/SettingsPage';
import { ConnectionStatus } from './components/ConnectionStatus';
import { EditorPanel } from './components/EditorPanel';
import { FileTree } from './components/FileTree';
import { GitPanel } from './components/GitPanel';
import { HardwarePanel } from './components/HardwarePanel';
import { PreviewPanel } from './components/PreviewPanel';
import { SearchPanel } from './components/SearchPanel';

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
}

function formatQuota(quota: QuotaInfo) {
  if (quota.limit === 0) {
    return `已用 ${quota.used} / 无限制`;
  }
  return `已用 ${quota.used} / ${quota.limit}，剩余 ${quota.remaining}`;
}

function App() {
  const [token, setToken] = useState<string | null>(null);
  const [connection, setConnection] = useState<ConnectionState>('disconnected');
  const [statusMessage, setStatusMessage] = useState('等待连接');
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaInfo | null>(null);
  const [fullTrust, setFullTrust] = useState(false);
  const [editingFile, setEditingFile] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [onboardingStatus, setOnboardingStatus] = useState<'loading' | 'needed' | 'completed'>('loading');
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [language, setLanguage] = useState<'zh' | 'en'>('zh');
  const [githubStatus, setGithubStatus] = useState<{ connected: boolean; scope: string }>({ connected: false, scope: '' });

  const loadProjects = async () => {
    if (!window.kyrozen) return;
    const list = await window.kyrozen.getProjects();
    setProjects(Array.isArray(list) ? list : []);
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
      setGithubStatus({ connected: status.connected, scope: status.scope || '' });
    } catch {
      setGithubStatus({ connected: false, scope: '' });
    }
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

    const unsubConnection = window.kyrozen.onConnectionChange((state: ConnectionState, message: string) => {
      setConnection(state);
      setStatusMessage(message);
    });

    const unsubProtocolUrl = window.kyrozen.onProtocolUrl(async (url: string) => {
      const params = new URL(url).searchParams;
      const openToken = params.get('token');
      const projectId = params.get('project_id');
      if (openToken && window.kyrozen) {
        setStatusMessage('正在验证唤起令牌...');
        const verified = await window.kyrozen.verifyOpenToken(openToken);
        if (verified) {
          setToken(verified.wsToken);
          await loadProjects();
          if (projectId) {
            setCurrentProjectId(projectId);
            await window.kyrozen.setCurrentProject(projectId);
          }
        }
      }
    });

    const unsubSessionResumed = window.kyrozen.onSessionResumed(async (token: string, url: string) => {
      setToken(token);
      setStatusMessage(`已恢复会话：${url}`);
      await loadProjects();
      await loadQuota();
      await loadFullTrust();
      await loadLanguage();
      await loadGitHubStatus();
    });

    const unsubSessionEnded = window.kyrozen.onSessionEnded(() => {
      setToken(null);
      setProjects([]);
      setCurrentProjectId(null);
      setQuota(null);
      setFullTrust(false);
      setGithubStatus({ connected: false, scope: '' });
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

    window.kyrozen.requestInitialToken();

    return () => {
      clearTimeout(updateTimer);
      unsubConnection();
      unsubProtocolUrl();
      unsubSessionResumed();
      unsubSessionEnded();
      unsubOpenSettings();
      unsubOpenPreviewUrl();
      unsubFullTrustChange();
      unsubGitHubStatus();
      unsubUpdateStatus();
    };
  }, []);

  const handleOnboardingComplete = async () => {
    setOnboardingStatus('completed');
    setStatusMessage('设置完成');
    await loadProjects();
    await loadQuota();
    await loadFullTrust();
    await loadLanguage();
    await loadGitHubStatus();
  };

  const handleToggleFullTrust = async () => {
    if (!window.kyrozen) return;
    const next = !fullTrust;
    if (next) {
      const confirmed = window.confirm(
        '开启“完全信任模式”后，本次会话内所有高危操作（文件写入、命令执行等）将自动执行，不再弹窗确认。是否继续？'
      );
      if (!confirmed) return;
    }
    const result = await window.kyrozen.setFullTrust(next);
    setFullTrust(result.enabled);
  };

  const handleSelectProject = async (projectId: string) => {
    if (!window.kyrozen) return;
    setCurrentProjectId(projectId);
    setPreviewUrl(null);
    setEditingFile(null);
    await window.kyrozen.setCurrentProject(projectId);
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
        setStatusMessage('导入取消或未选择有效目录');
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
      setStatusMessage(`已导入项目：${imported.name}`);
    } catch (err: any) {
      setStatusMessage(`导入失败：${err.message || '未知错误'}`);
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
          <div className="font-hand text-3xl">Kyrozen</div>
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
      <div className="h-screen w-screen flex flex-col">
        <ConnectionStatus state={connection} message={statusMessage} />
        <LoginPage />
      </div>
    );
  }

  const currentProject = projects.find((p) => p.id === currentProjectId);

  return (
    <div className="h-screen w-screen flex flex-col bg-paper text-ink">
      <ConnectionStatus state={connection} message={statusMessage} />
      <header className="h-12 border-b border-line bg-surface flex items-center justify-between px-4 flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="font-hand text-2xl leading-none text-ink">Kyrozen</span>
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
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setShowSettings(true)}
            className="btn-secondary text-xs px-3 py-1.5"
          >
            设置
          </button>
          <div className="w-7 h-7 rounded bg-accent flex items-center justify-center text-xs font-medium text-white">
            K
          </div>
        </div>
      </header>
      <div className="flex-1 flex overflow-hidden">
        <aside data-testid="project-list" className="w-64 flex-shrink-0 border-r border-line bg-paper-sink flex flex-col">
          <div className="p-4 border-b border-line flex items-center justify-between">
            <h2 className="font-hand text-lg leading-none text-ink">我的项目</h2>
            <button
              type="button"
              onClick={handleImportLocalProject}
              title="导入已有本地目录"
              className="btn-ghost text-xs px-2 py-1"
            >
              导入
            </button>
          </div>
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

          <div className="p-3 border-t border-line space-y-3 text-xs">
            {quota && (
              <div className="text-ink-soft" title={quota.reason}>
                <div className="font-medium mb-1">云端 Token 额度</div>
                <div className="text-ink-faint">{formatQuota(quota)}</div>
              </div>
            )}

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

            <SearchPanel onOpenFile={handleOpenFileFromSearch} />

            <div className="border-t border-line pt-2">
              <div className="px-2 font-medium text-ink-soft mb-1">本地文件</div>
              <FileTree projectId={currentProjectId} onSelectFile={setEditingFile} />
            </div>

            <HardwarePanel />
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
            <ChatPage projectId={currentProjectId} onOpenPreview={handleOpenPreview} />
            {previewUrl && <PreviewPanel url={previewUrl} onClose={() => setPreviewUrl(null)} />}
          </div>
          {currentProjectId && editingFile && (
            <EditorPanel
              projectId={currentProjectId}
              relativePath={editingFile}
              onClose={() => setEditingFile(null)}
            />
          )}
        </main>
        <div className="w-72 flex-shrink-0 h-full border-l border-line bg-surface">
          <GitPanel />
        </div>
      </div>
      {showSettings && (
        <SettingsPage
          onClose={() => setShowSettings(false)}
          fullTrust={fullTrust}
          onToggleFullTrust={handleToggleFullTrust}
          githubStatus={githubStatus}
          onConnectGitHub={handleConnectGitHub}
          language={language}
          onChangeLanguage={handleChangeLanguage}
          onLogout={handleLogout}
        />
      )}
    </div>
  );
}

export default App;

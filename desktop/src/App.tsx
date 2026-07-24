import { useEffect, useState } from 'react';
import { ChatPage } from './pages/ChatPage';
import { LoginPage } from './pages/LoginPage';
import { ConnectionStatus } from './components/ConnectionStatus';
import { EditorPanel } from './components/EditorPanel';
import { FileTree } from './components/FileTree';
import { PreviewPanel } from './components/PreviewPanel';

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

interface Project {
  id: string;
  name: string;
  current_stage: string;
  description?: string;
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

  useEffect(() => {
    if (!window.kyrozen) return;

    window.kyrozen.onConnectionChange((state: ConnectionState, message: string) => {
      setConnection(state);
      setStatusMessage(message);
    });

    window.kyrozen.onProtocolUrl(async (url: string) => {
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

    window.kyrozen.onSessionResumed(async (token: string, url: string) => {
      setToken(token);
      setStatusMessage(`已恢复会话：${url}`);
      await loadProjects();
      await loadQuota();
      await loadFullTrust();
    });

    window.kyrozen.onOpenPreviewUrl((url: string) => {
      setPreviewUrl(url);
    });

    window.kyrozen.requestInitialToken();
  }, []);

  const handleLogin = async (email: string, password: string, serverUrl: string) => {
    setStatusMessage('正在登录...');
    const result = await window.kyrozen!.login(email, password, serverUrl);
    if (result.success && result.wsToken) {
      setToken(result.wsToken);
      setStatusMessage('登录成功');
      await loadProjects();
      await loadQuota();
      await loadFullTrust();
    } else {
      setConnection('error');
      setStatusMessage(result.error || '登录失败');
    }
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

  if (!token) {
    return (
      <div className="h-screen w-screen flex flex-col">
        <ConnectionStatus state={connection} message={statusMessage} />
        <LoginPage onLogin={handleLogin} />
      </div>
    );
  }

  const currentProject = projects.find((p) => p.id === currentProjectId);

  return (
    <div className="h-screen w-screen flex flex-col bg-slate-900 text-slate-100">
      <ConnectionStatus state={connection} message={statusMessage} />
      <div className="flex-1 flex overflow-hidden">
        <aside data-testid="project-list" className="w-64 flex-shrink-0 border-r border-slate-700 bg-slate-800 flex flex-col">
          <div className="p-4 border-b border-slate-700">
            <h2 className="font-semibold text-sm">我的项目</h2>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {projects.length === 0 && (
              <div className="text-xs text-slate-400 p-2">暂无项目</div>
            )}
            {projects.map((project) => (
              <button
                key={project.id}
                onClick={() => handleSelectProject(project.id)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                  project.id === currentProjectId
                    ? 'bg-blue-600 text-white'
                    : 'hover:bg-slate-700 text-slate-200'
                }`}
              >
                <div className="font-medium truncate">{project.name}</div>
                <div className="text-xs opacity-80 truncate">
                  {project.current_stage}
                </div>
              </button>
            ))}
          </div>

          <div className="p-3 border-t border-slate-700 space-y-3 text-xs">
            {quota && (
              <div className="text-slate-300" title={quota.reason}>
                <div className="font-medium mb-1">云端 Token 额度</div>
                <div className="text-slate-400">{formatQuota(quota)}</div>
              </div>
            )}

            <label className="flex items-center justify-between cursor-pointer group">
              <span className={`${fullTrust ? 'text-orange-400' : 'text-slate-300'}`}>
                完全信任模式
              </span>
              <input
                type="checkbox"
                checked={fullTrust}
                onChange={handleToggleFullTrust}
                className="sr-only peer"
              />
              <span className={`w-8 h-4 rounded-full relative transition-colors ${
                fullTrust ? 'bg-orange-500' : 'bg-slate-600'
              }`}>
                <span className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform ${
                  fullTrust ? 'translate-x-4' : ''
                }`} />
              </span>
            </label>
            {fullTrust && (
              <div className="text-orange-400">
                高危操作将自动执行，不再确认。
              </div>
            )}

            <div className="border-t border-slate-700 pt-2">
              <div className="px-2 font-medium text-slate-300 mb-1">本地文件</div>
              <FileTree projectId={currentProjectId} onSelectFile={setEditingFile} />
            </div>
          </div>
        </aside>
        <main className="flex-1 flex flex-col overflow-hidden relative">
          {currentProject && (
            <div className="px-4 py-2 bg-slate-800 border-b border-slate-700 text-sm">
              当前项目：<span className="font-medium">{currentProject.name}</span>
              <span className="ml-2 text-slate-400 text-xs">{currentProject.current_stage}</span>
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
      </div>
    </div>
  );
}

export default App;

import { useEffect, useState } from 'react';
import { ChatPage } from './pages/ChatPage';
import { LoginPage } from './pages/LoginPage';
import { ConnectionStatus } from './components/ConnectionStatus';

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

interface Project {
  id: string;
  name: string;
  current_stage: string;
  description?: string;
}

function App() {
  const [token, setToken] = useState<string | null>(null);
  const [connection, setConnection] = useState<ConnectionState>('disconnected');
  const [statusMessage, setStatusMessage] = useState('等待连接');
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);

  const loadProjects = async () => {
    if (!window.kyrozen) return;
    const list = await window.kyrozen.getProjects();
    setProjects(Array.isArray(list) ? list : []);
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
    } else {
      setConnection('error');
      setStatusMessage(result.error || '登录失败');
    }
  };

  const handleSelectProject = async (projectId: string) => {
    if (!window.kyrozen) return;
    setCurrentProjectId(projectId);
    await window.kyrozen.setCurrentProject(projectId);
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
        </aside>
        <main className="flex-1 flex flex-col overflow-hidden">
          {currentProject && (
            <div className="px-4 py-2 bg-slate-800 border-b border-slate-700 text-sm">
              当前项目：<span className="font-medium">{currentProject.name}</span>
              <span className="ml-2 text-slate-400 text-xs">{currentProject.current_stage}</span>
            </div>
          )}
          <ChatPage projectId={currentProjectId} />
        </main>
      </div>
    </div>
  );
}

export default App;

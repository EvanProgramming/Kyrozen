import { useEffect, useState } from 'react';
import { ChatPage } from './pages/ChatPage';
import { LoginPage } from './pages/LoginPage';
import { ConnectionStatus } from './components/ConnectionStatus';

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

function App() {
  const [token, setToken] = useState<string | null>(null);
  const [connection, setConnection] = useState<ConnectionState>('disconnected');
  const [statusMessage, setStatusMessage] = useState('等待连接');

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
          if (projectId) {
            window.kyrozen.setCurrentProject(projectId);
          }
        }
      }
    });

    window.kyrozen.requestInitialToken();
  }, []);

  const handleLogin = async (email: string, password: string, serverUrl: string) => {
    setStatusMessage('正在登录...');
    const result = await window.kyrozen!.login(email, password, serverUrl);
    if (result.success && result.wsToken) {
      setToken(result.wsToken);
      setStatusMessage('登录成功');
    } else {
      setConnection('error');
      setStatusMessage(result.error || '登录失败');
    }
  };

  if (!token) {
    return (
      <div className="h-screen w-screen flex flex-col">
        <ConnectionStatus state={connection} message={statusMessage} />
        <LoginPage onLogin={handleLogin} />
      </div>
    );
  }

  return (
    <div className="h-screen w-screen flex flex-col">
      <ConnectionStatus state={connection} message={statusMessage} />
      <ChatPage />
    </div>
  );
}

export default App;
